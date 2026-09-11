from typing import List, Optional

from models.resume_models import Resume, TechnicalSkillCategory
from models.job_models import JobDescription
from core.exceptions import TailoringGenerationError
from services.bullet_verifier import verify_bullets, find_unauthorized_terms
from .llm_client import rewrite_resume_sections, categorize_skills, assign_skills_to_existing_categories, revise_bullet
import json
import logging
import re

logger = logging.getLogger(__name__)


def estimate_resume_fullness(resume: Resume) -> int:
    """
    Estimate how full/dense the resume content is by counting various elements.
    Returns a score representing content density.

    Higher scores indicate fuller resumes that may not have room for headline/summary.
    """
    score = 0

    # Count experience entries and bullets (weighted heavily)
    if resume.experience:
        score += len(resume.experience) * 3  # Each experience entry counts as 3
        for exp in resume.experience:
            score += len(exp.bullets)  # Each bullet counts as 1

    # Count project entries and bullets
    if resume.projects:
        score += len(resume.projects) * 2  # Each project counts as 2
        for proj in resume.projects:
            score += len(proj.bullets)

    # Count leadership entries and bullets
    if resume.leadership:
        score += len(resume.leadership) * 2  # Each leadership entry counts as 2
        for lead in resume.leadership:
            score += len(lead.bullets)

    # Count education entries
    if resume.education:
        score += len(resume.education) * 2  # Each education entry counts as 2

    # Count other sections (lighter weight)
    if resume.volunteer_work:
        score += len(resume.volunteer_work) * 2
        for vol in resume.volunteer_work:
            score += len(vol.bullets)

    if resume.awards:
        score += len(resume.awards)

    if resume.publications:
        score += len(resume.publications) * 2

    # Skills section counts as 1
    if resume.skills:
        score += 1

    # Categorized TECHNICAL SKILLS section adds a whole extra section to the
    # page (section header + one line per category), so weight it accordingly
    # rather than letting it go uncounted.
    if resume.technical_skills:
        score += 1  # section header, mirrors base weight of other sections
        score += len(resume.technical_skills)  # each category line ~= a bullet

    return score


def conditionally_remove_headline_summary(resume: Resume) -> Resume:
    """
    Remove headline and summary sections if the resume is too full to fit on one page.
    ADD headline and summary if the resume is sparse and needs more content.

    Threshold guideline:
    - Score < 35: Resume is sparse, KEEP or ADD headline/summary to fill space
    - Score >= 35: Resume is full, REMOVE headline/summary to save space
    """
    FULLNESS_THRESHOLD = 35  # Raised from 30

    fullness_score = estimate_resume_fullness(resume)

    # Additional checks for sparseness
    has_work_experience = len(resume.experience) > 0
    total_bullets = (
        sum(len(exp.bullets) for exp in resume.experience) +
        sum(len(proj.bullets) for proj in resume.projects) +
        sum(len(lead.bullets) for lead in resume.leadership) +
        sum(len(vol.bullets) for vol in resume.volunteer_work)
    )

    # Resume is SPARSE if:
    # - No work experience, OR
    # - Few bullets (< 15), OR
    # - Low fullness score (< 35)
    is_sparse = (
        not has_work_experience or
        total_bullets < 15 or
        fullness_score < FULLNESS_THRESHOLD
    )

    if is_sparse:
        # Resume is sparse - KEEP headline/summary to fill space
        # Don't remove even if they exist
        pass  # Keep as is
    else:
        # Resume is full - REMOVE headline/summary to save space
        resume.headline = None
        resume.summary = None

    return resume


def format_skill(skill: str) -> str:
    """
    Format a skill string:
    - If it's a tool (no commas or "and"), keep it as is
    - If it's a concept phrase (contains commas or "and"), capitalize first letter of every word
    """
    # Check if it's a concept phrase (contains commas or " and " with spaces)
    if "," in skill or re.search(r'\s+and\s+', skill, re.IGNORECASE):
        # Title case: capitalize first letter of every word
        # Split by word boundaries to handle punctuation properly
        def capitalize_word(word: str) -> str:
            """Capitalize first letter of a word, lowercasing the rest."""
            if not word:
                return word
            # Find first alphabetic character
            for i, char in enumerate(word):
                if char.isalpha():
                    return word[:i] + char.upper() + word[i+1:].lower()
            return word

        # Split into words (preserving spaces)
        words = skill.split()
        formatted_words = [capitalize_word(word) for word in words]
        return " ".join(formatted_words)
    else:
        # Keep tools as is
        return skill


