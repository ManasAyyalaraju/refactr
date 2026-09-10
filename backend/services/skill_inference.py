"""
Infer skills a resume's owner plausibly has but didn't explicitly list -
computed once at reformat/save time, surfaced later during tailoring as
opt-in suggestions the candidate can confirm (never silently added).

Two-step, both on the fast model tier:
1. Classify the resume's own domain (same taxonomy as job_parser.py's JD
   classifier, grounded in the resume's actual titles/companies/bullets).
2. Suggest concrete skills, grounded in BOTH the resume's real content and
   the matched domain's curated guidance (domain_prompts.py) - not free
   association. domain_prompts.py's skill_priorities aren't reliably literal
   skill names (e.g. Software Engineering's "high" tier is ["Programming
   languages", "Frameworks", ...] - abstract categories, not concrete
   skills), so it's used as grounding context for one small LLM call rather
   than a direct lookup table.
"""
from typing import List
from pydantic import BaseModel
from core.config import settings
from models.resume_models import Resume
from services.domain_prompts import get_domain_prompt, format_domain_guidance
from services.llm_client import client, _extract_parsed


class _ResumeDomain(BaseModel):
    industry: str
    sub_domain: str
    confidence: str


class _SuggestedSkills(BaseModel):
    skills: List[str]


_FALLBACK_DOMAIN = {"industry": "General / Hybrid", "sub_domain": "General Business", "confidence": "low"}


def _resume_background_text(resume: Resume) -> str:
    """Condense a resume's headline/summary/education/titles/companies/
    bullets/skills/certifications into plain text, for prompts that don't
    need the full JSON structure inline.

    Headline, summary, education major, and certifications are often the
    *strongest* domain signal on a resume - especially for candidates with
    little or no work experience, where experience/project bullets alone can
    emphasize an activity (e.g. "led workshops") over its actual subject
    matter (e.g. cybersecurity), misleading domain classification toward the
    activity's field instead of the candidate's real one.
    """
    lines: List[str] = []
    if resume.headline:
        lines.append(resume.headline)
    if resume.summary:
        lines.append(resume.summary)
    for edu in resume.education:
        if edu.major:
            lines.append(f"{edu.degree} in {edu.major}" if edu.degree else edu.major)
    for exp in resume.experience:
        lines.append(f"{exp.title} at {exp.company}")
        lines.extend(exp.bullets)
    for proj in resume.projects:
        if proj.role:
            lines.append(proj.role)
        lines.extend(proj.bullets)
    if resume.skills:
        lines.append("Listed skills: " + ", ".join(resume.skills))
    if resume.additional_info and resume.additional_info.certifications:
        lines.append("Certifications: " + ", ".join(resume.additional_info.certifications))
    return "\n".join(lines)


def _existing_skill_set(resume: Resume) -> set:
    existing = {s.strip().lower() for s in resume.skills}
    for cat in resume.technical_skills:
        existing.update(i.strip().lower() for i in cat.items)
    return existing


async def classify_resume_domain(resume: Resume) -> dict:
    """
    Classify which industry/sub-domain a resume's background belongs to -
    same taxonomy as job_parser.py's JD classifier, grounded in the resume's
    own titles/companies/bullets/skills instead of JD text.
    """
    if not client:
        return dict(_FALLBACK_DOMAIN)

    background = _resume_background_text(resume)
    if not background.strip():
        return dict(_FALLBACK_DOMAIN)

    prompt = f"""
You are a career-background classifier. Based on this person's work/project history and skills, classify what industry and sub-domain their professional background belongs to.

INDUSTRIES:
- Technology
- Finance
- Healthcare
- Marketing
- Education
- Operations
- Consulting
- General / Hybrid

TECHNOLOGY SUB-DOMAINS:
- Software Engineering (SWE)
- Data Analyst / Business Intelligence
- Analytics Engineer / Data Engineering
- Machine Learning / AI / Data Science
- Cloud / DevOps
- Frontend Development
- Backend Development
- Full-Stack Development
- Mobile Development
- QA / Testing

FINANCE SUB-DOMAINS:
- Commercial Banking
- Investment Banking
- Corporate Finance
- Risk Management
- Financial Analysis
- Accounting
- Wealth Management

HEALTHCARE SUB-DOMAINS:
- Clinical (Nursing, Physician, etc.)
- Healthcare Administration
- Medical Research
- Public Health
- Healthcare IT

MARKETING SUB-DOMAINS:
- Digital Marketing
- Content Marketing
- Brand Management
- Marketing Analytics
- Product Marketing

EDUCATION SUB-DOMAINS:
- Teaching (K-12, Higher Ed)
- Educational Administration
- Curriculum Development
- Educational Technology

OPERATIONS SUB-DOMAINS:
- Operations Management
- Supply Chain
- Process Improvement
- Quality Assurance

CONSULTING SUB-DOMAINS:
- Management Consulting
- Technology Consulting
- Financial Consulting

GENERAL / HYBRID:
- Project Management
- Business Analysis
- General Business

Confidence levels:
- "high": Clear, consistent indicators across multiple entries
- "medium": Some indicators, but could fit multiple domains
- "low": Sparse or ambiguous background

PERSON'S BACKGROUND:
\"\"\"{background}\"\"\"
"""
    try:
        response = await client.chat.completions.parse(
            model=settings.openai_model_fast,
            messages=[{"role": "user", "content": prompt}],
            response_format=_ResumeDomain,
            temperature=0,
        )
        parsed = _extract_parsed(response.choices[0].message)
        return {
            "industry": parsed.industry or _FALLBACK_DOMAIN["industry"],
            "sub_domain": parsed.sub_domain or _FALLBACK_DOMAIN["sub_domain"],
            "confidence": parsed.confidence or _FALLBACK_DOMAIN["confidence"],
        }
    except Exception:
        return dict(_FALLBACK_DOMAIN)


