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
from typing import Dict, List

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from openai import AuthenticationError

from core.config import settings
from core.exceptions import UnreadablePdfError
from core.timing import timed_stage
from services.pdf_reader import extract_text_from_pdf_or_raise
from services.pdf_resume_parser import parse_pdf_resume_to_json
from services.skill_inference import infer_plausible_skills_for_resume
from services.skill_utils import parse_skill_line, merge_and_dedupe_skills

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Resumes"])


@router.post("/resumes/validate-pdf")
async def validate_pdf(pdf: UploadFile = File(...)):
    """
    Cheap pre-upload check: does this PDF have a real text layer? No OpenAI
    call - just the same pdfplumber extraction the parser itself relies on -
    so the frontend can reject a scanned/flattened-image PDF right after
    file selection, before the user picks a template and waits through a
    full reformat only to hit the same error at the end.
    """
    suffix = os.path.splitext(pdf.filename or "")[1] or ".pdf"
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(await pdf.read())

    try:
        extract_text_from_pdf_or_raise(temp_path)
        return JSONResponse(content={"valid": True})
    except UnreadablePdfError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        logger.exception("validate_pdf failed")
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while checking your PDF."
        )
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


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

        # Merge (never overwrite) skills from a dedicated Skills section with
        # any separate "Computer/Technical Skills" line under Additional Info
        # - mirrors reformat_routes.py's parse-time normalization. See that
        # router for why this must be a merge, not an overwrite.
        line_skills: List[str] = []
        if getattr(resume.additional_info, "computer_skills", None):
            line_skills = parse_skill_line(resume.additional_info.computer_skills)
            resume.additional_info.computer_skills = ""
        elif getattr(resume.additional_info, "technical_skills", None):
            line_skills = parse_skill_line(resume.additional_info.technical_skills)
            resume.additional_info.technical_skills = ""

        if line_skills:
            resume.skills = merge_and_dedupe_skills(resume.skills or [], line_skills)

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
    except UnreadablePdfError as e:
        raise HTTPException(status_code=422, detail=str(e))
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
