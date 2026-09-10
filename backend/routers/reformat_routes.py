import base64
import json
import logging
import os
import tempfile
from typing import Dict

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from openai import AuthenticationError

from core.config import settings
from core.timing import timed_stage
from services.pdf_resume_parser import parse_pdf_resume_to_json
from services.pdf_writer import render_resume_pdf
from services.reformat_engine import reformat_resume
from services.skill_inference import infer_plausible_skills_for_resume
from services.tailor_engine import ensure_technical_skills

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Reformatter"])


@router.post("/reformat/pdf")
async def reformat_resume_from_pdf(
    pdf: UploadFile = File(...),
    resume_format: str = Form("regular"),
    output: str = Form("pdf"),
):
    """
    Upload a resume PDF and get a reformatted, ATS-friendly PDF back.
    No JD input and no bullet rewriting.

    output="pdf" (default, unchanged): raw PDF bytes, as before.
    output="json": {resume, inferred_skills, pdf_base64} in one body - used
    by the save flow, which needs the structured data (to persist alongside
    the resume, skipping a re-parse on every future tailor request) and the
    actual PDF (for storage) from a single backend parse. The PDF is
    base64-encoded in the JSON body rather than carried via a response
    header - a dense resume's structured JSON could approach typical ~8KB
    proxy header-size limits, unlike the small dict already sent via
    X-Pipeline-Timings.
    """
    try:
        settings.validate_api_key()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Unique per-request temp filename - reusing pdf.filename directly let
    # two concurrent requests uploading a common name (e.g. "resume.pdf")
    # collide on the same path.
    suffix = os.path.splitext(pdf.filename or "")[1] or ".pdf"
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(await pdf.read())

    timings: Dict[str, int] = {}

    try:
        with timed_stage("parse_resume", timings):
            resume = await parse_pdf_resume_to_json(temp_path)

        # Normalize skills from computer/technical skills strings into list
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

        # Categorize skills into TECHNICAL SKILLS *before* reformatting so the
        # compact-mode/spacing decision (computed inside reformat_resume) knows
        # about the section that's about to be added - otherwise a resume
        # that's borderline full gets loose spacing and overflows to page 2
        # once the extra section shows up at render time.
        use_technical_skills = resume_format.lower() == "technical"
        if use_technical_skills:
            with timed_stage("categorize_skills", timings):
                resume = await ensure_technical_skills(resume)

        with timed_stage("reformat", timings):
            reformatted = await reformat_resume(resume)

        with timed_stage("render_pdf", timings):
            pdf_bytes = render_resume_pdf(reformatted, use_technical_skills=use_technical_skills)

        if output.lower() == "json":
            with timed_stage("infer_skills", timings):
                inferred_skills = await infer_plausible_skills_for_resume(reformatted)

            return JSONResponse(
                content=jsonable_encoder({
                    "resume": reformatted,
                    "inferred_skills": inferred_skills,
                    "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
                }),
                headers={"X-Pipeline-Timings": json.dumps(timings)},
            )

        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="ats_resume.pdf"',
                "X-Pipeline-Timings": json.dumps(timings),
            },
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=401,
            detail=f"OpenAI API authentication failed. Please check your API key in the .env file.\n"
                   f"Error: {str(e)}\n"
                   f"Get your API key from: https://platform.openai.com/account/api-keys"
        )
    except Exception:
        logger.exception("reformat_resume_from_pdf failed")
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while processing your request."
        )
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass
