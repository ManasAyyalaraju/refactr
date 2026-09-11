import json
from typing import List, Optional
from openai import AsyncOpenAI
from pydantic import BaseModel
from core.config import settings
from models.resume_models import Resume, TechnicalSkillCategory
from services.domain_prompts import get_domain_prompt, format_domain_guidance

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
        primary_rule = """
=========================================
⚠️ PRIMARY RULE: EXPAND CONTENT TO FILL PAGE ⚠️
=========================================

RESUME TYPE: SPARSE - EXPAND bullets and ADD headline/summary

**YOUR PRIMARY JOB:**
1. **ADD HEADLINE**: Create a professional headline (one impactful sentence, 50-80 chars)
2. **ADD SUMMARY**: Write a compelling 2-3 sentence summary (150-250 chars total)
3. **EXPAND BULLETS**: Make each bullet MORE detailed and comprehensive
   - Target 180-250 characters per bullet (2.5-3 lines)
   - Add context, technologies, methodologies, and impact
   - Include stakeholder information where relevant
   - Describe scope, team size, and business outcomes
   - Use metrics and quantifiable results

**HOW TO EXPAND BULLETS:**
✅ GOOD: Add specific technologies and tools used
✅ GOOD: Include team size, scope, and stakeholders
✅ GOOD: Add business context and outcomes
✅ GOOD: Expand on methodologies and approaches
✅ GOOD: Include comprehensive metrics and impact details
✅ GOOD: Make bullets fill 2.5-3 complete lines on the page

**Example of GOOD expansion:**
Original (120 chars): "Supervised sorting and packaging of donated meals and essentials"
✅ Expanded (210 chars): "Supervised and coordinated a team of 10+ volunteers in the efficient sorting, packaging, and distribution of donated meals and essential supplies, ensuring timely delivery to 15+ local charities and hunger relief programs across the Dallas-Fort Worth region"
"""
        examples_header = "**SPARSE RESUME - EXPAND with detail:**"
        example1 = '✅ Good (230 chars): "Developed and engineered 5+ comprehensive IT mobile applications and catalog items using modern frameworks including React Native and TypeScript, resulting in a significant 15% increase in user engagement metrics, positive user ratings, and enhanced customer satisfaction across multiple platforms"'
        example2 = '✅ Good (195 chars): "Supported and facilitated technical sales cycles across 10+ national accounts, collaborating with cross-functional teams to align secure data integration and governance solutions with client business objectives"'
        headline_summary_instruction = """
**HEADLINE AND SUMMARY GENERATION (REQUIRED FOR SPARSE RESUMES):**
- **headline**: Write ONE impactful sentence (50-80 chars) that captures the candidate's value proposition
  Example: "Information Systems Student | Cybersecurity Enthusiast | Tech Leader"
- **summary**: Write 2-3 sentences (150-250 chars) highlighting key strengths, skills, and career focus
  Example: "Information Technology student with hands-on experience in cybersecurity education and community impact initiatives. Skilled in WatsonX AI, data analysis, and volunteer leadership. Passionate about leveraging technology to solve real-world challenges in food security and information systems."
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
2. {"**MATCH CHARACTER COUNTS** - Each tailored bullet should be within ±15 chars of original" if is_compact else "**EXPAND BULLETS** - Each bullet should be 180-250 characters (2.5-3 lines)"}
3. {"**SWAP, DON'T ADD** - Replace generic terms with JD-specific keywords" if is_compact else "**ADD DETAIL** - Include technologies, context, metrics, and impact"}
4. **PRESERVE STRUCTURE** - Do NOT change job titles, companies, dates, or locations
5. **KEEP METRICS** - Preserve all numbers and percentages from original bullets
6. **STAY TRUTHFUL** - Only use skills from the resume's skills list

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

    system_message = f"You are a resume editor specializing in {industry}. Your PRIMARY goal: tailor content while matching original bullet lengths character-for-character."

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


async def generate_headline_summary(resume_json: dict) -> dict:
    """
    Generate ONLY a headline and summary from existing resume content.
    - No JD context
    - Do NOT alter bullets or any other fields
    - Keep it concise and truthful to provided data
    """
    if not client:
        return {"headline": None, "summary": None}

    system_message = (
        "You are a resume editor. Only produce a short headline and 2-3 sentence "
        "summary using existing resume details. Do not invent facts. Do not rewrite "
        "bullets or any other fields. Keep it concise and professional."
    )

    prompt = f"""
