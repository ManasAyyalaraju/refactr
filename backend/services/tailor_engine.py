from typing import List, Optional

from models.resume_models import Resume, TechnicalSkillCategory
from models.job_models import JobDescription
from core.exceptions import TailoringGenerationError
from services.bullet_verifier import (
    verify_bullets,
    find_unauthorized_terms,
    find_weak_opener_bullets,
    find_duplicate_opening_verbs,
    extract_opening_verb,
    find_overlong_bullets,
    SPARSE_BULLET_CHAR_CEILING,
)
from .llm_client import (
    rewrite_resume_sections,
    categorize_skills,
    assign_skills_to_existing_categories,
    revise_bullet,
    revise_weak_opener,
    revise_repeated_verb,
    revise_overlong_bullet,
    generate_headline_summary,
    classify_confirmed_skills,
    weave_skill_into_bullet,
    _category_split_is_degenerate,
)
from services.pdf_writer import render_resume_pdf_ex, _count_pdf_pages
import asyncio
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


def compute_compact_mode(resume: Resume) -> bool:
    """
    Shared compact-mode decision - used identically at reformat time
    (reformat_engine.py) and tailor time (tailor_resume below). A resume's
    bullet/section counts don't change between the two stages (tailoring
    only rewords bullets, it never adds or removes them), so there's no
    reason for each stage to maintain its own copy of this threshold logic;
    previously they did, as two separately-written but textually-identical
    formulas. Page-fit precision from here on is handled by render_resume_pdf
    measuring the actual rendered output (see pdf_writer.py's roomy_mode
    stepping) - this only needs to pick a reasonable starting tier.
    """
    fullness_score = estimate_resume_fullness(resume)
    total_bullets = (
        sum(len(exp.bullets) for exp in resume.experience) +
        sum(len(proj.bullets) for proj in resume.projects) +
        sum(len(lead.bullets) for lead in resume.leadership) +
        sum(len(vol.bullets) for vol in resume.volunteer_work)
    )
    has_work_experience = len(resume.experience) > 0

    return (
        has_work_experience and    # Must have work experience
        total_bullets >= 15 and    # At least 15 bullets
        fullness_score >= 35       # High fullness score
    )


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


async def ensure_technical_skills(resume: Resume, allow_recategorize: bool = False) -> Resume:
    """
    Populate resume.technical_skills from the flat resume.skills list when
    the source resume didn't already present skills in a categorized format.
    Only call this when the Technical template is actually being rendered -
    without it, picking "Technical" on a resume with a flat skills list has
    no visible effect since the template only renders a TECHNICAL SKILLS
    section when technical_skills is non-empty.

    allow_recategorize: when True (tailor time only - see tailor_routes.py),
    an existing technical_skills that's degenerate (collapsed to a single,
    often generically-labeled bucket like "Technical Skills" - the parser
    faithfully transcribes a resume's own "Technical Skills: A, B, C" line
    that way, since it reads as "categorized" even though a single generic
    label carries no more structure than a flat list) gets re-categorized
    from scratch through the same categorize_skills() used for an
    uncategorized resume, instead of just having new skills appended to the
    existing bad bucket. Defaults to False so reformat time (a first save)
    leaves whatever categorization the user's own resume presented alone,
    even if degenerate - tailoring, which is already reshaping the resume
    for a specific submission, is the more appropriate moment to fix it.
    """
    if not resume.skills:
        return resume

    certifications = (
        resume.additional_info.certifications
        if resume.additional_info and resume.additional_info.certifications
        else None
    )

    needs_fresh_categorization = not resume.technical_skills or (
        allow_recategorize
        and _category_split_is_degenerate(
            [c.model_dump() for c in resume.technical_skills],
            len(resume.skills) + len(certifications or []),
        )
    )

    if needs_fresh_categorization:
        categories = await categorize_skills(resume.skills, certifications)
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


def _tailorable_bullet_lists(resume: Resume) -> List[list]:
    """
    Bullet lists from the sections tailoring actually rewrites - mirrors
    _verify_and_correct_section's scope (experience/projects/leadership;
    volunteer_work isn't LLM-rewritten so it's excluded here too).
    """
    lists = [entry.bullets for entry in resume.experience]
    lists += [entry.bullets for entry in resume.projects]
    lists += [entry.bullets for entry in resume.leadership]
    return lists


