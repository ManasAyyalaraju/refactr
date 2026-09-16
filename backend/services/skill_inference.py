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

Suggestions come back pre-split into {"tools": [...], "methodologies": [...]}
(suggest_plausible_skills_grouped) - a tool being a specific named
software/platform/language/certification, a methodology being a technique
or process (even one that sounds technical). This split is domain-agnostic
by construction: it's a structural distinction, not a technology-specific
one, so it applies the same way to a nurse's tools (Epic EHR) vs protocols
(Patient Triage) as to a data analyst's tools (SQL) vs techniques
(Statistical Analysis). The picker UI still shows one flat, undifferentiated
list to confirm from - the split only matters for what happens after
confirmation (tailor_engine.tailor_resume routes tool skills to Technical
Skills, methodology skills into bullet wording).
"""
import json
import logging
from typing import List
from pydantic import BaseModel
from core.config import settings
from models.resume_models import Resume
from services.domain_prompts import get_domain_prompt, format_domain_guidance
from services.llm_client import client, _extract_parsed
from services.bullet_verifier import _contains_skill

logger = logging.getLogger(__name__)


class _ResumeDomain(BaseModel):
    industry: str
    sub_domain: str
    confidence: str


class _SuggestedSkillsGrouped(BaseModel):
    tools: List[str]
    methodologies: List[str]


class _SkillMatch(BaseModel):
    jd_skill: str
    matched_candidate_skills: List[str]


class _SkillMatches(BaseModel):
    matches: List[_SkillMatch]


_FALLBACK_DOMAIN = {"industry": "General / Hybrid", "sub_domain": "General Business", "confidence": "low"}

# Shared across both suggestion passes so every inferred skill reads as one
# consistent style, instead of each entry free-forming its own format (e.g.
# "DCF (Discounted Cash Flow) modeling" next to "Financial statement
# analysis" next to "Financial reporting standards (GAAP/IFRS)" - three
# different conventions for essentially the same kind of entry).
_FORMATTING_RULES = """FORMATTING (apply to every suggestion, no exceptions):
- Title Case, short noun phrase (2-5 words) - exactly how it would read on a resume's
  own skills line.
- Never use a parenthetical to spell out, define, or exemplify a term - each suggestion
  is either the acronym/short name OR the full name, never both. Pick whichever a
  practitioner would actually write on their own resume:
  - Well-known acronym alone: "DCF Modeling", "LBO Modeling", "M&A Analysis", "SWOT
    Analysis", "PEST Analysis" - NOT "DCF (Discounted Cash Flow) Modeling".
  - Full name alone when there's no standard short form: "Comparable Company Analysis",
    "Financial Statement Analysis".
  - A specific named tool/certification is not an acronym to expand: "Excel", "AWS
    Certified Cloud Practitioner".
"""


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
    if resume.additional_info and resume.additional_info.certifications:
        existing.update(c.strip().lower() for c in resume.additional_info.certifications)
    return existing


def _all_bullet_text(resume: Resume) -> str:
    """Every experience and project bullet's raw text, concatenated."""
    parts: List[str] = []
    for exp in resume.experience:
        parts.extend(exp.bullets)
    for proj in resume.projects:
        parts.extend(proj.bullets)
    return " ".join(parts)


def _drop_already_mentioned_in_bullets(result: dict, resume: Resume) -> dict:
    """
    Deterministic final filter: drop any suggestion that's already
    literally named in an experience/project bullet's own text, even
    though it's absent from resume.skills/technical_skills/certifications
    (the only fields _existing_skill_set checks). A tool named only inline
    in a bullet - e.g. "...achieving 85.7% recall using XGBoost and SMOTE"
    - reads as truthfully already-claimed, not a new plausible suggestion,
    even though the model sees this exact bullet text as background
    context and still doesn't reliably avoid re-suggesting it on its own
    (observed directly: XGBoost and SMOTE, both named in a real resume's
    own bullet, were suggested anyway).
    """
    bullet_text = _all_bullet_text(resume)
    if not bullet_text:
        return result
    return {
        "tools": [s for s in result["tools"] if not _contains_skill(bullet_text, s)],
        "methodologies": [s for s in result["methodologies"] if not _contains_skill(bullet_text, s)],
    }


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
        logger.exception("classify_resume_domain failed, falling back to default domain")
        return dict(_FALLBACK_DOMAIN)


