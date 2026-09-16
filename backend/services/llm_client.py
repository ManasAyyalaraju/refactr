import json
from typing import List, Optional
from openai import AsyncOpenAI
from pydantic import BaseModel
from core.config import settings
from models.resume_models import Resume, TechnicalSkillCategory
from services.domain_prompts import get_domain_prompt, format_domain_guidance
from services.bullet_verifier import SPARSE_BULLET_CHAR_TARGET, SPARSE_BULLET_CHAR_CEILING

# Validate API key on import
try:
    settings.validate_api_key()
except ValueError as e:
    import warnings
    warnings.warn(str(e), UserWarning)

client = (
    AsyncOpenAI(api_key=settings.openai_api_key, max_retries=settings.openai_max_retries)
    if settings.openai_api_key
    else None
)


def _extract_parsed(message):
    """Pull the validated structured-output object off a chat completion message,
    raising clearly instead of letting a None/refusal propagate silently."""
    if message.refusal:
        raise RuntimeError(f"Model refused the request: {message.refusal}")
    if message.parsed is None:
        raise RuntimeError("Model returned no parsed structured output.")
    return message.parsed


async def rewrite_resume_sections(resume_json: dict, job_json: dict, domain_info: dict) -> Resume:
    """
    Call the LLM to strongly tailor the resume to any job description:
    - Rewrite summary (if present)
    - Rewrite ALL bullets in experience, projects, and volunteer work
    - Keep the SAME number of bullets per entry
    - Match original bullet lengths character-for-character
    - Adapt to any domain (tech, healthcare, finance, marketing, etc.)

    `domain_info` ({"industry", "sub_domain", "confidence"}) is produced once
    by job_parser.parse_job_description_from_text (merged into the JD-parsing
    call) rather than detected again here.
    """
    if not client:
        raise RuntimeError("OpenAI client not configured - OPENAI_API_KEY is missing.")

    # Calculate original resume structure and bullet lengths
    experience_bullet_counts = [len(exp.get("bullets", [])) for exp in resume_json.get("experience", [])]
    project_bullet_counts = [len(proj.get("bullets", [])) for proj in resume_json.get("projects", [])]
    leadership_bullet_counts = [len(lead.get("bullets", [])) for lead in resume_json.get("leadership", [])]
    volunteer_bullet_counts = [len(vol.get("bullets", [])) for vol in resume_json.get("volunteer_work", [])]

    # Get all bullets with their lengths for the prompt
    bullet_examples = []
    for exp in resume_json.get("experience", []):
        for bullet in exp.get("bullets", []):
            bullet_examples.append(f"Original ({len(bullet)} chars): \"{bullet}\"")
    for proj in resume_json.get("projects", []):
        for bullet in proj.get("bullets", []):
            bullet_examples.append(f"Original ({len(bullet)} chars): \"{bullet}\"")
    for lead in resume_json.get("leadership", []):
        for bullet in lead.get("bullets", []):
            bullet_examples.append(f"Original ({len(bullet)} chars): \"{bullet}\"")

    # Show first 5 as examples
    bullet_examples_str = "\n".join(bullet_examples[:5])

    # Calculate bullet lengths
    all_bullets = []
    for exp in resume_json.get("experience", []):
        all_bullets.extend(exp.get("bullets", []))
    for proj in resume_json.get("projects", []):
        all_bullets.extend(proj.get("bullets", []))
    for lead in resume_json.get("leadership", []):
        all_bullets.extend(lead.get("bullets", []))

    bullet_lengths = [len(bullet) for bullet in all_bullets if bullet]
    avg_bullet_length = sum(bullet_lengths) / len(bullet_lengths) if bullet_lengths else 150

    total_bullets = sum(experience_bullet_counts + project_bullet_counts + leadership_bullet_counts + volunteer_bullet_counts)

    # Use compact_mode from the resume object (already calculated in tailor_engine.py)
    # This determines whether we need tight spacing AND short bullets
    is_compact = resume_json.get("compact_mode", False)

    industry = domain_info.get("industry", "General / Hybrid")
    sub_domain = domain_info.get("sub_domain", "General Business")

    # Prefer a condensed, fixed-size briefing built from domain_prompts.py when
    # this (industry, sub_domain) pair has an entry; otherwise fall back to the
    # plain label (coverage is partial - e.g. Consulting has no entries at all).
    # Deliberately NOT dumping the full emphasis/language_patterns/metrics/
    # skill_priorities/terminology lists here - that was tried before and
    # reverted because the larger prompt measurably slowed generation.
    domain_entry = get_domain_prompt(industry, sub_domain)
    if domain_entry:
        domain_guidance_line = f"INDUSTRY: {industry} > {sub_domain}. {format_domain_guidance(domain_entry)}"
    else:
        domain_guidance_line = f"INDUSTRY: {industry} > {sub_domain}"

    # Build a simple focus string from JD skills
    must = job_json.get("must_have_skills", []) or []
    nice = job_json.get("nice_to_have_skills", []) or []
    focus_skills = ", ".join(must + nice)

    # Build examples and instructions based on resume type
    if is_compact:
        # Adaptive compression target based on original bullet length
        # Don't compress too aggressively - respect user's original content
        if avg_bullet_length >= 200:
            target_range = "170-190 characters"
            compression_note = "Original bullets are very long (200+ chars). Compress them to ~180 chars to save space while preserving key details."
        elif avg_bullet_length >= 170:
            target_range = "150-170 characters"
            compression_note = "Original bullets are moderately long (170-200 chars). Compress them to ~160 chars to fit better on one page."
        else:
            target_range = "130-160 characters"
            compression_note = "Original bullets are already concise. Keep them short at 130-160 chars."

        primary_rule = f"""
=========================================
⚠️ PRIMARY RULE: COMPRESS BULLETS FOR ONE-PAGE FIT ⚠️
=========================================

RESUME TYPE: COMPACT/ONE-PAGE - Need SHORT bullets to fit on one page

ORIGINAL AVERAGE BULLET LENGTH: {avg_bullet_length:.0f} characters
TARGET RANGE: {target_range}

**YOUR PRIMARY JOB:**
Compress bullets to fit on one page while preserving key information.
{compression_note}

**HOW TO COMPRESS BULLETS:**
✅ GOOD: Use concise, powerful action verbs
✅ GOOD: Remove redundant words and filler phrases ("comprehensive", "various", "diverse")
✅ GOOD: Keep core metrics and key technologies
✅ GOOD: Eliminate unnecessary context and explanations
✅ GOOD: Integrate JD keywords by REPLACING verbose descriptions
❌ BAD: Removing important metrics or achievements
❌ BAD: Making bullets too short and losing substance
❌ BAD: Writing bullets that wrap to 3 lines

**Example Compression:**
Original (240 chars): "Spread client financials by meticulously analyzing tax returns, reviewing supporting schedules, and preparing comprehensive income statements, balance sheets, and key financial metrics, which supported thorough valuation and transaction analysis for multiple clients"
✅ Compressed (185 chars): "Analyzed client financials by reviewing tax returns, supporting schedules, and preparing income statements, balance sheets, and key metrics to support valuation and transaction analysis for clients"
"""
        examples_header = f"**COMPACT RESUME - Compress bullets to {target_range}:**"
        example1 = '✅ Good (185 chars): "Analyzed client financials by reviewing tax returns, supporting schedules, and preparing income statements, balance sheets, and key metrics to support valuation and transaction analysis for clients"'
        example2 = '✅ Good (178 chars): "Performed competitor analysis for two client engagements with $10-15M revenue, identifying 8+ comparable companies to benchmark valuations and align pricing expectations for target businesses"'
        headline_summary_instruction = ""
    else:
        primary_rule = f"""
=========================================
⚠️ PRIMARY RULE: TAILOR CONTENT TO THE JOB - EXPAND ONLY WITH TRUTHFUL DETAIL ⚠️
=========================================

RESUME TYPE: SPARSE - tailor bullets to the JD, let them run a bit longer, and ADD/REWRITE a JD-focused headline+summary

**YOUR PRIMARY JOB:**
1. **HEADLINE**: Write or rewrite ONE impactful sentence (50-80 chars) that foregrounds the candidate's JD-relevant strengths
2. **SUMMARY**: Write or rewrite a 2-3 sentence summary (150-250 chars total) highlighting the candidate's truthful strengths most relevant to THIS job
3. **TAILOR BULLETS**: Rework each bullet's wording and emphasis for this JD - target {SPARSE_BULLET_CHAR_TARGET[0]}-{SPARSE_BULLET_CHAR_TARGET[1]} characters (~2 lines), never exceed {SPARSE_BULLET_CHAR_CEILING} characters (~3 lines) - adding only detail that's already true

Page fullness for a sparse resume comes from the headline/summary above,
from letting bullets breathe a bit more (up to 3 lines), and from layout -
NOT from inventing facts that aren't already grounded in the resume.

**HOW TO EXPAND BULLETS (TRUTHFULLY):**
✅ GOOD: Swap in JD-relevant keywords and emphasis the candidate can truthfully claim
✅ GOOD: Sharpen the verb and impact framing of what's already there
✅ GOOD: Spell out technologies, tools, or methods already named elsewhere in the resume
✅ GOOD: Surface a metric or scale already stated elsewhere in the resume, if relevant to this bullet
❌ BAD: Inventing team sizes, geographies, stakeholders, or scope not in the original
❌ BAD: Padding a bullet with vague filler just to add length
"""
        examples_header = "**SPARSE RESUME - expand with real detail, not filler:**"
        example1 = '✅ Good (175 chars): "Coordinated sorting, packaging, and distribution of donated meals and essentials, partnering with local organizations to ensure accurate weekly delivery across the service area"'
        example2 = '✅ Good (160 chars): "Supported technical sales cycles across 10+ national accounts, aligning data integration solutions with client business objectives and priorities"'
        headline_summary_instruction = """
**HEADLINE AND SUMMARY (REQUIRED - WRITE/REWRITE THESE TAILORED TO THIS JOB):**
- **headline**: ONE impactful sentence (50-80 chars) that foregrounds the candidate's strengths most relevant to THIS job
  Example: "Information Systems Student | Cybersecurity Enthusiast | Tech Leader"
- **summary**: 2-3 sentences (150-250 chars total) highlighting the candidate's truthful strengths, skills, and experience most relevant to THIS job description
  Example: "Information Technology student with hands-on experience in cybersecurity education and community impact initiatives. Skilled in WatsonX AI, data analysis, and volunteer leadership. Passionate about leveraging technology to solve real-world challenges in food security and information systems."
- Use ONLY facts already present in the resume - do not invent achievements, employers, or skills to fill these in.
"""

    prompt = f"""
You are an expert resume tailoring assistant. Tailor this resume to the job description.

{primary_rule}

ORIGINAL BULLETS (with character counts):
{bullet_examples_str}
... (showing first 5 bullets as examples)

AVERAGE BULLET LENGTH: {avg_bullet_length:.0f} characters
TOTAL BULLETS: {total_bullets}

=========================================
JOB DESCRIPTION FOCUS
=========================================

TITLE: {job_json.get("title", "N/A")}
{domain_guidance_line}
KEY SKILLS: {focus_skills if focus_skills else "General"}

=========================================
TAILORING RULES
=========================================

1. **KEEP EXACT BULLET COUNT** - Same number of bullets per job/project as original
2. {"**MATCH CHARACTER COUNTS** - Each tailored bullet should be within ±15 chars of original" if is_compact else "**EXPAND WITH TRUTHFUL DETAIL** - Add only detail already grounded in the original bullet or resume; never invent new specifics"}
3. {"**SWAP, DON'T ADD** - Replace generic terms with JD-specific keywords" if is_compact else "**TAILOR, DON'T ADD** - Replace generic terms with JD-specific keywords the candidate can truthfully claim"}
4. **START WITH A STRONG ACTION VERB** - Never open with "Responsible for", "Worked on", "Helped with", or a gerund ("Managing...", "Leading...") as the first word - lead with a specific past-tense action verb
5. **VARY YOUR OPENING VERBS** - Do not start two bullets on the same resume with the same verb; use a different one for each
6. **WHAT, SO WHAT, HOW** - Convey the achievement (what you did), its impact (so what), and briefly how - don't just list a responsibility
7. **QUANTIFY WHEN TRUE** - Include a real number, percentage, or scale already grounded in the original bullet or resume when available; never invent a metric that isn't already there
8. {"**1 LINE PREFERRED, 2 LINES MAX** - Keep each bullet to at most 2 lines; a single concise line is preferred over two" if is_compact else f"**2 LINES PREFERRED, 3 LINES MAX** - Target {SPARSE_BULLET_CHAR_TARGET[0]}-{SPARSE_BULLET_CHAR_TARGET[1]} characters; never exceed {SPARSE_BULLET_CHAR_CEILING} characters"}
9. **PRESERVE STRUCTURE** - Do NOT change job titles, companies, dates, or locations
10. **KEEP METRICS** - Preserve all numbers and percentages from original bullets
11. **STAY TRUTHFUL** - Only use skills from the resume's skills list

{headline_summary_instruction}

**SKILLS AVAILABLE** (use ONLY these):
{resume_json.get("skills", [])}

=========================================
EXAMPLES OF GOOD TAILORING
=========================================

{examples_header}

Original (112 chars): "Developed 5+ IT mobile applications resulting in 15% increase in user engagement and positive ratings"
{example1}

Original (95 chars): "Supported technical sales cycles across 10+ national accounts helping align solutions"
{example2}

=========================================
RESUME AND JOB DATA
=========================================

RESUME JSON:
{json.dumps(resume_json, indent=2)}

JOB DESCRIPTION JSON:
{json.dumps(job_json, indent=2)}
"""

    system_message = (
        f"You are a resume editor specializing in {industry}. Your PRIMARY goal: tailor content "
        f"to the job description while keeping bullet lengths close to the original. Every bullet "
        f"must open with a strong, distinct action verb (never a passive phrase or a gerund), "
        f"convey what was done and its impact, and stay at most 2 lines (1 preferred)."
    )

    response = await client.chat.completions.parse(
        model=settings.openai_model_generate,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ],
        response_format=Resume,
        temperature=0.3,  # Lower temperature for more consistent length matching
    )

    return _extract_parsed(response.choices[0].message)