async def _correct_weak_openers(resume: Resume, jd_json: dict) -> None:
    """
    Auto-correct fix-up for bullets that open with a responsibility phrase
    or a gerund instead of a strong action verb. Each bullet's correction
    is independent of every other, so they run concurrently.
    """
    refs = [
        (bullets, idx)
        for bullets in _tailorable_bullet_lists(resume)
        for idx in find_weak_opener_bullets(bullets)
    ]
    if not refs:
        return

    revised = await asyncio.gather(*[revise_weak_opener(bullets[idx], jd_json) for bullets, idx in refs])
    for (bullets, idx), new_bullet in zip(refs, revised):
        bullets[idx] = new_bullet

    logger.info("bullet_verifier: corrected %d weak-opener bullet(s)", len(refs))


async def _correct_repeated_opening_verbs(resume: Resume, jd_json: dict) -> None:
    """
    Auto-correct fix-up for bullets that share an opening verb with another
    bullet on the same resume. Unlike weak-opener correction, this needs
    cross-bullet awareness - each fix must avoid every verb already in use,
    including ones just fixed earlier in this same pass - so corrections
    run sequentially with a growing used-verb set rather than concurrently.
    """
    all_refs = [
        (bullets, idx)
        for bullets in _tailorable_bullet_lists(resume)
        for idx in range(len(bullets))
    ]
    flat_bullets = [bullets[idx] for bullets, idx in all_refs]

    duplicates = find_duplicate_opening_verbs(flat_bullets)
    if not duplicates:
        return

    used_verbs = {extract_opening_verb(b) for b in flat_bullets if extract_opening_verb(b)}
    corrected_count = 0

    for verb, flat_idxs in duplicates.items():
        # Keep the first bullet using this verb as-is; only the later ones
        # sharing it need a new verb.
        for flat_idx in flat_idxs[1:]:
            bullets, idx = all_refs[flat_idx]
            original = bullets[idx]

            revised = await revise_repeated_verb(original, sorted(used_verbs), jd_json)
            new_verb = extract_opening_verb(revised)

            # Bounded to one attempt - if the model didn't actually land on
            # an unused verb, keep the original bullet (still a duplicate,
            # but truthful and safe) rather than risk another round.
            if new_verb and new_verb not in used_verbs:
                bullets[idx] = revised
                used_verbs.add(new_verb)
                corrected_count += 1
            else:
                logger.warning(
                    "bullet_verifier: repeated-verb re-ask did not produce a new verb, "
                    "keeping original bullet (verb=%s)", verb
                )

    if corrected_count:
        logger.info("bullet_verifier: corrected %d repeated-opening-verb bullet(s)", corrected_count)


async def _correct_overlong_bullets(resume: Resume, jd_json: dict) -> None:
    """
    Auto-correct fix-up for bullets exceeding SPARSE_BULLET_CHAR_CEILING -
    bullet_verifier's calibrated character proxy for the sparse-mode
    3-line ceiling (nothing in this pipeline renders an individual bullet
    to measure its actual wrapped line count). Each bullet's correction is
    independent of every other, so they run concurrently. Only meaningful
    for sparse (non-compact) resumes - the caller only invokes this when
    compact_mode is off, since compact mode's own char-match instruction
    already keeps bullets well under this ceiling.
    """
    refs = [
        (bullets, idx)
        for bullets in _tailorable_bullet_lists(resume)
        for idx in find_overlong_bullets(bullets)
    ]
    if not refs:
        return

    revised = await asyncio.gather(
        *[revise_overlong_bullet(bullets[idx], SPARSE_BULLET_CHAR_CEILING, jd_json) for bullets, idx in refs]
    )
    corrected_count = 0
    for (bullets, idx), new_bullet in zip(refs, revised):
        # Bounded to one attempt - if the model still didn't get it under
        # the ceiling, keep whichever version is actually shorter rather
        # than risk another round.
        if len(new_bullet) < len(bullets[idx]):
            bullets[idx] = new_bullet
            corrected_count += 1

    if corrected_count:
        logger.info("bullet_verifier: shortened %d overlong bullet(s)", corrected_count)