# Shared, deliberately narrow TOOLS definition - reused by both the grounded
# and fallback grouped passes below. First version of this prompt defined
# TOOLS loosely enough that the model filed "ETL Processes", "KPI
# Development", "Metrics Analysis" (all processes/techniques, not named
# tools) under TOOLS anyway - the same failure mode llm_client.py's
# classify_confirmed_skills hit and fixed with this same explicit,
# example-anchored "when in doubt, it's a methodology" wording. Keeping the
# two definitions in sync matters: this pass and that one draw the same
# boundary at two different points in the pipeline (suggestion time here,
# confirm time there).
_TOOL_VS_METHODOLOGY_DEFINITION = """1. TOOLS: ONLY a REAL, ACTUALLY-EXISTING named software product, platform, instrument,
   programming/query language, or certification - something a candidate would list as a
   standalone keyword because it is a genuine product/brand name (e.g. "Tableau", "Epic EHR",
   "Bloomberg Terminal", "Python", "AWS Certified Cloud Practitioner"). Three kinds of tools all
   count, and all are worth actively looking for - bias toward including a plausible real tool
   rather than omitting it, since every suggestion here is opt-in: the candidate reviews and
   actively confirms each one before it's ever used, so a suggestion that turns out not to apply
   costs nothing (they simply don't pick it), while a genuinely-known tool that's never
   suggested is a missed opportunity they never get to confirm:
   a. Specific to THIS candidate's particular background - a tool implied by the exact
      technologies, systems, or platforms named in their bullets.
   b. Near-universal baseline tools that someone demonstrating this level of sophistication in
      this domain has almost certainly picked up along the way, even if not unique to their
      specialization (e.g. Excel, Git, command-line/terminal usage for a technical background;
      Microsoft Office, email/calendar platforms for a business background).
   c. Commonly-paired or adjacent tools within this domain/tech stack that someone with this
      exact background plausibly has real exposure to, even without a specific bullet naming
      them directly - e.g. a candidate who names pandas and scikit-learn for ML work plausibly
      also knows NumPy and Jupyter; a candidate doing SQL-heavy analytics work plausibly has
      touched at least one BI tool even if unnamed. This is a real, reasoned inference from their
      actual stack and domain, not a free-associated guess unrelated to their background.
   The one thing that never changes regardless of how broadly you're looking: NEVER invent a
   generic placeholder name by bolting "Software"/"Tool"/"Platform"/"System" onto a concept,
   technique, or methodology - e.g. "DCF Modeling Software", "LBO Modeling Software", "M&A Deal
   Management Software", "Financial Modeling Software" are NOT real products and must never be
   suggested; if you can't name an actual, specific, existing product for a technique like "DCF
   Modeling", that technique belongs ONLY in methodologies below, not disguised as a fake tool.
   This rule is about REAL vs INVENTED names, not about how confident you are that the candidate
   uses it - broaden which real tools you suggest, never invent one that doesn't exist.
2. METHODOLOGIES: everything else - a technique, practice, or process commonly applied using
   those tools and within this domain, something that reads better as part of a sentence
   describing an accomplishment than as a standalone keyword. This includes terms that SOUND
   technical but name a process rather than a specific tool, e.g. "Statistical Analysis", "KPI
   Development", "ETL Processes", "Data Validation", "Patient Triage Protocols", "DCF Modeling",
   "A/B Testing", "HIPAA Compliance Auditing" - none of these are a named tool or language, so
   none of them are TOOLS even though they sound technical. When in doubt whether something is a
   specific tool/language or a general practice, classify it as a METHODOLOGY - the TOOLS bucket
   should stay narrow in WHAT COUNTS as a tool, even though you should actively look for more of
   them (both kinds above). Ground methodologies in BOTH the candidate's background and the tools
   you're suggesting/they already have - a methodology should be something someone using those
   tools in this domain would plausibly practice, not a generic guess."""