Resume JSON (truth source):
{json.dumps(resume_json, indent=2)}

Instructions:
- Use ONLY information present above (roles, education, skills, bullets)
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


MAX_SKILL_CATEGORIES = 3  # hard cap, enforced below - on top of this, Certifications gets its own category


class _SkillCategories(BaseModel):
    categories: List[TechnicalSkillCategory]


async def categorize_skills(skills: list[str]) -> list[dict]:
    """
    Bucket a flat list of skills into at most MAX_SKILL_CATEGORIES broad,
    resume-specific categories (plus a separate Certifications category when
    applicable), for resumes whose skills section isn't already categorized.
    Used when the user picks the Technical template but the parsed resume has
    no technical_skills data to render.

    Category labels are chosen dynamically (not a fixed taxonomy) so they fit
    the actual skill set - e.g. "Design Tools" for a designer, "Programming"
    for an engineer - but the model is pushed hard toward FEW, BROAD
    categories rather than one-off niche ones. An earlier version let the
    model invent as many categories as it wanted, which produced overly
    granular, inconsistent groupings (e.g. "Web Development", "Data Science",
    "Databases", "Business Intelligence", "DevOps & Tools" all for one
    person's skill list) and let certifications get miscategorized as tools.
    The category count is a hard requirement, so it's enforced in code below
    rather than trusted to the prompt alone.
    """
    if not client or not skills:
        return []

    system_message = (
        f"You are a resume editor. Group the given flat list of skills into "
        f"AT MOST {MAX_SKILL_CATEGORIES} BROAD categories for actual skills, "
        f"plus a separate 'Certifications' category when applicable - "
        f"{MAX_SKILL_CATEGORIES} skill categories is a hard maximum, never "
        f"more. Each category should cover a meaningful share of the list, "
        f"not just one or two items. Choose labels that fit this specific "
        f"skill set (e.g. 'Programming', 'Design Tools', 'Data Analysis') "
        f"rather than a fixed template, but do not fragment skills into many "
        f"narrow categories - when in doubt, merge related skills into the "
        f"same broader category instead of creating a new one. Keep each "
        f"label SHORT - one concise term or short phrase (1-2 words), never "
        f"a combined 'X & Y' or 'X and Y' label - pick whichever single "
        f"concept best fits most of that category's skills. The one "
        f"exception to the category cap: if any skills are professional "
        f"certifications or credentials (even if worded like a skill, e.g. "
        f"'AWS Certified Cloud Practitioner'), always put those together "
        f"under their own 'Certifications' category, separate from the "
        f"rest - this is in addition to, not counted against, the "
        f"{MAX_SKILL_CATEGORIES}-category limit for actual skills. Do not "
        f"add, remove, or rename any skill."
    )

    prompt = f"""
Skills:
{json.dumps(skills, indent=2)}

Instructions:
- At most {MAX_SKILL_CATEGORIES} categories for actual skills - prefer fewer, wider categories over many narrow ones
- Keep each label short - one concise term or short phrase, not a combined "X & Y" label
- Every skill from the input must appear in exactly one category, unchanged
- Certifications/credentials always go in their own "Certifications" category, separate from technical skills and not counted against the {MAX_SKILL_CATEGORIES}-category limit
"""

    try:
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
        categories = [c for c in categories if c.get("label") and c.get("items")]
        categories = _enforce_skill_category_cap(categories)
        return _restore_dropped_skills(categories, skills)
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