def format_skills_list(skills: list[str]) -> list[str]:
    """Format a list of skills according to the formatting rules."""
    return [format_skill(skill) for skill in skills]


async def ensure_technical_skills(resume: Resume) -> Resume:
    """
    Populate resume.technical_skills from the flat resume.skills list when
    the source resume didn't already present skills in a categorized format.
    Only call this when the Technical template is actually being rendered -
    without it, picking "Technical" on a resume with a flat skills list has
    no visible effect since the template only renders a TECHNICAL SKILLS
    section when technical_skills is non-empty.
    """
    if not resume.skills:
        return resume

    if not resume.technical_skills:
        categories = await categorize_skills(resume.skills)
        if categories:
            resume.technical_skills = [TechnicalSkillCategory(**c) for c in categories]
        return resume

    # Categories already exist (parsed from the original resume), but
    # resume.skills can have grown since (e.g. picker-confirmed skills merged
    # in after that parse) - without this, anything added after the original
    # categorization would show up in the flat skills list/compatibility
    # score but never in the rendered TECHNICAL SKILLS section.
    categorized_lower = {item.lower() for cat in resume.technical_skills for item in cat.items}
    orphaned = [s for s in resume.skills if s.lower() not in categorized_lower]
    if not orphaned:
        return resume

    # Fit the orphaned skills into the EXISTING categories rather than
    # re-categorizing everything from scratch (which silently renamed/
    # reshuffled labels the candidate already had, e.g. "Computer Software"
    # becoming "Data Tools") or categorizing the orphaned skills in total
    # isolation (which had no context to avoid awkward single-item
    # categories like "Web Development: FastAPI"). Only creates a new
    # category as a last resort, when a skill genuinely doesn't fit any
    # existing one.
    existing_labels = [c.label for c in resume.technical_skills]
    assignments = await assign_skills_to_existing_categories(orphaned, existing_labels)

    assigned_lower = set()
    for a in assignments:
        skill, label = a.get("skill"), (a.get("category_label") or "").strip()
        if not skill or not label:
            continue
        existing = next(
            (c for c in resume.technical_skills if c.label.strip().lower() == label.lower()), None
        )
        if existing:
            if skill.lower() not in {i.lower() for i in existing.items}:
                existing.items.append(skill)
        else:
            resume.technical_skills.append(TechnicalSkillCategory(label=label, items=[skill]))
        assigned_lower.add(skill.lower())

    # The model occasionally drops an input skill from its response -
    # never let that silently lose it from the rendered section.
    unassigned = [s for s in orphaned if s.lower() not in assigned_lower]
    if unassigned and resume.technical_skills:
        resume.technical_skills[0].items.extend(unassigned)

    return resume


def reorder_skills(resume: Resume, jd: JobDescription) -> Resume:
    jd_skills = set(jd.must_have_skills + jd.nice_to_have_skills)
    jd_skills_lower = {s.lower() for s in jd_skills}

    matching = [s for s in resume.skills if s.lower() in jd_skills_lower]
    non_matching = [s for s in resume.skills if s.lower() not in jd_skills_lower]

    resume.skills = matching + non_matching
    return resume


async def _verify_and_correct_section(
    original_entries: list,
    rewritten_entries: list,
    jd_skills: list[str],
    resume_skills: list[str],
    resume_technical_skills: list[str],
    jd_json: dict,
) -> None:
    """
    For each entry in a section (experience/projects/leadership), check its
    tailored bullets against bullet_verifier and correct or revert any that
    introduce a JD skill the candidate doesn't actually have. Mutates
    `rewritten_entries` in place.
    """
    for original, rewritten in zip(original_entries, rewritten_entries):
        violations = verify_bullets(
            original.bullets, rewritten.bullets, jd_skills, resume_skills, resume_technical_skills
        )
        if not violations:
            continue

        for idx, unauthorized_terms in violations.items():
            original_bullet = original.bullets[idx]
            tailored_bullet = rewritten.bullets[idx]

            revised = await revise_bullet(original_bullet, tailored_bullet, unauthorized_terms, jd_json)
            still_flagged = find_unauthorized_terms(
                original_bullet, revised, jd_skills, resume_skills, resume_technical_skills
            )

            # Bounded to exactly one re-ask - if it's still not clean, fall
            # back to the original bullet text (guaranteed truthful) rather
            # than risk another round or fragile string surgery.
            if still_flagged:
                logger.warning(
                    "bullet_verifier: re-ask did not clear violation, reverting to original bullet "
                    "(terms=%s, still_flagged=%s)", unauthorized_terms, still_flagged
                )
                rewritten.bullets[idx] = original_bullet
            else:
                logger.info(
                    "bullet_verifier: corrected tailored bullet (terms=%s)", unauthorized_terms
                )
                rewritten.bullets[idx] = revised