class _HeadlineSummary(BaseModel):
    headline: Optional[str] = None
    summary: Optional[str] = None


async def generate_headline_summary(resume_json: dict, jd_json: Optional[dict] = None) -> dict:
    """
    Generate ONLY a headline and summary from existing resume content.
    - Do NOT alter bullets or any other fields
    - Keep it concise and truthful to provided data

    jd_json: when given, the headline/summary are written to foreground
    whichever of the candidate's truthful strengths are most relevant to
    this job - same JD-aware framing rewrite_resume_sections' sparse branch
    uses for a resume tailored from the start. Omitted (reformat time, or a
    post-render underfill backfill for an already-compact-flagged tailor
    that had no JD-aware pass to begin with), it's generated from the
    resume alone with no JD framing.
    """
    if not client:
        return {"headline": None, "summary": None}

    system_message = (
        "You are a resume editor. Only produce a short headline and 2-3 sentence "
        "summary using existing resume details. Do not invent facts. Do not rewrite "
        "bullets or any other fields. Keep it concise and professional."
    )

    jd_context = (
        f"""
JOB DESCRIPTION (for framing only - do not copy its wording or invent skills from it):
TITLE: {jd_json.get("title", "N/A")}
KEY SKILLS: {", ".join((jd_json.get("must_have_skills") or []) + (jd_json.get("nice_to_have_skills") or []))}

Foreground whichever of the candidate's truthful strengths above are most relevant to this job.
"""
        if jd_json
        else ""
    )

    prompt = f"""
Resume JSON (truth source):
{json.dumps(resume_json, indent=2)}
{jd_context}
Instructions:
- Use ONLY information present in the resume JSON above (roles, education, skills, bullets)
- No new achievements or skills; do not change wording of bullets
- Keep headline 50-80 characters; summary 2-3 sentences, ~120-220 chars total
- If information is insufficient, return null for that field
"""

    try:
        response = await client.chat.completions.parse(
            model=settings.openai_model_fast,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            response_format=_HeadlineSummary,
            temperature=0.3,
        )
        parsed = _extract_parsed(response.choices[0].message)
        return {
            "headline": parsed.headline or None,
            "summary": parsed.summary or None,
        }
    except Exception:
        return {"headline": None, "summary": None}


