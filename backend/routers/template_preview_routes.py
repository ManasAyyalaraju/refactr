from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from models.resume_models import (
    Resume,
    Contact,
    EducationEntry,
    Experience,
    Project,
    TechnicalSkillCategory,
    AdditionalInfo,
)
from services.pdf_writer import render_resume_pdf

router = APIRouter(tags=["Template Preview"])

# Static example resume used purely to demonstrate what the Regular vs
# Technical templates look like. No AI call, no user data involved.
# Identity fields are deliberately generic placeholders (not a real-sounding
# name) so users previewing this alongside their own upload don't mistake it
# for their resume and worry they uploaded the wrong file.
DUMMY_RESUME = Resume(
    name="Your Name",
    contact=Contact(
        email="your.email@example.com",
        phone="(555) 123-4567",
        linkedin="linkedin.com/in/yourname",
        location="Austin, TX",
    ),
    education=[
        EducationEntry(
            school="University of Texas at Austin",
            degree="Bachelor of Science",
            major="Computer Science",
            graduation_date="May 2026",
            location="Austin, TX",
        )
    ],
    technical_skills=[
        TechnicalSkillCategory(label="Computer Languages", items=["Python", "JavaScript", "SQL", "Java"]),
        TechnicalSkillCategory(label="Frameworks & Tools", items=["React", "Node.js", "Git", "Docker"]),
        TechnicalSkillCategory(label="Certifications", items=["AWS Certified Cloud Practitioner"]),
    ],
    experience=[
        Experience(
            title="Software Engineering Intern",
            company="Acme Technologies",
            location="Austin, TX",
            start_date="June 2025",
            end_date="August 2025",
            bullets=[
                "Built and shipped a customer-facing dashboard feature used by 5,000+ active users, improving task completion time by 20%.",
                "Collaborated with a team of 4 engineers to migrate a legacy service to a modern API architecture, reducing average response time by 30%.",
                "Wrote automated tests that increased backend code coverage from 60% to 85%.",
            ],
        )
    ],
    projects=[
        Project(
            name="Campus Event Finder",
            role="Full-Stack Developer",
            semester="Spring 2025",
            bullets=[
                "Developed a full-stack web app helping students discover campus events, reaching 500+ users in the first month.",
                "Implemented search and filtering features using React and a PostgreSQL-backed API.",
            ],
        )
    ],
    skills=["Python", "JavaScript", "SQL", "Java", "React", "Node.js", "Git", "Docker"],
    additional_info=AdditionalInfo(
        languages=["English", "Spanish"],
        work_eligibility="Eligible to work in the U.S. with no restrictions",
    ),
)

# Rendered once per format, then served from memory - the content never changes.
_preview_cache: dict[str, bytes] = {}


@router.get("/templates/preview")
async def get_template_preview(format: str = Query("regular")):
    """
    Returns a sample PDF rendered from a hardcoded example resume, so users
    can see the difference between the Regular and Technical templates
    before choosing one for their own resume.
    """
    normalized = format.lower()
    if normalized not in ("regular", "technical"):
        raise HTTPException(status_code=400, detail="format must be 'regular' or 'technical'")

    if normalized not in _preview_cache:
        pdf_bytes = render_resume_pdf(DUMMY_RESUME, use_technical_skills=(normalized == "technical"))
        _preview_cache[normalized] = pdf_bytes

    return StreamingResponse(
        iter([_preview_cache[normalized]]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{normalized}_template_preview.pdf"'},
    )
