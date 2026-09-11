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
from services.skill_inference import match_inferred_skills_to_jd
from services.pdf_writer import render_resume_pdf

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

    matched_must = [must_map[s] for s in must_norm if s in resume_norm or s in credited_norm]
    matched_nice = [nice_map[s] for s in nice_norm if s in resume_norm or s in credited_norm]
    missing_must = [must_map[s] for s in must_norm if s not in resume_norm and s not in credited_norm]
    missing_nice = [nice_map[s] for s in nice_norm if s not in resume_norm and s not in credited_norm]

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

@router.post("/tailor/pdf")
async def tailor_resume_from_pdf(
    pdf: Optional[UploadFile] = File(None),
    resume_json: Optional[str] = Form(None),
    jd_text: str = Form(...),
    output: str = Form("json"),
    resume_format: str = Form("regular"),
    additional_skills: Optional[str] = Form(None),
    credited_skills: Optional[str] = Form(None),
):
    """
    Upload either:
    - Resume PDF (parsed fresh), or
    - resume_json (an already-parsed Resume, from a previously-saved
      base_resume - skips the PDF parse entirely)
    Plus JD text.

    additional_skills: optional JSON array string of skills the candidate
    explicitly confirmed (e.g. from the inferred-skills picker) - merged
    into the resume's truthful skill pool before tailoring.

    credited_skills: optional JSON array string of JD requirement phrases
    (verbatim from the JD's must/nice-to-have lists) that the frontend
    already determined are satisfied by the confirmed additional_skills, via
    /api/jd/parse's skill_matches (computed there against the resume's full
    inferred_skills pool, which gives the model more context to judge a
    match confidently than re-deriving it here against only the smaller
    confirmed subset would). Only affects the compatibility score/matched
    list - never written onto the resume itself.
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
    # resume_json/additional_skills surfaces as its own 400 instead of being
    # swallowed by the generic 500 handler further down.
    parsed_additional_skills: List[str] = []
    if additional_skills:
        try:
            parsed_additional_skills = json.loads(additional_skills)
            if not isinstance(parsed_additional_skills, list) or not all(
                isinstance(s, str) for s in parsed_additional_skills
            ):
                raise ValueError("additional_skills must be a JSON array of strings")
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid additional_skills.")

    parsed_credited_skills: List[str] = []
    if credited_skills:
        try:
            parsed_credited_skills = json.loads(credited_skills)
            if not isinstance(parsed_credited_skills, list) or not all(
                isinstance(s, str) for s in parsed_credited_skills
            ):
                raise ValueError("credited_skills must be a JSON array of strings")
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid credited_skills.")

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

        # Parse any dedicated skills line and MERGE with extracted skills (do not overwrite).
        line_skills: List[str] = []
        if getattr(resume.additional_info, "computer_skills", None):
            line_skills = _parse_skill_line(resume.additional_info.computer_skills)
        elif getattr(resume.additional_info, "technical_skills", None):
            line_skills = _parse_skill_line(resume.additional_info.technical_skills)

        category_skills: List[str] = [item for cat in resume.technical_skills for item in cat.items]

        # additional_skills (confirmed from the picker) must be merged in
        # here, before categorize_skills below - not left to tailor_resume()'s
        # own merge, which runs after categorization and left newly-confirmed
        # skills out of the rendered TECHNICAL SKILLS section entirely even
        # though they appeared in the flat skills list. tailor_resume() still
        # merges them too (idempotent - a no-op for anything already present)
        # so it stays correct if ever called without this router in front of it.
        resume.skills = _merge_and_dedupe_skills(
            resume.skills or [], line_skills, category_skills, parsed_additional_skills
        )

        # Categorize skills into TECHNICAL SKILLS *before* tailoring so the
        # compact-mode/spacing decision (computed inside tailor_resume) knows
        # about the section that's about to be added - otherwise a resume
        # that's borderline full gets loose spacing and overflows to page 2
        # once the extra section shows up at render time.
        use_technical_skills = resume_format.lower() == "technical" and output.lower() == "pdf"
        if use_technical_skills:
            with timed_stage("categorize_skills", timings):
                resume = await ensure_technical_skills(resume)

        # 3) Tailor
        with timed_stage("tailor", timings):
            tailored_resume = await tailor_resume(resume, jd, domain_info, parsed_additional_skills)

        # 3b) Compatibility report
        jd_data = jd.model_dump()
        compatibility = _compute_compatibility(tailored_resume.skills or [], jd_data)

        # If the frontend determined (via /api/jd/parse's skill_matches, run
        # earlier against the resume's full inferred_skills pool) that some
        # confirmed skills satisfy a JD requirement phrased more broadly than
        # their own wording, credit those requirements here. Restricted to
        # the JD's own verbatim requirement text and to requirements still
        # missing after the exact-match pass, so a malformed/tampered value
        # can't inflate the score - only affects the score/matched list, the
        # broader wording itself is never written onto the resume.
        if parsed_credited_skills:
            still_missing = set(compatibility["missing_must_have"] + compatibility["missing_nice_to_have"])
            all_jd_skills = set((jd.must_have_skills or []) + (jd.nice_to_have_skills or []))
            credited = [s for s in parsed_credited_skills if s in still_missing and s in all_jd_skills]
            if credited:
                compatibility = _compute_compatibility(tailored_resume.skills or [], jd_data, credited)

        # A second, server-side pass: the frontend's credited_skills above
        # only ever considered the resume's *inferred* skills (computed at
        # picker time) as evidence - it has no way to know whether a JD
        # requirement is actually satisfied by a skill the candidate already
        # had explicitly listed (e.g. "business intelligence" satisfied by an
        # already-listed "Power BI"/"Tableau", not anything from the picker).
        # Only runs when the picker was actually used (same cost/latency
        # footprint as the pass above, not added to every tailor request),
        # using the full final skill list (explicit + confirmed) as context.
        if parsed_additional_skills:
            still_missing = compatibility["missing_must_have"] + compatibility["missing_nice_to_have"]
            if still_missing:
                with timed_stage("credit_explicit_skills", timings):
                    matches = await match_inferred_skills_to_jd(still_missing, tailored_resume.skills or [])
                credited = [m["jd_skill"] for m in matches]
                if credited:
                    compatibility = _compute_compatibility(tailored_resume.skills or [], jd_data, credited)

        timings_header = json.dumps(timings)

        # 4) Output mode
        if output.lower() == "pdf":
            with timed_stage("render_pdf", timings):
                pdf_bytes = render_resume_pdf(tailored_resume, use_technical_skills=use_technical_skills)
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