class _RevisedBullet(BaseModel):
    bullet: str


async def revise_bullet(
    original_bullet: str,
    tailored_bullet: str,
    unauthorized_terms: List[str],
    jd_json: dict,
) -> str:
    """
    Bounded, single-shot correction: rewrite ONE bullet to remove skills/tools
    flagged by bullet_verifier as unverified, without reintroducing them.

    No internal retry loop - the caller (tailor_engine.tailor_resume) owns the
    retry-once-then-fall-back-to-original semantics. On any failure here, the
    original tailored bullet is returned unchanged so the caller's own
    re-check still catches the violation and can fall back safely.
    """
    if not client:
        return tailored_bullet

    terms_str = ", ".join(unauthorized_terms)
    system_message = (
        "You are a resume editor. Rewrite exactly one bullet point to remove "
        "unverified claims while keeping it accurate, well-written, and close "
        "to the original length."
    )
    prompt = f"""
This tailored bullet mentions skills/tools the candidate's resume does not actually list or use elsewhere: {terms_str}

ORIGINAL BULLET (source of truth): "{original_bullet}"
TAILORED BULLET (needs correction): "{tailored_bullet}"

JOB TITLE: {jd_json.get("title", "N/A")}

Rewrite the bullet to:
- Remove all mention of: {terms_str}
- NOT introduce any other skill/tool not already present in the original bullet
- Keep the same general length and structure as the tailored bullet
- Stay truthful to the original bullet's content

Return the corrected bullet text.
"""

    try:
        response = await client.chat.completions.parse(
            model=settings.openai_model_fast,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            response_format=_RevisedBullet,
            temperature=0.2,
        )
        parsed = _extract_parsed(response.choices[0].message)
        return parsed.bullet.strip() or tailored_bullet
    except Exception:
        return tailored_bullet