async def _weave_applied_skills(resume: Resume, applied_skills: List[str], jd_json: dict) -> None:
    """
    For each confirmed applied/methodology skill (classify_confirmed_skills'
    "applied" bucket - e.g. "Statistical Analysis", "KPI Development"),
    find the single most contextually plausible bullet across experience/
    projects/leadership and weave the skill into its wording, instead of
    adding it to the Technical Skills section where it doesn't read as a
    tool/keyword. Skipped entirely for a skill with no truthful fit - a
    confirmed skill that can't honestly attach to any bullet is left out
    rather than forced onto one.

    Sequential, not concurrent: two applied skills could plausibly target
    the same bullet, and each call needs to see the previous one's
    revision already applied so it doesn't get silently overwritten. Also
    tracks which bullets already received a woven skill and passes that
    along, so multiple applied skills spread across different bullets when
    more than one is a genuinely truthful fit, instead of defaulting to
    piling every skill onto whichever single bullet is the closest match.
    """
    if not applied_skills:
        return

    bullet_lists = _tailorable_bullet_lists(resume)
    woven_count = 0
    already_woven_indices: set = set()

    for skill in applied_skills:
        flat_bullets = [b for bullets in bullet_lists for b in bullets]
        if not flat_bullets:
            break

        result = await weave_skill_into_bullet(skill, flat_bullets, jd_json, already_woven_indices)
        if not result:
            continue

        flat_idx = result.get("bullet_index")
        revised = result.get("revised_bullet")
        if flat_idx is None or not revised or not (0 <= flat_idx < len(flat_bullets)):
            continue

        # Map the flat index back to its (bullets_list, local index) - same
        # flatten order flat_bullets was just built in.
        cursor = 0
        for bullets in bullet_lists:
            if flat_idx < cursor + len(bullets):
                bullets[flat_idx - cursor] = revised
                already_woven_indices.add(flat_idx)
                woven_count += 1
                break
            cursor += len(bullets)

    if woven_count:
        logger.info("skill_inference: wove %d applied skill(s) into bullets", woven_count)


async def render_pdf_with_underfill_backfill(
    resume: Resume, use_technical_skills: bool, jd_json: Optional[dict] = None
) -> bytes:
    """
    Render the resume, and if the post-render underfill check discovers the
    page actually needed a headline/summary after all - compact_mode's
    pre-render bullet-count guess said "full enough to skip it," but the
    real one-page render came back visibly underfull - generate one and
    re-render once more, reusing the render's own fill-ratio measurement
    instead of trusting the pre-render heuristic alone.

    Bullets are never re-tailored here, only this cheap headline/summary
    addition: re-running the main tailoring call a second time would
    roughly double tailoring latency for every resume that hits this edge
    case, for a page-fill problem that headline/summary content (plus the
    spacing loosening render_resume_pdf_ex already applied) already fixes.

    Mutates `resume.headline`/`resume.summary` in place when it generates
    them, so a caller returning this same resume object as JSON (not just
    the PDF bytes) stays consistent with what got rendered - and reverts
    that mutation if the backfilled render has to be discarded (see below),
    for the same reason.

    jd_json: forwarded to generate_headline_summary - JD-aware framing at
    tailor time, resume-only at reformat time (no JD).
    """
    pdf_bytes, needs_headline_summary = render_resume_pdf_ex(resume, use_technical_skills)

    if not needs_headline_summary:
        return pdf_bytes

    resume_json = json.loads(resume.model_dump_json())
    generated = await generate_headline_summary(resume_json, jd_json)

    if not generated.get("headline") and not generated.get("summary"):
        return pdf_bytes

    original_headline, original_summary = resume.headline, resume.summary
    resume.headline = generated.get("headline") or resume.headline
    resume.summary = generated.get("summary") or resume.summary

    backfilled_bytes, _ = render_resume_pdf_ex(resume, use_technical_skills)

    # Guard against the rare case where the added headline/summary content
    # pushes an already-borderline-full resume onto a 2nd page -
    # render_resume_pdf_ex's own overflow guard already tries
    # ultra_compact_mode first, but if it still doesn't fit in one page,
    # revert the content change (so a caller returning `resume` as JSON
    # alongside the PDF stays consistent with what actually got rendered)
    # and ship the original underfull-but-safely-one-page render instead.
    # A resume with some blank space at the bottom beats one that spilled
    # onto a second page.
    try:
        still_one_page = _count_pdf_pages(backfilled_bytes) == 1
    except Exception:
        still_one_page = False

    if not still_one_page:
        resume.headline, resume.summary = original_headline, original_summary
        return pdf_bytes

    return backfilled_bytes


