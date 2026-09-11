"""
Standalone job-description parsing (Phase 4) - lets the frontend fetch a
JD's must-have/nice-to-have skills before submitting a tailor request, to
compute overlap with a resume's inferred_skills and offer a picker. Thin
wrapper over job_parser.py's existing parse/classify call - no new
extraction or caching logic, reuses what /api/tailor/pdf already relies on.
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Form, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from openai import AuthenticationError

from core.config import settings
from services.job_parser import parse_job_description_from_text
from services.skill_inference import match_inferred_skills_to_jd

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Job Description"])


@router.post("/jd/parse")
async def parse_jd(jd_text: str = Form(...), inferred_skills: Optional[str] = Form(None)):
    """
    Parse a job description's skills/domain without tailoring a resume
    against it. Returns {job_description, domain, skill_matches}.

    inferred_skills: optional JSON array string of a resume's inferred
    skills - when given, also returns which of them concretely satisfy a
    JD requirement phrased more broadly than the skill's own wording (e.g.
    "hyperparameter tuning" satisfying "data modeling techniques"), on top
    of whatever the frontend already finds via plain literal overlap.
    """
    try:
        settings.validate_api_key()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        jd, domain_info = await parse_job_description_from_text(jd_text)

        skill_matches: list = []
        if inferred_skills:
            try:
                parsed_inferred = json.loads(inferred_skills)
            except json.JSONDecodeError:
                parsed_inferred = None
            if isinstance(parsed_inferred, list) and all(isinstance(s, str) for s in parsed_inferred):
                jd_skill_list = (jd.must_have_skills or []) + (jd.nice_to_have_skills or [])
                skill_matches = await match_inferred_skills_to_jd(jd_skill_list, parsed_inferred)

        return JSONResponse(content=jsonable_encoder({
            "job_description": jd,
            "domain": domain_info,
            "skill_matches": skill_matches,
        }))
    except AuthenticationError as e:
        raise HTTPException(
            status_code=401,
            detail=f"OpenAI API authentication failed. Please check your API key in the .env file.\n"
                   f"Error: {str(e)}\n"
                   f"Get your API key from: https://platform.openai.com/account/api-keys"
        )
    except Exception:
        logger.exception("parse_jd failed")
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while parsing the job description."
        )