async def revise_weak_opener(bullet: str, jd_json: dict) -> str:
    """
    Bounded, single-shot correction: rewrite ONE bullet so it opens with a
    strong action verb instead of a passive/responsibility phrase or a
    gerund, without changing what it actually claims.

    Same no-internal-retry contract as revise_bullet() - on failure, returns
    the bullet unchanged so the caller's own check still sees the violation.
    """
    if not client:
        return bullet

    system_message = (
        "You are a resume editor. Rewrite exactly one bullet point so it "
        "begins with a strong, specific past-tense action verb, without "
        "changing what it actually claims."
    )
    prompt = f"""
This bullet opens weakly - a responsibility phrase like "Responsible for" or "Worked on", or a gerund like "Managing..." - instead of a strong action verb:

BULLET: "{bullet}"

JOB TITLE: {jd_json.get("title", "N/A")}

Rewrite it to:
- Start with a strong, specific past-tense action verb (e.g. "Led", "Built", "Reduced", "Drove")
- Keep the same facts, scope, and any metrics - do not invent new ones
- Keep roughly the same length as the original

Return the corrected bullet text.
"""

    try:
        response = await client.chat.completions.parse(
            model=settings.openai_model_fast,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            response_format=_RevisedBullet,
            temperature=0.2,
        )
        parsed = _extract_parsed(response.choices[0].message)
        return parsed.bullet.strip() or bullet
    except Exception:
        return bullet


async def revise_repeated_verb(bullet: str, used_verbs: List[str], jd_json: dict) -> str:
    """
    Bounded, single-shot correction: rewrite ONE bullet so it opens with a
    verb different from every verb already in use elsewhere on the resume,
    without changing what it actually claims.

    Cross-bullet-aware by construction (`used_verbs` is the caller's
    running set) but each call is single-bullet and single-shot, same
    no-internal-retry contract as revise_bullet() - the caller decides
    whether the result is acceptable and falls back to the original bullet
    if not, rather than looping here.
    """
    if not client:
        return bullet

    used_str = ", ".join(sorted(set(used_verbs))) or "(none)"
    system_message = (
        "You are a resume editor. Rewrite exactly one bullet point so it "
        "opens with an action verb not already used elsewhere on the same "
        "resume, without changing what it actually claims."
    )
    prompt = f"""
This bullet's opening verb is already used by another bullet on the same resume, so it needs a different one:

BULLET: "{bullet}"

VERBS ALREADY IN USE ELSEWHERE ON THIS RESUME (do not start with any of these): {used_str}

JOB TITLE: {jd_json.get("title", "N/A")}

Rewrite it to:
- Start with a strong, specific past-tense action verb NOT in the list above
- Keep the same facts, scope, and any metrics - do not invent new ones
- Keep roughly the same length as the original

Return the corrected bullet text.
"""

    try:
        response = await client.chat.completions.parse(
            model=settings.openai_model_fast,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            response_format=_RevisedBullet,
            temperature=0.2,
        )
        parsed = _extract_parsed(response.choices[0].message)
        return parsed.bullet.strip() or bullet
    except Exception:
        return bullet