# Soft targets for suggest_plausible_skills_grouped's two buckets - a
# shared ceiling (never suggest more, even for a rich background) and a
# floor per bucket the prompt aims for but doesn't force: a thin resume
# that only genuinely supports 3 tools and 2 methodologies should get
# exactly that, not padded with weak guesses to hit either floor. TOOLS
# gets a floor matching the ceiling - tools kept coming back sparse in
# practice (the model tends to find methodologies more readily than
# concrete tools), and since every suggestion is opt-in (the candidate
# actively confirms each one - see _TOOL_VS_METHODOLOGY_DEFINITION), an
# unconfirmed-but-plausible tool costs nothing, while an unsuggested real
# one is a missed chance to confirm it. The "never invent a fake product
# name" rule is a separate, still-strict guard against fabrication - this
# floor only affects how broadly real tools are searched for.
GROUPED_SKILLS_CEILING = 10
TOOLS_SOFT_FLOOR = 10
METHODOLOGIES_SOFT_FLOOR = 6


def _dedupe_grouped(tools: List[str], methodologies: List[str], existing: set) -> dict:
    """
    Trim each list to the ceiling, drop anything already on the resume or
    duplicated across both buckets (a tool accidentally also listed as a
    methodology), and cap total output - shared cleanup for both the
    grounded and fallback grouped passes below.
    """
    seen = set(existing)
    clean_tools, clean_methodologies = [], []
    for s in tools:
        s = s.strip()
        if s and s.lower() not in seen:
            clean_tools.append(s)
            seen.add(s.lower())
    for s in methodologies:
        s = s.strip()
        if s and s.lower() not in seen:
            clean_methodologies.append(s)
            seen.add(s.lower())
    return {
        "tools": clean_tools[:GROUPED_SKILLS_CEILING],
        "methodologies": clean_methodologies[:GROUPED_SKILLS_CEILING],
    }


async def _suggest_grouped_skills_grounded(
    background: str, existing: set, domain_info: dict, entry: dict
) -> dict:
    """
    Grouped counterpart to _suggest_grounded_skills: same domain-grounded
    reasoning (curated domain_prompts.py guidance for this industry/sub-
    domain), but splits the result into TOOLS (specific named software,
    platforms, languages, or certifications - a keyword a candidate would
    list standalone) vs METHODOLOGIES (techniques, practices, or processes
    commonly applied using those tools and in this domain - something that
    reads better woven into a bullet than as a standalone keyword).

    Domain-agnostic by construction: the tool/methodology split is a
    structural distinction, not a technology-specific one - a healthcare
    candidate's tools might be "Epic EHR"/"Cerner" against methodologies
    like "Patient Triage Protocols"/"HIPAA Compliance Auditing", exactly
    the same shape as a data analyst's Tableau/SQL against Statistical
    Analysis/KPI Development.
    """
    guidance = format_domain_guidance(entry)

    prompt = f"""
You are helping identify skills a candidate plausibly has but didn't list on their resume.

DOMAIN GUIDANCE for {domain_info.get("industry")} > {domain_info.get("sub_domain")}:
{guidance}

CANDIDATE'S ACTUAL BACKGROUND:
\"\"\"{background}\"\"\"

CANDIDATE'S ALREADY-LISTED SKILLS (do not repeat any of these):
{sorted(existing)}

Suggest plausible skills this candidate has given their actual background and the domain
guidance above, but did NOT list explicitly - split into two groups:

{_TOOL_VS_METHODOLOGY_DEFINITION}

Aim for up to {GROUPED_SKILLS_CEILING} of each. For TOOLS specifically, push yourself to reach at
least {TOOLS_SOFT_FLOOR} - actively look for all three kinds described above (candidate-specific,
near-universal baseline, AND commonly-paired/adjacent) before settling for a short list; tools
are easy to under-suggest compared to methodologies, and since confirmation is opt-in, err toward
including a real, plausible tool rather than leaving it out. For METHODOLOGIES, aim for at least
{METHODOLOGIES_SOFT_FLOOR}. The one thing that's never negotiable regardless of these targets:
every TOOL must be a real, actually-existing product - never invent a placeholder name just to
hit a number (see above). A shorter list of entirely real tools always beats a longer one with
even one invented name.

Rules:
- Never suggest something contradicted by or unrelated to their actual experience.
- Each suggestion must be a concrete, nameable thing - never a vague category (e.g.
  "Programming languages", "Certifications", "Cloud platforms", "Analytical Techniques") and
  never an invented placeholder product name like "DCF Modeling Software" or "M&A Deal
  Management Software" - a TOOL must be a real, actually-existing product/brand name.
- Do NOT reach for generic role-boilerplate just to fill the lists - only include something if
  their actual background specifically implies it.
- A given item belongs in exactly one list, never both.

{_FORMATTING_RULES}
"""
    try:
        response = await client.chat.completions.parse(
            model=settings.openai_model_classification,
            messages=[{"role": "user", "content": prompt}],
            response_format=_SuggestedSkillsGrouped,
            temperature=0.2,
        )
        parsed = _extract_parsed(response.choices[0].message)
        return _dedupe_grouped(parsed.tools, parsed.methodologies, existing)
    except Exception:
        logger.exception("_suggest_grouped_skills_grounded failed")
        return {"tools": [], "methodologies": []}