async def suggest_plausible_skills(resume: Resume, domain_info: dict) -> List[str]:
    """
    Suggest concrete, plausible-but-unlisted skills for this resume, grounded
    in both the resume's own actual content and the matched domain's curated
    guidance - never free-associated. Fails safe to an empty list on any
    domain-coverage miss (domain_prompts.py doesn't cover every sub-domain)
    or missing client, rather than guessing.
    """
    if not client:
        return []

    entry = get_domain_prompt(domain_info.get("industry", ""), domain_info.get("sub_domain", ""))
    if not entry:
        return []

    background = _resume_background_text(resume)
    if not background.strip():
        return []

    existing = _existing_skill_set(resume)
    guidance = format_domain_guidance(entry)

    prompt = f"""
You are helping identify skills a candidate plausibly has but didn't list on their resume.

DOMAIN GUIDANCE for {domain_info.get("industry")} > {domain_info.get("sub_domain")}:
{guidance}

CANDIDATE'S ACTUAL BACKGROUND:
\"\"\"{background}\"\"\"

CANDIDATE'S ALREADY-LISTED SKILLS (do not repeat any of these):
{sorted(existing)}

Suggest up to 15 concrete, specific tools/technologies/methodologies/certifications this
candidate plausibly knows given their actual background and the domain guidance above,
but did NOT list explicitly. Two categories both count:
1. Specific to THIS candidate's particular background (not just generic to the broad
   domain) - e.g. a specific tool implied by the exact technologies in their bullets.
2. Near-universal baseline tools that someone demonstrating this level of technical
   sophistication has almost certainly picked up along the way, even if not unique to
   their specialization (e.g. Excel, command-line/terminal usage, Git, basic scripting) -
   include these when the candidate's overall skill level genuinely implies familiarity,
   not by default for every resume regardless of what it shows.
Rules:
- Never suggest something contradicted by or unrelated to their actual experience.
- Each suggestion must be a concrete, nameable thing (e.g. "Excel", "Docker",
  "AWS Certified Cloud Practitioner") - never a vague category (e.g. "Programming
  languages", "Certifications", "Cloud platforms").
- Do NOT reach for generic role-boilerplate (e.g. "Agile project management", "CI/CD
  practices", "RESTful APIs") just to fill the list - only include it if something in
  their actual bullets specifically implies it, not just because it's common for their
  general field.
- If you can't confidently suggest 15 things grounded in their actual background, return
  fewer rather than padding the list with weaker guesses.
"""
    try:
        response = await client.chat.completions.parse(
            model=settings.openai_model_fast,
            messages=[{"role": "user", "content": prompt}],
            response_format=_SuggestedSkills,
            temperature=0.2,
        )
        parsed = _extract_parsed(response.choices[0].message)
        return [s.strip() for s in parsed.skills if s.strip() and s.strip().lower() not in existing]
    except Exception:
        return []


async def infer_plausible_skills_for_resume(resume: Resume) -> List[str]:
    """Full pipeline: classify domain, then suggest concrete plausible skills."""
    domain_info = await classify_resume_domain(resume)
    return await suggest_plausible_skills(resume, domain_info)