async def revise_overlong_bullet(bullet: str, char_ceiling: int, jd_json: dict) -> str:
    """
    Bounded, single-shot correction: shorten ONE bullet to fit under a
    character ceiling (bullet_verifier's calibrated proxy for a line-count
    limit) by tightening language, without cutting any fact, metric, or
    claim it makes.
    """
    if not client:
        return bullet

    system_message = (
        "You are a resume editor. Shorten exactly one bullet point to fit a "
        "character limit by tightening the wording, without cutting any "
        "fact, metric, or claim it makes."
    )
    prompt = f"""
This bullet is too long and needs to be shortened to fit the page:

BULLET ({len(bullet)} chars): "{bullet}"

TARGET: under {char_ceiling} characters

JOB TITLE: {jd_json.get("title", "N/A")}

Rewrite it to:
- Fit under {char_ceiling} characters
- Keep every fact, metric, and claim from the original - only tighten the wording
- Keep the same opening action verb

Return the corrected bullet text.
"""

    try:
        response = await client.chat.completions.parse(
            model=settings.openai_model_fast,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            response_format=_RevisedBullet,
            temperature=0.2,
        )
        parsed = _extract_parsed(response.choices[0].message)
        return parsed.bullet.strip() or bullet
    except Exception:
        return bullet


class _SkillTypeClassification(BaseModel):
    hard_skills: List[str]
    applied_skills: List[str]


async def classify_confirmed_skills(skills: list[str]) -> dict:
    """
    Split a candidate-confirmed skill list (e.g. from the inferred-skills
    picker) into hard/tool skills (belong as Technical Skills keywords -
    "Python", "SQL", "Tableau", "AWS") vs applied/methodology skills
    ("Statistical Analysis", "KPI Development", "Data Validation", "ETL
    Processes") that read better woven into a bullet's own wording than
    listed as a standalone keyword.

    The HARD bucket is deliberately narrow: only a coding/query language or
    a specific named tool/platform - NOT a process, practice, or
    methodology, even one that sounds technical. "ETL Processes" describes
    a general data-engineering practice, not a named tool, so it belongs in
    APPLIED even though it's a data/engineering term.

    Returns {"hard_skills": [...], "applied_skills": [...]} - every input
    skill appears in exactly one list. Falls back to treating everything as
    a hard skill (today's behavior) on any failure, rather than silently
    dropping a confirmed skill.
    """
    if not client or not skills:
        return {"hard_skills": list(skills or []), "applied_skills": []}

    system_message = (
        "You are a resume editor. Classify each given skill as either a HARD skill or an "
        "APPLIED skill.\n"
        "HARD skill: ONLY a coding/query language (e.g. \"Python\", \"SQL\") or a specific "
        "named tool, platform, software, or certification (e.g. \"Tableau\", \"AWS Cloud "
        "Practitioner\", \"Excel\") - something a candidate would list as a standalone keyword.\n"
        "APPLIED skill: everything else - a general analytical practice, technique, process, "
        "or methodology that reads better as part of a sentence describing an accomplishment "
        "than as a standalone keyword. This includes terms that sound technical but name a "
        "PROCESS rather than a specific tool, e.g. \"Statistical Analysis\", \"KPI "
        "Development\", \"Data Validation\", \"ETL Processes\", \"Stakeholder Management\", "
        "\"Agile Methodology\" - none of these are a named tool or language, so none of them "
        "are HARD skills even though they sound technical.\n"
        "When in doubt whether something is a specific tool/language or a general practice, "
        "classify it as APPLIED - the HARD bucket should stay narrow.\n"
        "Every input skill must appear in exactly one of the two lists, unchanged."
    )
    prompt = f"""
Skills to classify:
{json.dumps(list(skills), indent=2)}
"""
    try:
        response = await client.chat.completions.parse(
            model=settings.openai_model_classification,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            response_format=_SkillTypeClassification,
            temperature=0,
        )
        parsed = _extract_parsed(response.choices[0].message)
        hard = [s for s in parsed.hard_skills if s]
        applied = [s for s in parsed.applied_skills if s]

        # Never let a classification failure silently lose a confirmed
        # skill - anything the model omitted from both lists falls back to
        # "hard" (today's behavior), the safer default since it still ends
        # up visible on the resume rather than dropped.
        classified_lower = {s.strip().lower() for s in hard + applied}
        missing = [s for s in skills if s.strip().lower() not in classified_lower]
        hard.extend(missing)

        return {"hard_skills": hard, "applied_skills": applied}
    except Exception:
        return {"hard_skills": list(skills), "applied_skills": []}


class _SkillWeaveResult(BaseModel):
    applicable: bool
    bullet_index: Optional[int] = None
    revised_bullet: Optional[str] = None