async def _suggest_grouped_skills_fallback(background: str, existing: set) -> dict:
    """
    Grouped counterpart to _suggest_fallback_skills - same last-resort,
    no-curated-guidance reasoning, used only when the grounded pass comes
    back with nothing in either bucket. Aims lower than the grounded pass
    (this is deliberately the weaker-confidence path), but keeps the same
    tools/methodologies split and the same "ground it or drop it" rule.
    """
    if not client:
        return {"tools": [], "methodologies": []}

    prompt = f"""
You are helping identify skills a candidate plausibly has but didn't list on their resume.
No curated guidance is available for their exact specialization, so reason directly from
their own background below using your general knowledge of their field.

CANDIDATE'S ACTUAL BACKGROUND:
\"\"\"{background}\"\"\"

CANDIDATE'S ALREADY-LISTED SKILLS (do not repeat any of these):
{sorted(existing)}

Suggest plausible skills this candidate has given their actual background, but did NOT list
explicitly - split into two groups:

{_TOOL_VS_METHODOLOGY_DEFINITION}

Suggest up to 9 TOOLS and up to 5 METHODOLOGIES if well-grounded - push yourself to reach for
tools specifically (all three kinds described above: background-specific, near-universal
baseline, AND commonly-paired/adjacent) before settling for a short list, since tools are easy to
under-suggest and every suggestion here is opt-in - a real, plausible tool costs nothing if the
candidate doesn't confirm it. Return fewer (or none in one group) rather than inventing a
placeholder product name - that rule never loosens, only how broadly you look for real ones.
Each suggestion must be traceable to something specific in their background.

Rules:
- Never suggest something contradicted by or unrelated to their actual experience.
- Each suggestion must be a concrete, nameable thing - never a vague category, and never an
  invented placeholder product name like "DCF Modeling Software" - a TOOL must be a real,
  actually-existing product/brand name.
- A given item belongs in exactly one list, never both.

{_FORMATTING_RULES}
"""
    try:
        response = await client.chat.completions.parse(
            model=settings.openai_model_classification,
            messages=[{"role": "user", "content": prompt}],
            response_format=_SuggestedSkillsGrouped,
            temperature=0.2,
        )
        parsed = _extract_parsed(response.choices[0].message)
        return _dedupe_grouped(parsed.tools, parsed.methodologies, existing)
    except Exception:
        logger.exception("_suggest_grouped_skills_fallback failed")
        return {"tools": [], "methodologies": []}


async def suggest_plausible_skills_grouped(resume: Resume, domain_info: dict) -> dict:
    """
    Suggest concrete, plausible-but-unlisted skills for this resume, split
    into {"tools": [...], "methodologies": [...]} rather than one flat
    list, so a confirmed skill is already tagged tool-vs-methodology at the
    moment it's suggested rather than needing a separate classification
    pass later at tailor time (tailor_engine.classify_confirmed_skills's
    legacy fallback path is now only needed for a base_resumes row saved
    before this split existed).

    "Unlisted" means absent from resume.skills/technical_skills/
    certifications AND absent from the literal text of every experience/
    project bullet (_drop_already_mentioned_in_bullets) - a tool named only
    inline in a bullet (e.g. "...using XGBoost and SMOTE") is still
    truthfully already-claimed, not a new suggestion, even though the
    model sees that same bullet as background context and doesn't reliably
    avoid re-suggesting it on its own.
    """
    if not client:
        return {"tools": [], "methodologies": []}

    background = _resume_background_text(resume)
    if not background.strip():
        return {"tools": [], "methodologies": []}

    existing = _existing_skill_set(resume)

    entry = get_domain_prompt(domain_info.get("industry", ""), domain_info.get("sub_domain", ""))
    if entry:
        grounded = await _suggest_grouped_skills_grounded(background, existing, domain_info, entry)
        if grounded["tools"] or grounded["methodologies"]:
            return _drop_already_mentioned_in_bullets(grounded, resume)

    fallback = await _suggest_grouped_skills_fallback(background, existing)
    return _drop_already_mentioned_in_bullets(fallback, resume)


