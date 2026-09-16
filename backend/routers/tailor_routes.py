import asyncio
import json
import logging
import os
import re
import tempfile
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from openai import AuthenticationError
from pydantic import ValidationError

from core.config import settings
from core.exceptions import TailoringGenerationError
from core.timing import timed_stage
from models.resume_models import Resume
from services.pdf_resume_parser import parse_pdf_resume_to_json
from services.job_parser import parse_job_description_from_text
from services.tailor_engine import tailor_resume, ensure_technical_skills
from services.pdf_writer import render_resume_pdf
from services.skill_inference import match_inferred_skills_to_jd, _resume_background_text
from services.bullet_verifier import _contains_skill
from services.llm_client import classify_confirmed_skills

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Tailoring"])


def _normalize_skill(skill: str) -> str:
    """Lowercase and collapse whitespace for matching."""
    return re.sub(r"\s+", " ", skill.strip().lower())


def _parse_skill_line(raw_skills: str) -> List[str]:
    """Split a pipe/comma/semicolon-separated skill line into a list."""
    if not raw_skills:
        return []
    normalized = raw_skills
    for sep in ["|", ";"]:
        normalized = normalized.replace(sep, ",")
    return [s.strip() for s in normalized.split(",") if s.strip()]


def _merge_and_dedupe_skills(*skill_lists: List[str]) -> List[str]:
    merged: List[str] = []
    seen = set()
    for skills in skill_lists:
        for skill in skills or []:
            clean = skill.strip()
            if not clean:
                continue
            key = _normalize_skill(clean)
            if key not in seen:
                seen.add(key)
                merged.append(clean)
    return merged


def _compute_compatibility(
    resume_skills: List[str],
    jd_data: Dict[str, Any],
    credited_skills: Optional[List[str]] = None,
    background_text: str = "",
) -> Dict[str, Any]:
    """
    Calculate compatibility using a weighted formula:
    - must-have coverage weighted 70%
    - nice-to-have coverage weighted 30%
    - cap at 60 if any must-haves are missing

    credited_skills: JD skill requirements (verbatim wording) to also treat
    as matched even though they're not a literal match in resume_skills -
    used when the candidate confirmed a concrete skill (e.g. "hyperparameter
    tuning") that a separate LLM pass determined concretely satisfies a more
    broadly-worded JD requirement (e.g. "data modeling techniques"). That
    broader wording is never written onto the resume itself - this only
    affects the score/matched-list, not resume content.

    background_text: full resume text (skill_inference._resume_background_text
    - headline/summary/education major/experience+project titles and
    bullets/skills/certifications), also searched for a literal mention of
    each JD skill. resume_skills alone only covers the Skills/Technical
    Skills section - a real skill mentioned only in bullet text (e.g.
    "Linux" used throughout experience bullets but never listed under
    Technical Skills) was previously invisible to this scorer even though
    it's genuinely present on the resume. This only ever credits a LITERAL
    text match via the same word-boundary-safe _contains_skill matcher
    bullet_verifier.py already relies on elsewhere - never an inferred or
    assumed skill the resume doesn't actually state.
    """
    must_have = jd_data.get("must_have_skills", []) or []
    nice_to_have = jd_data.get("nice_to_have_skills", []) or []

    # Build lookup maps to preserve original casing in outputs
    resume_map = {_normalize_skill(s): s for s in resume_skills}
    must_map = {_normalize_skill(s): s for s in must_have}
    nice_map = {_normalize_skill(s): s for s in nice_to_have}

    resume_norm = set(resume_map.keys())
    credited_norm = {_normalize_skill(s) for s in (credited_skills or [])}
    must_norm = list(must_map.keys())
    nice_norm = list(nice_map.keys())

    def _covered(norm_key: str, original: str) -> bool:
        return (
            norm_key in resume_norm
            or norm_key in credited_norm
            or (background_text and _contains_skill(background_text, original))
        )

    matched_must = [must_map[s] for s in must_norm if _covered(s, must_map[s])]
    matched_nice = [nice_map[s] for s in nice_norm if _covered(s, nice_map[s])]
    missing_must = [must_map[s] for s in must_norm if not _covered(s, must_map[s])]
    missing_nice = [nice_map[s] for s in nice_norm if not _covered(s, nice_map[s])]

    total_must = len(must_norm)
    total_nice = len(nice_norm)

    must_coverage = len(matched_must) / total_must if total_must else 0
    nice_coverage = len(matched_nice) / total_nice if total_nice else 0

    if total_must == 0:
        raw_score = 100 * nice_coverage
    elif total_nice == 0:
        # When no nice-to-haves exist, score purely on must-have coverage
        raw_score = 100 * must_coverage
        if missing_must:
            raw_score = min(raw_score, 80)
    else:
        raw_score = 100 * (0.7 * must_coverage + 0.3 * nice_coverage)
        if missing_must:
            raw_score = min(raw_score, 80)

    score = max(0, min(100, round(raw_score)))

    resume_skill_hits = [resume_map[s] for s in resume_norm if s in set(must_norm + nice_norm)]

    return {
        "score": score,
        "must_coverage": must_coverage,
        "nice_coverage": nice_coverage,
        "matched_must_have": matched_must,
        "matched_nice_to_have": matched_nice,
        "missing_must_have": missing_must,
        "missing_nice_to_have": missing_nice,
        "resume_skill_hits": resume_skill_hits,
    }