async def weave_skill_into_bullet(
    skill: str, bullets: list[str], jd_json: dict, already_woven_indices: Optional[set] = None
) -> Optional[dict]:
    """
    Find the single most contextually plausible bullet (by index into
    `bullets`) that this applied/methodology skill could truthfully have
    been part of, and rewrite that one bullet to naturally weave it in -
    or report the skill isn't a truthful fit for any bullet, so the caller
    can leave it out entirely rather than force it somewhere untrue.

    already_woven_indices: bullet indices a PRIOR call in the same batch
    already wove a skill into. When more than one bullet is a genuinely
    plausible fit, the model is told to prefer one not already on this
    list, so several applied skills don't all pile onto the same bullet by
    default - but this is a tie-breaker only, never a reason to pick a
    worse-fitting bullet just to spread skills out.

    Returns {"bullet_index": int, "revised_bullet": str} or None.
    """
    if not client or not bullets:
        return None

    numbered = "\n".join(f"{i}: \"{b}\"" for i, b in enumerate(bullets))
    already_woven_note = (
        f"\nBullets that already had another skill woven in this pass (prefer avoiding these "
        f"if another bullet is an equally genuine fit - but only as a tie-breaker, never over a "
        f"better-fitting bullet): {sorted(already_woven_indices)}\n"
        if already_woven_indices
        else ""
    )
    system_message = (
        "You are a resume editor. Given a candidate's confirmed skill and their existing "
        "resume bullets, decide whether any ONE bullet plausibly involved that skill based "
        "on what the bullet already describes. If so, rewrite that bullet to naturally "
        "weave the skill into its wording without changing its core facts, metrics, or "
        "length. If no bullet is a truthful, plausible fit, say so - never force the skill "
        "into a bullet it doesn't genuinely relate to."
    )
    prompt = f"""
CONFIRMED SKILL: "{skill}"

JOB TITLE: {jd_json.get("title", "N/A")}

CANDIDATE'S BULLETS (indexed):
{numbered}
{already_woven_note}
Instructions:
- Pick AT MOST ONE bullet index where this skill plausibly applies to the work already described.
- Rewrite only that bullet to weave the skill in naturally - keep its facts, metrics, and
  roughly its length unchanged.
- If none of the bullets are a genuine fit for this skill, set applicable to false and leave
  bullet_index/revised_bullet empty - do not pick the closest option if it isn't a real fit.
- If multiple bullets are equally genuine fits, prefer one not already listed above as having a
  skill woven in - avoid concentrating every skill into a single bullet when better distributed
  placement is just as truthful.
"""
    try:
        response = await client.chat.completions.parse(
            model=settings.openai_model_fast,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            response_format=_SkillWeaveResult,
            temperature=0.2,
        )
        parsed = _extract_parsed(response.choices[0].message)
        if not parsed.applicable or parsed.bullet_index is None or not parsed.revised_bullet:
            return None
        return {"bullet_index": parsed.bullet_index, "revised_bullet": parsed.revised_bullet.strip()}
    except Exception:
        return None


MIN_SKILL_CATEGORIES = 2  # floor, enforced below via one bounded retry
MAX_SKILL_CATEGORIES = 3  # hard cap, enforced below - on top of this, Certifications gets its own category

# A label that just restates the section header instead of describing what's
# actually inside it - the tell-tale sign of the degenerate one-bucket
# failure mode this floor exists to catch (observed directly: a 23-skill
# resume came back as one category literally labeled "Technical Skills").
_GENERIC_CATEGORY_LABELS = {"technical skills", "skills", "core skills", "general skills", "key skills"}


class _SkillCategories(BaseModel):
    categories: List[TechnicalSkillCategory]


def _category_split_is_degenerate(categories: list[dict], total_skill_count: int) -> bool:
    """
    True when the actual-skills categorization collapsed to fewer than
    MIN_SKILL_CATEGORIES, or came back under a generic placeholder label,
    instead of genuinely bucketing the list. Skipped for short skill lists
    (< 4), where a single category can be the honest answer rather than a
    degenerate one - nothing to force-split there.
    """
    if total_skill_count < 4:
        return False
    skill_categories = [c for c in categories if "certif" not in c["label"].lower()]
    if len(skill_categories) < MIN_SKILL_CATEGORIES:
        return True
    return any(c["label"].strip().lower() in _GENERIC_CATEGORY_LABELS for c in skill_categories)