async def tailor_resume(
    resume: Resume,
    jd: JobDescription,
    domain_info: dict,
    additional_skills: Optional[List[str]] = None,
) -> Resume:
    """
    Tailor resume to the job description:
    1. Reorder skills to prioritize JD-relevant ones.
    2. Ask LLM to rewrite summary + bullets.
    3. Enforce:
       - company, title, dates, location stay EXACTLY the same
       - number of bullets per experience/project/leadership stays the same
    4. Verify tailored bullets don't introduce a JD skill the candidate
       doesn't actually have; correct (bounded to one retry) or revert any
       that do.
    5. Set compact_mode based on resume fullness

    `additional_skills` - skills the candidate explicitly confirmed they
    have (e.g. from the inferred-skills picker), merged into resume.skills
    BEFORE reordering/rewriting so they're treated as truthful: the LLM
    rewrite sees them as part of the resume's real skill list, and the
    bullet verifier's allowed-skill pool (read from the rewritten resume's
    skills afterward) includes them automatically - no verifier changes
    needed.
    """
    if additional_skills:
        existing_lower = {s.lower() for s in resume.skills}
        for skill in additional_skills:
            if skill and skill.lower() not in existing_lower:
                resume.skills.append(skill)
                existing_lower.add(skill.lower())

    # Calculate resume fullness to determine compact mode
    fullness_score = estimate_resume_fullness(resume)

    # Count total bullets for density analysis
    total_bullets = 0
    for exp in resume.experience:
        total_bullets += len(exp.bullets)
    for proj in resume.projects:
        total_bullets += len(proj.bullets)
    for lead in resume.leadership:
        total_bullets += len(lead.bullets)
    for vol in resume.volunteer_work:
        total_bullets += len(vol.bullets)

    # Count sections
    num_sections = sum([
        1 if resume.experience else 0,
        1 if resume.projects else 0,
        1 if resume.leadership else 0,
        1 if resume.education else 0,
        1 if resume.volunteer_work else 0,
        1 if resume.awards else 0,
        1 if resume.publications else 0
    ])

    # Calculate average bullet length
    all_bullets = []
    for exp in resume.experience:
        all_bullets.extend(exp.bullets)
    for proj in resume.projects:
        all_bullets.extend(proj.bullets)
    for lead in resume.leadership:
        all_bullets.extend(lead.bullets)
    for vol in resume.volunteer_work:
        all_bullets.extend(vol.bullets)

    avg_bullet_length = sum(len(b) for b in all_bullets) / len(all_bullets) if all_bullets else 150

    # Check critical indicators
    has_work_experience = len(resume.experience) > 0
    has_headline = resume.headline not in [None, ""]
    has_summary = resume.summary not in [None, ""]

    # Set compact mode for SPACING using RELAXED criteria
    # Use minimal spacing if resume has substantial content, regardless of bullet length
    # This ensures "Full but Verbose" resumes (like Aswath) get minimal spacing
    resume.compact_mode = (
        has_work_experience and              # Must have work experience
        total_bullets >= 15 and              # At least 15 bullets
        fullness_score >= 35                 # High fullness score
        # NOTE: Don't check avg_bullet_length here - that's for LLM only
        # Even if bullets are long/verbose, use minimal spacing to save space
    )

    # Keep original experience, project, and leadership structures for safety
    original_experience = [exp.model_copy(deep=True) for exp in resume.experience]
    original_projects = [proj.model_copy(deep=True) for proj in resume.projects]
    original_leadership = [lead.model_copy(deep=True) for lead in resume.leadership]
    original_technical_skills = [cat.model_copy(deep=True) for cat in resume.technical_skills]

    # Step 1: rule-based skills adjustment
    resume = reorder_skills(resume, jd)

    # Step 2: LLM rewrite
    resume_json = json.loads(resume.model_dump_json())
    jd_json = json.loads(jd.model_dump_json())

    try:
        rewritten_resume = await rewrite_resume_sections(resume_json, jd_json, domain_info)
    except Exception as e:
        # Never silently fall back to the untailored resume - the caller
        # needs a clear, catchable signal that tailoring failed.
        raise TailoringGenerationError(f"Resume tailoring failed: {e}") from e

    # Preserve compact_mode setting
    rewritten_resume.compact_mode = resume.compact_mode

    # Preserve categorized technical skills exactly as parsed - never LLM-rewritten
    rewritten_resume.technical_skills = original_technical_skills

    # Step 3a: lock experience metadata and bullet counts
    locked_experience = []
    for original, rewritten in zip(original_experience, rewritten_resume.experience):
        # Lock non-editable fields
        rewritten.company = original.company
        rewritten.title = original.title
        rewritten.start_date = original.start_date
        rewritten.end_date = original.end_date
        rewritten.location = original.location

        # Enforce same number of bullets
        orig_bullets = original.bullets
        new_bullets = rewritten.bullets or []

        if len(new_bullets) < len(orig_bullets):
            # If fewer bullets returned, pad with original ones
            new_bullets = new_bullets + orig_bullets[len(new_bullets):]
        elif len(new_bullets) > len(orig_bullets):
            # If too many, truncate
            new_bullets = new_bullets[: len(orig_bullets)]

        rewritten.bullets = new_bullets
        locked_experience.append(rewritten)

    rewritten_resume.experience = locked_experience

    # Step 3b: enforce same bullet count for projects too
    locked_projects = []
    for original, rewritten in zip(original_projects, rewritten_resume.projects):
        orig_bullets = original.bullets
        new_bullets = rewritten.bullets or []

        if len(new_bullets) < len(orig_bullets):
            new_bullets = new_bullets + orig_bullets[len(new_bullets):]
        elif len(new_bullets) > len(orig_bullets):
            new_bullets = new_bullets[: len(orig_bullets)]

        rewritten.bullets = new_bullets
        locked_projects.append(rewritten)

    rewritten_resume.projects = locked_projects

    # Step 3c: enforce same bullet count for leadership
    locked_leadership = []
    for original, rewritten in zip(original_leadership, rewritten_resume.leadership):
        # Lock non-editable fields
        rewritten.organization = original.organization
        rewritten.role = original.role
        rewritten.start_date = original.start_date
        rewritten.end_date = original.end_date
        rewritten.location = original.location

        # Enforce same number of bullets
        orig_bullets = original.bullets
        new_bullets = rewritten.bullets or []

        if len(new_bullets) < len(orig_bullets):
            new_bullets = new_bullets + orig_bullets[len(new_bullets):]
        elif len(new_bullets) > len(orig_bullets):
            new_bullets = new_bullets[: len(orig_bullets)]

        rewritten.bullets = new_bullets
        locked_leadership.append(rewritten)

    rewritten_resume.leadership = locked_leadership

    # Step 4: Verify tailored bullets stay truthful - flag any JD skill that
    # shows up in a tailored bullet but wasn't in the original bullet nor
    # anywhere in the candidate's own skill lists, and correct/revert it.
    jd_skills = (jd.must_have_skills or []) + (jd.nice_to_have_skills or [])
    resume_skill_pool = rewritten_resume.skills or []
    resume_technical_pool = [item for cat in rewritten_resume.technical_skills for item in cat.items]

    await _verify_and_correct_section(
        original_experience, rewritten_resume.experience, jd_skills, resume_skill_pool, resume_technical_pool, jd_json
    )
    await _verify_and_correct_section(
        original_projects, rewritten_resume.projects, jd_skills, resume_skill_pool, resume_technical_pool, jd_json
    )
    await _verify_and_correct_section(
        original_leadership, rewritten_resume.leadership, jd_skills, resume_skill_pool, resume_technical_pool, jd_json
    )

    # Step 5: Format skills (tools stay as is, concept phrases get title case)
    rewritten_resume.skills = format_skills_list(rewritten_resume.skills)

    # Step 6: Conditionally remove headline/summary if resume is too full
    rewritten_resume = conditionally_remove_headline_summary(rewritten_resume)

    return rewritten_resume