def _parse_skill_array_field(raw: Optional[str], field_name: str) -> List[str]:
    """Parse a JSON-array-of-strings form field, or raise a 400 naming the
    field, so a malformed value surfaces clearly instead of a generic 500."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list) or not all(isinstance(s, str) for s in parsed):
            raise ValueError(f"{field_name} must be a JSON array of strings")
        return parsed
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}.")


@router.post("/tailor/pdf")
async def tailor_resume_from_pdf(
    pdf: Optional[UploadFile] = File(None),
    resume_json: Optional[str] = Form(None),
    jd_text: str = Form(...),
    output: str = Form("json"),
    resume_format: str = Form("regular"),
    additional_hard_skills: Optional[str] = Form(None),
    additional_applied_skills: Optional[str] = Form(None),
    additional_unclassified_skills: Optional[str] = Form(None),
    additional_skills: Optional[str] = Form(None),
):
    """
    Upload either:
    - Resume PDF (parsed fresh), or
    - resume_json (an already-parsed Resume, from a previously-saved
      base_resume - skips the PDF parse entirely)
    Plus JD text.

    Skills the candidate explicitly confirmed (e.g. from the inferred-skills
    picker), each a JSON array string:
    - additional_hard_skills: tools/languages/certifications - merged into
      the resume's Technical Skills.
    - additional_applied_skills: methodologies/techniques - woven into
      bullet wording instead.
    - additional_unclassified_skills: confirmed skills from a base_resumes
      row saved before the picker tagged tool-vs-methodology at suggestion
      time - classified here via tailor_resume's legacy fallback path.
    - additional_skills: DEPRECATED alias for additional_unclassified_skills
      - the pre-split field names above didn't exist yet when this was the
      only field. Kept for callers not yet updated to the new contract
      (e.g. the web app's own tailor page, a separate implementation of
      this same picker); treated identically to additional_unclassified_skills.

    Returns:
    - Tailored resume JSON
    """
    if bool(pdf) == bool(resume_json):
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of 'pdf' or 'resume_json'.",
        )

    # Validate API key before processing
    try:
        settings.validate_api_key()
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    # Validated up-front (not inside the try/except below) so a malformed
    # skill field surfaces as its own 400 instead of being swallowed by the
    # generic 500 handler further down.
    parsed_hard_skills = _parse_skill_array_field(additional_hard_skills, "additional_hard_skills")
    parsed_applied_skills = _parse_skill_array_field(additional_applied_skills, "additional_applied_skills")
    parsed_unclassified_skills = _parse_skill_array_field(
        additional_unclassified_skills, "additional_unclassified_skills"
    ) + _parse_skill_array_field(additional_skills, "additional_skills")

    parsed_resume: Optional[Resume] = None
    if resume_json is not None:
        try:
            parsed_resume = Resume.model_validate(json.loads(resume_json))
        except (json.JSONDecodeError, ValidationError):
            raise HTTPException(status_code=400, detail="Invalid resume_json.")

    temp_path: Optional[str] = None
    if pdf is not None:
        # Unique per-request temp filename - reusing pdf.filename directly let
        # two concurrent requests uploading a common name (e.g. "resume.pdf")
        # collide on the same path.
        suffix = os.path.splitext(pdf.filename or "")[1] or ".pdf"
        fd, temp_path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(await pdf.read())

    timings: Dict[str, int] = {}

    try:
        if temp_path is not None:
            # 1) PDF -> Resume Object, JD text -> JobDescription (independent
            # of each other, so run them concurrently instead of sequentially)
            with timed_stage("parse_resume_and_jd", timings):
                resume, (jd, domain_info) = await asyncio.gather(
                    parse_pdf_resume_to_json(temp_path),
                    parse_job_description_from_text(jd_text),
                )
        else:
            # Already-parsed resume supplied - only the JD needs parsing.
            resume = parsed_resume
            with timed_stage("parse_jd", timings):
                jd, domain_info = await parse_job_description_from_text(jd_text)

        # Resolve confirmed skills that came in unclassified (a legacy
        # base_resumes row saved before the picker tagged tool-vs-
        # methodology at suggestion time) into the hard/applied split now -
        # needed before the pre-merge below, which must only fold HARD
        # skills into resume.skills/Technical Skills. Applied/methodology
        # skills are deliberately excluded from this merge; they're woven
        # into bullet wording instead, inside tailor_resume() (step 5d).
        if parsed_unclassified_skills:
            with timed_stage("classify_confirmed_skills", timings):
                classified = await classify_confirmed_skills(parsed_unclassified_skills)
            parsed_hard_skills = parsed_hard_skills + (classified.get("hard_skills") or [])
            parsed_applied_skills = parsed_applied_skills + (classified.get("applied_skills") or [])

        # Parse any dedicated skills line and MERGE with extracted skills (do not overwrite).
        line_skills: List[str] = []
        if getattr(resume.additional_info, "computer_skills", None):
            line_skills = _parse_skill_line(resume.additional_info.computer_skills)
        elif getattr(resume.additional_info, "technical_skills", None):
            line_skills = _parse_skill_line(resume.additional_info.technical_skills)

        category_skills: List[str] = [item for cat in resume.technical_skills for item in cat.items]

        # Confirmed HARD skills (tools/languages/certifications) must be
        # merged in here, before categorize_skills below - not left to
        # tailor_resume()'s own merge, which runs after categorization and
        # left newly-confirmed skills out of the rendered TECHNICAL SKILLS
        # section entirely even though they appeared in the flat skills
        # list. tailor_resume() still merges them too (idempotent - a no-op
        # for anything already present) so it stays correct if ever called
        # without this router in front of it. Applied/methodology skills
        # are intentionally NOT merged here - see above.
        resume.skills = _merge_and_dedupe_skills(
            resume.skills or [], line_skills, category_skills, parsed_hard_skills
        )

        # The Regular template's Additional Info section renders
        # additional_info.computer_skills/technical_skills as a raw string
        # directly - not resume.skills - so a confirmed picker skill that's
        # only reflected in resume.skills never actually shows up in the
        # rendered PDF. Append any newly-confirmed HARD skills onto
        # whichever raw line the resume originally had, so the two stay in
        # sync. No-op for a resume with no additional_info skills line at
        # all (the template falls back to rendering resume.skills directly
        # in that case).
        if parsed_hard_skills and resume.additional_info:
            # Truthy check, not `is not None` - additional_info.computer_skills/
            # technical_skills can be an empty string rather than None for a
            # resume with no such line, and appending onto "" produced a
            # leading ", " artifact ("Technical Skills: , Information
            # Architecture, ...") on the rendered PDF.
            existing_line = resume.additional_info.computer_skills or resume.additional_info.technical_skills
            if existing_line:
                existing_lower = {_normalize_skill(s) for s in _parse_skill_line(existing_line)}
                new_items = [s for s in parsed_hard_skills if _normalize_skill(s) not in existing_lower]
                if new_items:
                    appended = existing_line.rstrip().rstrip(",") + ", " + ", ".join(new_items)
                    if resume.additional_info.computer_skills:
                        resume.additional_info.computer_skills = appended
                    else:
                        resume.additional_info.technical_skills = appended

        # Categorize skills into TECHNICAL SKILLS *before* tailoring so the
        # compact-mode/spacing decision (computed inside tailor_resume) knows
        # about the section that's about to be added - otherwise a resume
        # that's borderline full gets loose spacing and overflows to page 2
        # once the extra section shows up at render time.
        use_technical_skills = resume_format.lower() == "technical" and output.lower() == "pdf"
        if use_technical_skills:
            with timed_stage("categorize_skills", timings):
                resume = await ensure_technical_skills(resume, allow_recategorize=True)

        # 3) Tailor
        with timed_stage("tailor", timings):
            tailored_resume = await tailor_resume(
                resume, jd, domain_info,
                additional_hard_skills=parsed_hard_skills,
                additional_applied_skills=parsed_applied_skills,
            )

        # 3b) Compatibility report
        jd_data = jd.model_dump()
        background_text = _resume_background_text(tailored_resume)
        compatibility = _compute_compatibility(tailored_resume.skills or [], jd_data, background_text=background_text)

        # Semantic credit pass: literal matching above only catches a JD
        # requirement worded identically to a resume skill. Requirements
        # phrased more broadly than any single skill's own wording (e.g.
        # "business intelligence" satisfied by an already-listed "Power BI",
        # or "data modeling techniques" satisfied by a confirmed
        # "hyperparameter tuning") need an LLM judgment call instead. Runs
        # unconditionally against the resume's final skill list (explicit +
        # any confirmed hard skills, already merged in above) so a
        # resume with no inferred-skills picker interaction still gets full
        # credit for what it already explicitly lists - not just resumes
        # that happened to go through the picker.
        still_missing = compatibility["missing_must_have"] + compatibility["missing_nice_to_have"]
        if still_missing:
            # Certifications (e.g. "Adobe Certified Professional") live in a
            # separate field from resume.skills and are just as legitimate
            # evidence for a JD requirement (e.g. "Adobe CC") - included here
            # for scoring only, same as everything else in this pass; never
            # merged into resume.skills or written onto the resume itself.
            candidate_skills = list(tailored_resume.skills or [])
            if tailored_resume.additional_info and tailored_resume.additional_info.certifications:
                candidate_skills += tailored_resume.additional_info.certifications
            # Confirmed applied/methodology skills (e.g. "Statistical
            # Analysis") never get merged into resume.skills - they're woven
            # into bullet wording instead - but the candidate still
            # genuinely confirmed having them, so a JD requirement they
            # satisfy should count toward the score too, not just toward
            # bullet content.
            if parsed_applied_skills:
                candidate_skills += parsed_applied_skills
            with timed_stage("credit_semantic_skills", timings):
                matches = await match_inferred_skills_to_jd(still_missing, candidate_skills)
            credited = [m["jd_skill"] for m in matches]
            if credited:
                compatibility = _compute_compatibility(
                    tailored_resume.skills or [], jd_data, credited, background_text=background_text
                )

        timings_header = json.dumps(timings)

        # 4) Output mode
        if output.lower() == "pdf":
            with timed_stage("render_pdf", timings):
                pdf_bytes = render_resume_pdf(tailored_resume, use_technical_skills)
            return StreamingResponse(
                iter([pdf_bytes]),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": 'attachment; filename="tailored_resume.pdf"',
                    "X-Pipeline-Timings": json.dumps(timings),
                },
            )

        return JSONResponse(
            content=jsonable_encoder({
                "resume": tailored_resume,
                "job_description": jd,
                "compatibility": compatibility,
            }),
            headers={"X-Pipeline-Timings": timings_header},
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=401,
            detail=f"OpenAI API authentication failed. Please check your API key in the .env file.\n"
                   f"Error: {str(e)}\n"
                   f"Get your API key from: https://platform.openai.com/account/api-keys"
        )
    except TailoringGenerationError:
        logger.exception("Resume tailoring failed")
        raise HTTPException(
            status_code=502,
            detail="Resume tailoring failed. Please try again."
        )
    except Exception:
        logger.exception("tailor_resume_from_pdf failed")
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while processing your request."
        )
    finally:
        if temp_path is not None:
            try:
                os.remove(temp_path)
            except OSError:
                pass
