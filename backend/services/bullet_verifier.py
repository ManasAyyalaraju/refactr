"""
Deterministic quality/truthfulness guardrails for tailored bullets. No LLM
calls here - each check is a plain string/regex test; llm_client.py owns the
matching correction call for anything a check flags.

Truthfulness scope is intentionally narrow: general fabrication detection is
unbounded and fuzzy. What actually happens in practice is the model
borrowing a JD-desired skill the candidate doesn't have, to inflate the
match - so that's the one thing find_unauthorized_terms checks for: does a
tailored bullet introduce a JD skill that wasn't in the original bullet and
isn't anywhere in the candidate's own skill lists?
"""
import re
from functools import lru_cache
from typing import Dict, List


@lru_cache(maxsize=512)
def _skill_pattern(skill: str) -> re.Pattern:
    """
    Build a match pattern for a skill string that's safe for symbol-heavy
    names like "C++", "Node.js", "C#" - re.escape() so those symbols aren't
    treated as regex metacharacters, and custom alphanumeric-only boundaries
    since \\b doesn't reliably anchor around trailing +/./#. Allows a simple
    trailing s/es plural.
    """
    escaped = re.escape(skill.strip())
    return re.compile(
        rf"(?<![A-Za-z0-9]){escaped}(?:s|es)?(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


def _contains_skill(text: str, skill: str) -> bool:
    if not skill or not skill.strip() or not text:
        return False
    return bool(_skill_pattern(skill).search(text))


def find_unauthorized_terms(
    original_bullet: str,
    tailored_bullet: str,
    jd_skills: List[str],
    resume_skills: List[str],
    resume_technical_skills: List[str],
) -> List[str]:
    """
    Return the JD skills that appear in `tailored_bullet` but not in
    `original_bullet` nor anywhere in the candidate's own skill lists.
    """
    allowed_text = " ".join([*resume_skills, *resume_technical_skills])
    flagged = []

    for skill in jd_skills:
        if not skill or not skill.strip():
            continue
        if not _contains_skill(tailored_bullet, skill):
            continue  # not introduced in the tailored version
        if _contains_skill(original_bullet, skill):
            continue  # was already there - not a new claim
        if _contains_skill(allowed_text, skill):
            continue  # candidate actually lists this skill elsewhere
        flagged.append(skill)

    return flagged


def verify_bullets(
    original_bullets: List[str],
    tailored_bullets: List[str],
    jd_skills: List[str],
    resume_skills: List[str],
    resume_technical_skills: List[str],
) -> Dict[int, List[str]]:
    """
    Check each tailored bullet against its original. Returns a map of
    bullet index -> flagged JD-skill terms, for bullets with a violation.
    """
    violations: Dict[int, List[str]] = {}

    for i, (original, tailored) in enumerate(zip(original_bullets, tailored_bullets)):
        flagged = find_unauthorized_terms(
            original, tailored, jd_skills, resume_skills, resume_technical_skills
        )
        if flagged:
            violations[i] = flagged

    return violations


# Phrases that signal a bullet is describing a duty rather than an
# accomplishment - checked as a prefix match, not a substring match,
# since "Responsible for" mid-sentence isn't the same failure as opening
# with it.
_WEAK_OPENER_PHRASES = (
    "responsible for",
    "in charge of",
    "duties included",
    "duties include",
    "tasked with",
    "worked on",
    "worked with",
    "helped with",
    "helped to",
    "assisted with",
    "assisted in",
    "participated in",
    "involved in",
    "was responsible",
    "charged with",
)

_GERUND_FIRST_WORD_RE = re.compile(r"^[A-Za-z]+ing$")


def has_weak_opener(bullet: str) -> bool:
    """
    True if a bullet opens with a passive/responsibility phrase (e.g.
    "Responsible for...") or a gerund as its first word (e.g. "Managing...",
    "Leading...") instead of a strong action verb. Intentionally just this
    one narrow pattern - not a general grammar checker - since it's the
    specific failure the "begin with an action verb" rule is meant to catch.
    """
    if not bullet or not bullet.strip():
        return False
    text = bullet.strip().lower()
    if any(text.startswith(phrase) for phrase in _WEAK_OPENER_PHRASES):
        return True
    words = text.split()
    first_word = words[0] if words else ""
    first_word = re.sub(r"[^a-z]", "", first_word)
    return bool(_GERUND_FIRST_WORD_RE.match(first_word))


def find_weak_opener_bullets(bullets: List[str]) -> List[int]:
    """Indices of bullets (in the given order) that open weakly."""
    return [i for i, b in enumerate(bullets) if has_weak_opener(b)]


def extract_opening_verb(bullet: str) -> str:
    """
    First word of a bullet, normalized (letters only, lowercased) for
    duplicate-opening-verb comparison. Deliberately literal - "Developed"
    and "Develop" are treated as different verbs, since the goal is just to
    catch two bullets that open with the exact same word.
    """
    if not bullet or not bullet.strip():
        return ""
    first_word = bullet.strip().split(None, 1)[0]
    return re.sub(r"[^A-Za-z]", "", first_word).lower()


def find_duplicate_opening_verbs(bullets: List[str]) -> Dict[str, List[int]]:
    """
    Map each opening verb shared by 2+ bullets to the indices (in the given
    order) of every bullet that opens with it. Verbs used exactly once are
    omitted - nothing to fix there.
    """
    by_verb: Dict[str, List[int]] = {}
    for i, bullet in enumerate(bullets):
        verb = extract_opening_verb(bullet)
        if not verb:
            continue
        by_verb.setdefault(verb, []).append(i)
    return {verb: idxs for verb, idxs in by_verb.items() if len(idxs) > 1}


# Nothing in this pipeline renders an individual bullet to measure its
# actual wrapped line count - the only real rendered measurement is the
# whole-PAGE fill ratio in pdf_writer.py's roomy_mode stepping. These
# character counts are a calibrated proxy instead: ~95 chars/line, derived
# from resume_template.tex's 9.3pt font and ~7.3in effective bullet width
# (0.5in margins, 14pt itemize indent) and cross-checked against
# llm_client.py's pre-existing compact-mode compression targets, where a
# bullet around 190 chars was already being treated as the point it starts
# wrapping onto a 3rd line. Approximate, not exact font-metric math.
CHARS_PER_LINE_ESTIMATE = 95
SPARSE_BULLET_CHAR_TARGET = (160, 220)  # ~2 lines - the preferred range
SPARSE_BULLET_CHAR_CEILING = 3 * CHARS_PER_LINE_ESTIMATE  # ~285 - 3-line hard ceiling


def find_overlong_bullets(bullets: List[str], char_ceiling: int = SPARSE_BULLET_CHAR_CEILING) -> List[int]:
    """
    Indices of bullets that exceed a hard character ceiling - the calibrated
    proxy above for exceeding a target line count.
    """
    return [i for i, b in enumerate(bullets) if b and len(b) > char_ceiling]