async def tailor_resume(
    resume: Resume,
    jd: JobDescription,
    domain_info: dict,
    additional_hard_skills: Optional[List[str]] = None,
    additional_applied_skills: Optional[List[str]] = None,
    legacy_unclassified_skills: Optional[List[str]] = None,
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
    5. Auto-correct bullets that open weakly (a responsibility phrase or a
       gerund), that share an opening verb with another bullet on the
       resume, or (sparse resumes only) that exceed the calibrated
       character ceiling for the 3-line length target; weave any confirmed
       applied/methodology skills into bullet wording.
    6. Set compact_mode based on resume fullness

    Skills the candidate explicitly confirmed they have (e.g. from the
    inferred-skills picker) arrive pre-split by the caller into two groups,
    since skill_inference.suggest_plausible_skills_grouped already tags
    each suggestion tool-vs-methodology at the point it's suggested:
    - `additional_hard_skills` - tools/languages/certifications, merged into
      resume.skills BEFORE reordering/rewriting so they're treated as
      truthful: the LLM rewrite sees them as part of the resume's real
      skill list, and the bullet verifier's allowed-skill pool (read from
      the rewritten resume's skills afterward) includes them automatically
      - no verifier changes needed.
    - `additional_applied_skills` - methodologies/techniques, held back and
      woven into bullet wording instead, after tailoring finishes (step
      5d) - they don't read naturally as Technical Skills keywords.

    `legacy_unclassified_skills` - confirmed skills from a base_resumes row
    saved before the picker tagged tool-vs-methodology at suggestion time
    (inferred_skills was a flat, untyped list then). Classified here via
    classify_confirmed_skills and merged into the two groups above, so an
    older saved resume still works correctly without needing to be
    re-reformatted first.
    """
    hard_skills = list(additional_hard_skills or [])
    applied_skills = list(additional_applied_skills or [])

    if legacy_unclassified_skills:
        classified = await classify_confirmed_skills(legacy_unclassified_skills)
        hard_skills += classified.get("hard_skills") or []
        applied_skills += classified.get("applied_skills") or []

    if hard_skills:
        existing_lower = {s.lower() for s in resume.skills}
        for skill in hard_skills:
            if skill and skill.lower() not in existing_lower:
                resume.skills.append(skill)
                existing_lower.add(skill.lower())

    resume.compact_mode = compute_compact_mode(resume)

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

    # Preserve additional_info (certifications, languages, memberships, etc.)
    # exactly as parsed - factual credential/identity data, not something an
    # LLM rewrite should regenerate. Also fixes a real bug: the LLM's
    # structured-output reproduction of this field was unreliable - it would
    # sometimes silently drop it (e.g. certifications vanishing from the
    # rewritten resume), breaking downstream semantic-skill crediting that
    # depends on it even though the source data was always there.
    rewritten_resume.additional_info = resume.additional_info

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

    # Step 5a: auto-correct bullets that open weakly (independent per bullet)
    await _correct_weak_openers(rewritten_resume, jd_json)

    # Step 5b: auto-correct bullets that share an opening verb with another
    # bullet - run after weak-opener correction so it sees the final
    # opening verbs (weak-opener fixes can themselves change a verb)
    await _correct_repeated_opening_verbs(rewritten_resume, jd_json)

    # Step 5c: auto-correct bullets over the sparse-mode line-length
    # ceiling - only meaningful for sparse resumes; compact mode's own
    # char-match instruction already keeps bullets well under it
    if not rewritten_resume.compact_mode:
        await _correct_overlong_bullets(rewritten_resume, jd_json)

    # Step 5d: weave confirmed applied/methodology skills into bullet
    # wording rather than the Technical Skills section
    if applied_skills:
        await _weave_applied_skills(rewritten_resume, applied_skills, jd_json)

    # Step 6: Format skills (tools stay as is, concept phrases get title case)
    rewritten_resume.skills = format_skills_list(rewritten_resume.skills)

    # Step 7: Conditionally remove headline/summary if resume is too full
    rewritten_resume = conditionally_remove_headline_summary(rewritten_resume)

    return rewritten_resume
