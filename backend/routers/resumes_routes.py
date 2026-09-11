"""
Tester-only utility (Phase 3): backfill parsed_data/inferred_skills on
base_resumes rows saved before Phase 1 existed. Deliberately does NOT run
the full reformat_resume() decision pipeline (trim/compact-mode/headline-
summary regeneration) - the PDF being re-parsed here is already in its
final reformatted shape, so redoing those decisions risks inconsistent
regeneration of content that's already fine. Only parses + infers skills;
never re-renders or touches the saved PDF file.
"""
import json
import logging
import os
import tempfile
from typing import Dict

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from openai import AuthenticationError

from core.config import settings
from core.timing import timed_stage
from services.pdf_resume_parser import parse_pdf_resume_to_json
from services.skill_inference import infer_plausible_skills_for_resume

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Resumes"])


@router.post("/resumes/reparse")
async def reparse_resume(pdf: UploadFile = File(...)):
    """
    Parse an already-saved resume PDF and infer plausible skills.
    Returns {resume, inferred_skills} - no PDF re-render.
    """
    try:
        settings.validate_api_key()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    suffix = os.path.splitext(pdf.filename or "")[1] or ".pdf"
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(await pdf.read())

    timings: Dict[str, int] = {}

    try:
        with timed_stage("parse_resume", timings):
            resume = await parse_pdf_resume_to_json(temp_path)

        # Normalize skills from computer/technical skills strings into a
        # list - mirrors reformat_routes.py's parse-time normalization, in
        # case the PDF's skills text still reads back into additional_info
        # instead of a clean list.
        if getattr(resume.additional_info, "computer_skills", None):
            raw_skills = resume.additional_info.computer_skills
            for sep in ["|", ";"]:
                raw_skills = raw_skills.replace(sep, ",")
            parsed_skills = [s.strip() for s in raw_skills.split(",") if s.strip()]
            if parsed_skills:
                resume.skills = parsed_skills
        elif getattr(resume.additional_info, "technical_skills", None):
            raw_skills = resume.additional_info.technical_skills
            for sep in ["|", ";"]:
                raw_skills = raw_skills.replace(sep, ",")
            parsed_skills = [s.strip() for s in raw_skills.split(",") if s.strip()]
            if parsed_skills:
                resume.skills = parsed_skills

        with timed_stage("infer_skills", timings):
            inferred_skills = await infer_plausible_skills_for_resume(resume)

        return JSONResponse(
            content=jsonable_encoder({
                "resume": resume,
                "inferred_skills": inferred_skills,
            }),
            headers={"X-Pipeline-Timings": json.dumps(timings)},
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=401,
            detail=f"OpenAI API authentication failed. Please check your API key in the .env file.\n"
                   f"Error: {str(e)}\n"
                   f"Get your API key from: https://platform.openai.com/account/api-keys"
        )
    except Exception:
        logger.exception("reparse_resume failed")
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while processing your request."
        )
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass
