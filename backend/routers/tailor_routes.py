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


def _compute_compatibility(resume_skills: List[str], jd_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate compatibility using a weighted formula:
    - must-have coverage weighted 70%
    - nice-to-have coverage weighted 30%
    - cap at 60 if any must-haves are missing
    """
    must_have = jd_data.get("must_have_skills", []) or []
    nice_to_have = jd_data.get("nice_to_have_skills", []) or []

    # Build lookup maps to preserve original casing in outputs
    resume_map = {_normalize_skill(s): s for s in resume_skills}
    must_map = {_normalize_skill(s): s for s in must_have}
    nice_map = {_normalize_skill(s): s for s in nice_to_have}

    resume_norm = set(resume_map.keys())
    must_norm = list(must_map.keys())
    nice_norm = list(nice_map.keys())

    matched_must = [must_map[s] for s in must_norm if s in resume_norm]
    matched_nice = [nice_map[s] for s in nice_norm if s in resume_norm]
    missing_must = [must_map[s] for s in must_norm if s not in resume_norm]
    missing_nice = [nice_map[s] for s in nice_norm if s not in resume_norm]

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
):
    """
    Upload either:
    - Resume PDF (parsed fresh), or
    - resume_json (an already-parsed Resume, from a previously-saved
      base_resume - skips the PDF parse entirely)
    Plus JD text.
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
    # resume_json surfaces as its own 400 instead of being swallowed by the
    # generic 500 handler further down.
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

        resume.skills = _merge_and_dedupe_skills(resume.skills or [], line_skills, category_skills)

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
            tailored_resume = await tailor_resume(resume, jd, domain_info)

        # 3b) Compatibility report
        jd_data = jd.model_dump()
        compatibility = _compute_compatibility(tailored_resume.skills or [], jd_data)

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