async def categorize_skills(skills: list[str], certifications: Optional[list[str]] = None) -> list[dict]:
    """
    Bucket a flat list of skills into MIN_SKILL_CATEGORIES-MAX_SKILL_CATEGORIES
    broad, resume-specific categories (plus a separate Certifications category
    when applicable), for resumes whose skills section isn't already
    categorized. Used when the user picks the Technical template but the
    parsed resume has no technical_skills data to render.

    certifications: a resume's additional_info.certifications, if any - not
    part of resume.skills, so without passing them in here explicitly they'd
    never be visible to this call at all, making the "certifications get
    their own category" behavior below unreachable for the common case where
    a resume already keeps certifications in their own parsed field.

    Category labels are chosen dynamically (not a fixed taxonomy) so they fit
    the actual skill set - e.g. "Design Tools" for a designer, "Programming"
    for an engineer - but the model is pushed toward a FEW, BROAD categories
    in a fixed 2-3 range rather than either extreme. An earlier version only
    capped the count from above ("at most 3"), which let the model collapse
    everything into a single generic-labeled bucket (indistinguishable from
    not categorizing at all) just as easily as it once over-fragmented into
    5 narrow ones - both failure modes are wrong, so both ends are enforced
    now, with one bounded retry (same pattern as bullet_verifier's re-ask)
    if the first pass comes back degenerate.
    """
    if not client or not skills:
        return []

    all_items = skills + (certifications or [])

    system_message = (
        f"You are a resume editor. Group the given flat list of skills into "
        f"EXACTLY {MIN_SKILL_CATEGORIES} OR {MAX_SKILL_CATEGORIES} BROAD "
        f"categories for actual skills - never just 1 combined bucket, never "
        f"more than {MAX_SKILL_CATEGORIES} - plus a separate 'Certifications' "
        f"category when applicable. Each category should cover a meaningful "
        f"share of the list, not just one or two items. Choose labels that "
        f"fit this specific skill set (e.g. 'Programming', 'Design Tools', "
        f"'Data Analysis') rather than a fixed template, but do not fragment "
        f"skills into many narrow categories - when in doubt, merge related "
        f"skills into the same broader category instead of creating a new "
        f"one. Keep each label SHORT - one concise term or short phrase (1-2 "
        f"words), never a combined 'X & Y' or 'X and Y' label - pick "
        f"whichever single concept best fits most of that category's "
        f"skills. Never use a generic placeholder label that just restates "
        f"the section itself (e.g. 'Technical Skills', 'Skills', 'Core "
        f"Skills') - every label must describe what's actually grouped "
        f"under it. The one exception to the category range: if any items "
        f"are professional certifications or credentials (even if worded "
        f"like a skill, e.g. 'AWS Certified Cloud Practitioner'), always put "
        f"those together under their own 'Certifications' category, "
        f"separate from the rest - this is in addition to, not counted "
        f"against, the {MIN_SKILL_CATEGORIES}-{MAX_SKILL_CATEGORIES} range "
        f"for actual skills. Do not add, remove, or rename any item."
    )

    prompt = f"""
Skills:
{json.dumps(all_items, indent=2)}

Instructions:
- Exactly {MIN_SKILL_CATEGORIES} or {MAX_SKILL_CATEGORIES} categories for actual skills - never 1 combined bucket, never more than {MAX_SKILL_CATEGORIES}
- Keep each label short - one concise term or short phrase, not a combined "X & Y" label
- Never use a generic label like "Technical Skills" or "Skills" - it must describe what's actually inside it
- Every item from the input must appear in exactly one category, unchanged
- Certifications/credentials always go in their own "Certifications" category, separate from technical skills and not counted against the {MIN_SKILL_CATEGORIES}-{MAX_SKILL_CATEGORIES} range
"""

    async def _call() -> list[dict]:
        response = await client.chat.completions.parse(
            model=settings.openai_model_fast,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            response_format=_SkillCategories,
            temperature=0.2,
        )
        parsed = _extract_parsed(response.choices[0].message)
        categories = [c.model_dump() for c in parsed.categories]
        return [c for c in categories if c.get("label") and c.get("items")]

    try:
        categories = await _call()

        if _category_split_is_degenerate(categories, len(all_items)):
            retry_prompt = prompt + (
                f"\n\nNOTE: A previous pass over this same list collapsed into a "
                f"single bucket (or used a generic placeholder label like "
                f"'Technical Skills'/'Skills'). That is not acceptable - split "
                f"the actual skills into {MIN_SKILL_CATEGORIES} or "
                f"{MAX_SKILL_CATEGORIES} genuinely distinct, specifically-"
                f"labeled groups this time."
            )
            response = await client.chat.completions.parse(
                model=settings.openai_model_fast,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": retry_prompt},
                ],
                response_format=_SkillCategories,
                temperature=0.2,
            )
            parsed = _extract_parsed(response.choices[0].message)
            retry_categories = [c.model_dump() for c in parsed.categories]
            retry_categories = [c for c in retry_categories if c.get("label") and c.get("items")]
            # Bounded to one retry - if it's still degenerate, keep the
            # original rather than risk another round; a single honest
            # category beats forcing a nonsensical split.
            if not _category_split_is_degenerate(retry_categories, len(all_items)):
                categories = retry_categories

        categories = _enforce_skill_category_cap(categories)
        categories = _restore_dropped_skills(categories, all_items)
        # Runs last, after restoration - a dropped-then-restored certification
        # gets placed by _restore_dropped_skills' own wording guess ("certif"
        # substring), which doesn't catch every real certification (e.g. "AWS
        # Cloud Practitioner" has no such substring). This is the final,
        # authoritative pass: anything we KNOW is a certification ends up in
        # the Certifications category no matter how it got misplaced.
        return _relocate_known_certifications(categories, certifications or [])
    except Exception:
        return []


class _SkillAssignment(BaseModel):
    skill: str
    category_label: str


class _SkillAssignments(BaseModel):
    assignments: List[_SkillAssignment]


async def assign_skills_to_existing_categories(
    new_skills: list[str], existing_labels: list[str]
) -> list[dict]:
    """
    Assign each of new_skills to one of existing_labels wherever it
    reasonably fits, rather than categorize_skills()'s from-scratch
    bucketing - used when a resume's TECHNICAL SKILLS is already
    categorized and a few new skills (e.g. confirmed from the inferred-
    skills picker) need to be added without disturbing the categories the
    candidate already has. A from-scratch re-categorization would risk
    renaming/reshuffling the existing labels the candidate is used to
    seeing (e.g. "Computer Software" becoming "Data Tools"); this only ever
    appends to them.

    Returns [{"skill": ..., "category_label": ...}] - category_label is
    ideally one of existing_labels verbatim; the model may propose a new
    label only when a skill doesn't reasonably fit any of them.
    """
    if not client or not new_skills or not existing_labels:
        return []

    prompt = f"""
A resume's TECHNICAL SKILLS section already has these category labels:
{json.dumps(existing_labels)}

These new skills need to be added into the section:
{json.dumps(new_skills)}

For each new skill, choose which of the EXISTING category labels above it fits into.
STRONGLY prefer reusing an existing label, even for a loose or broad fit - most new skills
belong in one of the categories already there. Only propose a brand-new category label for a
skill that is genuinely different in kind from everything the existing categories cover (e.g.
a hardware/IoT-specific skill on an otherwise all-software-and-data resume) - this should be
rare, not the default choice.

Rules:
- Prefer an existing label from the list above whenever a skill reasonably fits there.
- Only invent a new label as a last resort, when no existing category fits at all.
- Every skill in the input list must get exactly one category_label.
"""

    try:
        response = await client.chat.completions.parse(
            model=settings.openai_model_fast,
            messages=[{"role": "user", "content": prompt}],
            response_format=_SkillAssignments,
            temperature=0,
        )
        parsed = _extract_parsed(response.choices[0].message)
        return [a.model_dump() for a in parsed.assignments if a.skill and a.category_label]
    except Exception:
        return []


def _relocate_known_certifications(categories: list[dict], certifications: list[str]) -> list[dict]:
    """
    Force every item passed in as a KNOWN certification (categorize_skills'
    `certifications` argument - i.e. the resume's own parsed
    additional_info.certifications, not a guess from wording) into the
    Certifications category, regardless of which category it currently
    sits in or how it got there. Called last, after both the model's own
    categorization AND _restore_dropped_skills - a certification can end up
    misplaced either way: the model files it under an invented category
    directly, or omits it entirely and _restore_dropped_skills' own
    wording-based guess (a "certif" substring match) puts it back in the
    wrong place since not every real certification's name contains that
    substring (e.g. "AWS Cloud Practitioner").

    The system prompt already tells the model to keep certifications
    separate even when worded like a skill - but that's prompt compliance,
    not a guarantee, and it isn't reliable: observed directly on a real
    resume, "AWS Cloud Practitioner" and "COMPTIA Security+ (In Progress)"
    (both passed in here as known certifications) still ended up filed
    under an invented "Programming" category. Since we already know for a
    fact which items are certifications, there's no reason to leave their
    placement up to the model at all.
    """
    known_lower = {c.strip().lower() for c in certifications if c and c.strip()}
    if not known_lower:
        return categories

    cert_idx = next((i for i, c in enumerate(categories) if "certif" in c["label"].lower()), None)
    if cert_idx is None:
        categories.append({"label": "Certifications", "items": []})
        cert_idx = len(categories) - 1

    cert_items_lower = {i.strip().lower() for i in categories[cert_idx]["items"]}

    for i, cat in enumerate(categories):
        if i == cert_idx:
            continue
        misplaced = [item for item in cat["items"] if item.strip().lower() in known_lower]
        if not misplaced:
            continue
        cat["items"] = [item for item in cat["items"] if item.strip().lower() not in known_lower]
        for item in misplaced:
            if item.strip().lower() not in cert_items_lower:
                categories[cert_idx]["items"].append(item)
                cert_items_lower.add(item.strip().lower())

    # A non-cert category emptied out entirely by relocation shouldn't
    # survive as an empty bucket.
    return [c for c in categories if c["items"]]


def _enforce_skill_category_cap(categories: list[dict]) -> list[dict]:
    """
    Hard-enforce MAX_SKILL_CATEGORIES regardless of what the model returned:
    Certifications is always kept as its own category (doesn't count against
    the cap), and any non-certification categories beyond the limit get their
    items folded into the last kept category rather than dropped.
    """
    cert_categories = [c for c in categories if "certif" in c["label"].lower()]
    skill_categories = [c for c in categories if "certif" not in c["label"].lower()]

    if len(skill_categories) > MAX_SKILL_CATEGORIES:
        kept = skill_categories[:MAX_SKILL_CATEGORIES]
        overflow = skill_categories[MAX_SKILL_CATEGORIES:]
        for extra in overflow:
            kept[-1]["items"].extend(extra["items"])
        skill_categories = kept

    return skill_categories + cert_categories


def _restore_dropped_skills(categories: list[dict], original_skills: list[str]) -> list[dict]:
    """
    The model occasionally omits an input skill from its response entirely
    (observed most often with certification-like entries). Never let that
    silently lose content from the user's resume: any skill missing from
    every category gets added back - into a "Certifications" category
    (created if needed) when it looks like a credential, otherwise appended
    to the last category.
    """
    placed = {item.strip().lower() for c in categories for item in c["items"]}
    missing = [s for s in original_skills if s.strip().lower() not in placed]
    if not missing:
        return categories

    cert_idx = next((i for i, c in enumerate(categories) if "certif" in c["label"].lower()), None)
    # Fixed ahead of the loop so a newly-created Certifications category
    # never becomes the fallback target for a later non-cert missing skill.
    fallback_idx = next((i for i, c in enumerate(categories) if "certif" not in c["label"].lower()), None)

    for skill in missing:
        if "certif" in skill.lower():
            if cert_idx is not None:
                categories[cert_idx]["items"].append(skill)
            else:
                categories.append({"label": "Certifications", "items": [skill]})
                cert_idx = len(categories) - 1
        elif fallback_idx is not None:
            categories[fallback_idx]["items"].append(skill)
        else:
            categories.append({"label": "Skills", "items": [skill]})
            fallback_idx = len(categories) - 1

    return categories