async def infer_plausible_skills_for_resume(resume: Resume) -> dict:
    """
    Full pipeline: classify domain, then suggest concrete plausible skills,
    pre-split into {"tools": [...], "methodologies": [...]}. Persisted as
    base_resumes.inferred_skills - already tagged tool-vs-methodology at
    this point, so tailor time doesn't need to re-classify a confirmed
    skill from scratch (see tailor_engine.tailor_resume's
    legacy_unclassified_skills param for the fallback path a resume saved
    before this existed still needs).
    """
    domain_info = await classify_resume_domain(resume)
    return await suggest_plausible_skills_grouped(resume, domain_info)


async def match_inferred_skills_to_jd(jd_skills: List[str], candidate_skills: List[str]) -> List[dict]:
    """
    Determine which of a candidate's already-vetted skills concretely
    satisfy which of a job's skill requirements - e.g. "hyperparameter
    tuning" satisfying a JD's "data modeling techniques", or "Python"
    satisfying "high level programming languages". Handles the case where a
    JD phrases a requirement as a broad knowledge area rather than a
    specific tool, which plain string matching can never catch.

    Never proposes a new skill: only matches within candidate_skills (an
    already-grounded list - either a resume's inferred_skills, when
    building the picker, or a user's confirmed selection from it, when
    crediting the compatibility score). Used for score/matching purposes
    only - the abstract jd_skill wording itself is never injected into a
    resume; only the concrete candidate_skills are.

    Returns [{"jd_skill": ..., "matched_candidate_skills": [...]}] - only
    for requirements with a genuine match; skips anything uncertain.
    """
    if not client or not jd_skills or not candidate_skills:
        return []

    prompt = f"""
A candidate has these already-vetted, plausible skills (their truthfulness is already
established - do not question whether these are real):
{json.dumps(candidate_skills)}

A job posting lists these skill requirements, in the job's own words (some are concrete
tools/technologies, some are broader knowledge areas or techniques):
{json.dumps(jd_skills)}

For each job requirement, determine if any of the candidate's skills above are a concrete,
genuine instance or application of that requirement - not just loosely related. For example,
"hyperparameter tuning" and "cross-validation" are concrete instances of "data modeling
techniques". "Python" is a concrete instance of "high level programming languages".

Evaluate every single job requirement above independently, one at a time, in order - do not
let earlier or later requirements in the list draw attention away from any one of them.
Accuracy on requirement 5 of 6 matters exactly as much as requirement 1 of 6.

Rules:
- Only include a job requirement if at least one candidate skill genuinely, concretely
  satisfies it - skip anything uncertain, loosely associative, or a stretch.
- Only reference skills from the candidate's list above verbatim - never invent or reword one.
- Include a requirement even if a candidate skill's wording is only slightly different from it
  (e.g. "Python" satisfies both "Python programming" and "data analysis" satisfies "data
  analytics") - callers of this function already remove anything that's an exact, identically-
  worded match before calling it, so do not skip a requirement just because a candidate skill's
  wording looks similar to it.
"""
    try:
        response = await client.chat.completions.parse(
            model=settings.openai_model_matching,
            messages=[{"role": "user", "content": prompt}],
            response_format=_SkillMatches,
            temperature=0,
        )
        parsed = _extract_parsed(response.choices[0].message)
        candidate_set = {s.lower() for s in candidate_skills}
        results = []
        for m in parsed.matches:
            matched = [s for s in m.matched_candidate_skills if s.lower() in candidate_set]
            if matched:
                results.append({"jd_skill": m.jd_skill, "matched_candidate_skills": matched})
        return results
    except Exception:
        # Silently falling back to [] here means the caller's compatibility
        # score quietly reverts to literal-match-only with zero trace of why
        # (looks identical to "nothing matched") - log it so a transient
        # OpenAI failure (rate limit, timeout, malformed response) is
        # diagnosable instead of indistinguishable from a genuine no-match.
        logger.exception(
            "match_inferred_skills_to_jd failed (jd_skills=%d, candidate_skills=%d)",
            len(jd_skills), len(candidate_skills),
        )
        return []
