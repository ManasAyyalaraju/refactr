import json
from typing import Optional
from models.resume_models import Resume
from services.llm_client import generate_headline_summary
from services.tailor_engine import (
    compute_compact_mode,
    conditionally_remove_headline_summary,
    format_skills_list,
)


def _strip_text(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    return text.strip()


def _trim_resume_strings(resume: Resume) -> Resume:
    """Light trimming; does not rewrite content."""
    resume.name = _strip_text(resume.name)
    if resume.contact:
        resume.contact.email = _strip_text(resume.contact.email)
        resume.contact.phone = _strip_text(resume.contact.phone)
        resume.contact.linkedin = _strip_text(resume.contact.linkedin)
        resume.contact.website = _strip_text(resume.contact.website)
        resume.contact.location = _strip_text(resume.contact.location)

    resume.headline = _strip_text(resume.headline)
    resume.summary = _strip_text(resume.summary)

    resume.skills = [s.strip() for s in resume.skills if s and s.strip()]

    for cat in resume.technical_skills:
        cat.label = _strip_text(cat.label) or cat.label
        cat.items = [i.strip() for i in cat.items if i and i.strip()]

    for exp in resume.experience:
        exp.title = _strip_text(exp.title)
        exp.company = _strip_text(exp.company)
        exp.location = _strip_text(exp.location)
        exp.start_date = _strip_text(exp.start_date)
        exp.end_date = _strip_text(exp.end_date)
        exp.bullets = [b.strip() for b in exp.bullets if b and b.strip()]

    for proj in resume.projects:
        proj.name = _strip_text(proj.name)
        proj.role = _strip_text(proj.role)
        proj.semester = _strip_text(proj.semester)
        proj.bullets = [b.strip() for b in proj.bullets if b and b.strip()]

    for lead in resume.leadership:
        lead.organization = _strip_text(lead.organization)
        lead.role = _strip_text(lead.role)
        lead.location = _strip_text(lead.location)
        lead.start_date = _strip_text(lead.start_date)
        lead.end_date = _strip_text(lead.end_date)
        lead.bullets = [b.strip() for b in lead.bullets if b and b.strip()]

    for vol in resume.volunteer_work:
        vol.organization = _strip_text(vol.organization)
        vol.role = _strip_text(vol.role)
        vol.location = _strip_text(vol.location)
        vol.start_date = _strip_text(vol.start_date)
        vol.end_date = _strip_text(vol.end_date)
        vol.bullets = [b.strip() for b in vol.bullets if b and b.strip()]

    for edu in resume.education:
        edu.school = _strip_text(edu.school)
        edu.degree = _strip_text(edu.degree)
        edu.major = _strip_text(edu.major)
        edu.graduation_date = _strip_text(edu.graduation_date)
        edu.gpa = _strip_text(edu.gpa)
        edu.location = _strip_text(edu.location)
        edu.scholarships = _strip_text(edu.scholarships)
        edu.relevant_coursework = _strip_text(edu.relevant_coursework)

    if resume.additional_info:
        resume.additional_info.computer_skills = _strip_text(resume.additional_info.computer_skills)
        resume.additional_info.technical_skills = _strip_text(resume.additional_info.technical_skills)
        resume.additional_info.work_eligibility = _strip_text(resume.additional_info.work_eligibility)
        resume.additional_info.other = _strip_text(resume.additional_info.other)
        resume.additional_info.certifications = [c.strip() for c in resume.additional_info.certifications if c and c.strip()]
        resume.additional_info.languages = [l.strip() for l in resume.additional_info.languages if l and l.strip()]
        resume.additional_info.professional_memberships = [
            m.strip() for m in resume.additional_info.professional_memberships if m and m.strip()
        ]

    return resume


async def _generate_headline_summary_if_missing(resume: Resume) -> Resume:
    """Use LLM only to fill headline/summary when absent and space allows."""
    needs_headline = not resume.headline
    needs_summary = not resume.summary

    if not needs_headline and not needs_summary:
        return resume

    resume_json = json.loads(resume.model_dump_json())
    generated = await generate_headline_summary(resume_json)

    if needs_headline and generated.get("headline"):
        resume.headline = generated["headline"]

    if needs_summary and generated.get("summary"):
        resume.summary = generated["summary"]

    return resume


async def reformat_resume(resume: Resume) -> Resume:
    """
    Deterministic reformatting:
    - Normalize spacing/strings
    - Preserve bullets; no rewriting
    - Drop headline/summary when compact/full
    - Add headline/summary ONLY when missing and resume is not compact
    """
    resume = _trim_resume_strings(resume)
    resume.compact_mode = compute_compact_mode(resume)

    if resume.compact_mode:
        resume = conditionally_remove_headline_summary(resume)
    else:
        resume = await _generate_headline_summary_if_missing(resume)

    # Format skills (tools stay as-is, concept phrases title-cased)
    resume.skills = format_skills_list(resume.skills)

    return resume

