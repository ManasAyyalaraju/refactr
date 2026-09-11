import hashlib
import re
from typing import List, Optional, Tuple
from pydantic import BaseModel
from core.config import settings
from models.job_models import JobDescription
from services.llm_client import client, _extract_parsed


NON_SKILL_PATTERNS = [
    r"\b\d+\s*(\+)?\s*(years|year|yrs)\b",
    r"\bexperience\b",
    r"\bdegree\b",
    r"\bbachelor",
    r"\bmaster",
    r"\bph\.?d",
    r"\bself[-\s]?starter\b",
    r"\bmotivated\b",
    r"\bability to\b",
    r"\bstrong\b",
    r"\bcustomer service\b",
    r"\bcommunication\b",
    r"\binteract with vendors\b",
    r"\borganized\b",
]


def _filter_concrete_skills(skills: List[str]) -> List[str]:
    filtered: List[str] = []
    seen = set()

    for skill in skills:
        cleaned = skill.strip()
        if not cleaned:
            continue

        lowered = cleaned.lower()
        if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in NON_SKILL_PATTERNS):
            continue

        if lowered not in seen:
            filtered.append(cleaned)
            seen.add(lowered)

    return filtered


class _ParsedJobFields(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    must_have_skills: List[str] = []
    nice_to_have_skills: List[str] = []
    responsibilities: List[str] = []
    keywords: List[str] = []


class _JDWithDomain(BaseModel):
    job: _ParsedJobFields
    industry: str
    sub_domain: str
    confidence: str


# Ephemeral, in-process cache (no TTL, cleared on restart) so tailoring the
# same JD against multiple resumes - or a retry - skips a full LLM round trip.
# Keyed on a hash of the normalized JD text, not a title prefix (the previous
# cache's actual bug: two different JDs sharing a title prefix would
# incorrectly share a domain classification).
_jd_cache: dict = {}

# Up to this many extra attempts (beyond the first) while extraction stays
# suspiciously sparse on a substantive JD. Each is an independent LLM sample,
# so this bounds cost/latency while reducing - not eliminating - the odds
# every attempt lands on an unlucky under-extraction.
MAX_EXTRACTION_RETRIES = 2


def _cache_key(text: str) -> str:
    normalized = " ".join(text.split()).strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


async def _call_and_parse(prompt: str) -> _JDWithDomain:
    response = await client.chat.completions.parse(
        model=settings.openai_model_fast,
        messages=[{"role": "user", "content": prompt}],
        response_format=_JDWithDomain,
        temperature=0,
    )
    return _extract_parsed(response.choices[0].message)


def _clean_job_fields(parsed: _JDWithDomain) -> dict:
    job_fields = parsed.job.model_dump()
    job_fields["must_have_skills"] = _filter_concrete_skills(job_fields.get("must_have_skills", []))
    job_fields["nice_to_have_skills"] = _filter_concrete_skills(job_fields.get("nice_to_have_skills", []))
    return job_fields


async def parse_job_description_from_text(text: str) -> Tuple[JobDescription, dict]:
    """
    Use the LLM to convert raw JD text into a structured JobDescription,
    plus classify its industry/sub-domain in the same call (previously a
    separate round trip chained onto the tailoring call's critical path).

    Returns (JobDescription, domain_info) where domain_info is
    {"industry", "sub_domain", "confidence"}.
    """
    key = _cache_key(text)
    if key in _jd_cache:
        return _jd_cache[key]

    if not client:
        raise RuntimeError("OpenAI client not configured - OPENAI_API_KEY is missing.")

    prompt = f"""
You are a job description parser and classifier.

TASK 1 - Extract structured fields from the job description text:
- "title": job title
- "company": company name if present
- "must_have_skills": Concrete tools/software/platforms/certifications/methodologies explicitly stated as required
- "nice_to_have_skills": Same kind of concrete skills that are preferred/bonus
- "responsibilities": key responsibilities (optional)
- "keywords": Important industry terms, methodologies, or concepts for ATS matching

Rules:
- Extract ONLY what appears in the text. Omit a field (leave it empty) if it's missing.
- Do NOT classify education requirements, years of experience, tenure, personality traits (self-starter, motivated, organized), or generic ability/communication/customer-service/vendor interaction statements as skills. Those may remain as keywords/responsibilities if present.
- Extract skills from ANY domain (tech, healthcare, finance, marketing, etc.) but keep them concrete.
- **Pull skill names out of qualifying phrases, don't discard the whole sentence.** A concrete tool/technology/methodology named inside phrases like "working knowledge of X", "exposure to Y", "understanding of Z", "familiarity with W", "experience with V" is still a real skill to extract - only the qualifying language is soft, not the named skill itself. A single sentence often contains skills at BOTH priority levels: e.g. "Working knowledge of SQL; exposure to Python, Alteryx, and Excel is a plus" must produce must_have_skills: ["SQL"] AND nice_to_have_skills: ["Python", "Alteryx", "Excel"] from that one sentence, not just one or the other.
- Similarly, "Basic understanding of data validation, reconciliation, and data quality practices" should extract "data validation", "reconciliation", and "data quality" as concrete methodologies - the word "basic" softens the requirement level, it doesn't disqualify the terms as skills.
- When in doubt about a specific named tool, technology, or methodology, include it rather than omit it - err toward extracting too much concrete detail rather than too little.

TASK 2 - Classify the role's industry and sub-domain:

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
- UX/UI / Product Design
- Forward Deployed Engineering

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

Confidence levels for the classification:
- "high": Clear indicators, specific role type
- "medium": Some indicators, but could be multiple domains
- "low": Unclear or very general role

JOB DESCRIPTION TEXT:
\"\"\"{text}\"\"\"
"""

    parsed = await _call_and_parse(prompt)
    job_fields = _clean_job_fields(parsed)
    total = len(job_fields["must_have_skills"]) + len(job_fields["nice_to_have_skills"])

    # temperature=0 reduces but doesn't eliminate run-to-run variance - on a
    # JD long enough to obviously contain several concrete skills, a result
    # with fewer than 2 total extracted is more likely an unlucky sample than
    # a genuinely skill-less posting. Retry (each an independent sample) while
    # it stays sparse, keeping whichever attempt did best. Short JDs never
    # enter this loop - a sparse result there is plausibly just correct.
    retry_prompt = prompt + (
        "\n\nNOTE: A previous pass over this same text under-extracted skills. "
        "Re-read carefully for any concrete tool, technology, or methodology named "
        "anywhere in the text, including inside qualifying phrases - do not return "
        "empty or near-empty skill lists for a substantive job description."
    )
    retries = 0
    while total < 2 and len(text) > 200 and retries < MAX_EXTRACTION_RETRIES:
        retries += 1
        candidate_parsed = await _call_and_parse(retry_prompt)
        candidate_fields = _clean_job_fields(candidate_parsed)
        candidate_total = len(candidate_fields["must_have_skills"]) + len(candidate_fields["nice_to_have_skills"])
        if candidate_total > total:
            parsed, job_fields, total = candidate_parsed, candidate_fields, candidate_total

    # raw_text is populated from the input directly rather than asked of the
    # model - there's no reason to spend output tokens/latency having it copy
    # back text we already have.
    jd_obj = JobDescription(raw_text=text, **job_fields)

    domain_info = {
        "industry": parsed.industry or "General / Hybrid",
        "sub_domain": parsed.sub_domain or "General Business",
        "confidence": parsed.confidence or "medium",
    }

    result = (jd_obj, domain_info)

    # Don't let a result that's still sparse after exhausting retries get
    # stuck in the cache - the next request against this same JD text gets a
    # fresh shot instead of permanently inheriting a bad sample.
    still_sparse = total < 2 and len(text) > 200
    if still_sparse:
        return result
    _jd_cache[key] = result
    return result
