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


def _parse_skill_array(raw: Optional[str]) -> list:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list) and all(isinstance(s, str) for s in parsed):
        return parsed
    return []


@router.post("/jd/parse")
async def parse_jd(
    jd_text: str = Form(...),
    inferred_skills: Optional[str] = Form(None),
    explicit_skills: Optional[str] = Form(None),
):
    """
    Parse a job description's skills/domain without tailoring a resume
    against it. Returns {job_description, domain, skill_matches}.

    inferred_skills: optional JSON array string of a resume's inferred
    (plausible-but-unlisted) skills. explicit_skills: optional JSON array
    string of the resume's already-listed skills. When either is given,
    both pools are combined into one candidate list for a single semantic
    match against the JD's requirements - e.g. "hyperparameter tuning" (an
    inferred skill) or "Power BI" (an explicit one) each satisfying "data
    modeling techniques"/"business intelligence", requirements phrased more
    broadly than any single skill's own wording. Matching both pools
    together (rather than two separate calls) lets the caller tell which
    JD requirements are already covered by what the candidate explicitly
    has - those don't need an inferred-skill suggestion - and rank any
    remaining inferred-skill candidates by how many still-uncovered
    requirements each one would satisfy.
    """
    try:
        settings.validate_api_key()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        jd, domain_info = await parse_job_description_from_text(jd_text)

        skill_matches: list = []
        candidate_pool = _parse_skill_array(explicit_skills) + _parse_skill_array(inferred_skills)
        if candidate_pool:
            jd_skill_list = (jd.must_have_skills or []) + (jd.nice_to_have_skills or [])
            skill_matches = await match_inferred_skills_to_jd(jd_skill_list, candidate_pool)

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
