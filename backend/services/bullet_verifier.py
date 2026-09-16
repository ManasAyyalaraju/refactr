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
import textwrap
from functools import lru_cache
from typing import Dict, List, Optional


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


_CONNECTOR_WORDS_RE = re.compile(r"^[A-Za-z]+(?:\s+[A-Za-z]+)?")


def extract_connector_phrase(clause: str) -> str:
    """
    Normalized signature (first two words) of an orphan-extend clause's
    opening connector, for duplicate-connector comparison across bullets -
    the same idea as extract_opening_verb above, but for the extend
    step's mid-sentence connector instead of a bullet's first word.
    ", which enabled the..." -> "which enabled"; " while ensuring..." ->
    "while ensuring". Two words, not one: nearly every clause starts with
    a small set of words ("which", "while", "ultimately"), so a one-word
    signature would flag "which enabled" and "which streamlined" as the
    same connector when they read as genuinely different - the second
    word is what actually distinguishes a real repeat ("which resulted in
    X" twice) from ordinary variety that happens to share an opener.
    """
    if not clause:
        return ""
    stripped = clause.strip().lstrip(",;:").strip()
    match = _CONNECTOR_WORDS_RE.match(stripped)
    return match.group(0).lower() if match else ""


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
# whole-PAGE fill ratio in pdf_writer.py's roomy_mode stepping. This
# character count is a calibrated proxy instead, grounded in two
# independent real-render measurements rather than assumed: (1) matching
# textwrap.wrap's output against confirmed last-line lengths (16/12/12/16
# chars) on four genuinely orphaned bullets from a real tailored PDF -
# single-line capacity measured at 124-127 chars, first real wrap at
# 133+, and 128 reproduced all four exactly; (2) independently
# re-confirmed via exact pdfplumber word-coordinate measurement across 15
# real wrapped lines in a different render (avg 127.87 chars, range
# 121-137). This applies to compact_mode, sparse, and roomy_mode alike -
# all three render at the same 10pt font (resume_template.tex only
# changes margins/spacing between them, never font size) - so a single
# constant covers them. ultra_compact_mode's smaller 9.3pt font measures
# ~139 chars/line instead, but that flag is only ever set during PDF
# rendering, strictly after every bullet-correction step in tailor_engine.py
# has already run and returned - there's currently no code path where a
# 9.3pt-aware value would actually be read, so this stays a single
# constant rather than a font-size-branching one until a correction step
# runs post-render.
CHARS_PER_LINE_ESTIMATE = 128
ORPHAN_LAST_LINE_CHAR_FLOOR = 40

# "~2 lines preferred" / "~3 lines max" targets for sparse-mode bullet
# generation, computed off CHARS_PER_LINE_ESTIMATE with a floor + 15 chars
# past the 1-line boundary, 10 chars short of the next wrap boundary - so
# a bullet written to hit this target doesn't land right back in orphan
# territory.
# The previous (160, 220)/285 values were computed off a since-disproven
# 95 chars/line assumption: a bullet at 160 chars (the bottom of that old
# "preferred" range) wrapped to a last line of only ~32 chars under the
# real 128 chars/line - already under the 40-char orphan floor - and even
# the old 285 ceiling produced a ~29-char final line. The old targets were
# themselves a source of orphan lines, not just imprecise.
SPARSE_BULLET_CHAR_TARGET = (
    CHARS_PER_LINE_ESTIMATE + ORPHAN_LAST_LINE_CHAR_FLOOR + 15,  # 183
    2 * CHARS_PER_LINE_ESTIMATE - 10,  # 246
)
SPARSE_BULLET_CHAR_CEILING = 3 * CHARS_PER_LINE_ESTIMATE  # 384 - 3-line hard ceiling


def find_overlong_bullets(bullets: List[str], char_ceiling: int = SPARSE_BULLET_CHAR_CEILING) -> List[int]:
    """
    Indices of bullets that exceed a hard character ceiling - the calibrated
    proxy above for exceeding a target line count.
    """
    return [i for i, b in enumerate(bullets) if b and len(b) > char_ceiling]


def find_orphan_line_bullets(
    bullets: List[str],
    chars_per_line: int = CHARS_PER_LINE_ESTIMATE,
    floor: int = ORPHAN_LAST_LINE_CHAR_FLOOR,
) -> List[int]:
    """
    Indices of bullets whose estimated final wrapped line is under `floor`
    characters - i.e. it wraps at all (2+ lines) but leaves only a word or
    two dangling on its own line. textwrap.wrap greedily breaks at word
    boundaries the same way LaTeX's line breaker does, so wrapping at
    CHARS_PER_LINE_ESTIMATE is a reasonable proxy for where the real PDF
    will actually break.
    """
    flagged = []
    for i, b in enumerate(bullets):
        if not b:
            continue
        wrapped = textwrap.wrap(b, width=chars_per_line)
        if len(wrapped) < 2:
            continue  # fits on one line - nothing to wrap
        if len(wrapped[-1]) < floor:
            flagged.append(i)
    return flagged


def orphan_extend_is_valid(
    original: str, candidate: str, chars_per_line: int = CHARS_PER_LINE_ESTIMATE
) -> bool:
    """
    True if an extend-strategy candidate actually fixed the orphan without
    spilling onto an extra wrapped line - find_orphan_line_bullets alone
    isn't enough here, since a candidate that grew past the original line
    count could land on a comfortably-full NEW last line and pass that
    check while still silently growing the bullet by a whole line (which
    shrinking, only ever making bullets shorter, could never do).
    """
    if find_orphan_line_bullets([candidate], chars_per_line=chars_per_line):
        return False
    orig_lines = len(textwrap.wrap(original, width=chars_per_line)) or 1
    cand_lines = len(textwrap.wrap(candidate, width=chars_per_line)) or 1
    return cand_lines <= orig_lines


def fit_extension_alternative(
    original: str,
    alternatives: List[str],
    chars_per_line: int = CHARS_PER_LINE_ESTIMATE,
    exclude_connectors: Optional[set] = None,
) -> Optional[tuple]:
    """
    Deterministically pick the longest of a ranked list of complete
    continuation alternatives (llm_client.generate_extension_alternatives
    - longest/most-detailed first) that actually resolves the orphan
    without spilling onto an extra line, AND (when `exclude_connectors`
    is given) doesn't open with a connector phrase already used by an
    earlier bullet in this pass - same idea as find_duplicate_opening_verbs
    but for the extend step's mid-sentence connector. Falls back to the
    longest valid alternative regardless of its connector if every valid
    option collides with an excluded one, rather than leaving a bullet
    un-extended just to avoid a repeat.

    Returns (fitted_bullet, connector_phrase) so the caller can grow its
    own used-connectors set across bullets, or None if nothing fits at
    all. This is the fitting decision made locally instead of gambling on
    the model hitting a character target itself - live testing of the old
    single-target design showed successes and failures both scattered
    widely around the target (246 to 282 chars against a 246 ceiling), so
    instead of retrying and hoping, this tries each pre-generated
    alternative in order and keeps the first (longest, most
    detail-preserving) one that fits.

    Each alternative is a complete clause, never a word-level fragment,
    so this never cuts a sentence mid-thought - it only ever selects
    between whole, already-finished options the model provided.

    Joining is done here, not trusted to the model's own formatting - an
    alternative that starts with a word instead of its own punctuation
    (e.g. "while continuously..." instead of ", which...") would
    otherwise glue directly onto the original with no space
    ("optimizationwhile..."), seen live in testing.
    """
    exclude_connectors = exclude_connectors or set()
    base = original.rstrip()
    if base.endswith("."):
        base = base[:-1]

    valid = []  # (candidate, connector), in the given longest-first order
    for alt in alternatives:
        if not alt:
            continue
        alt_clean = alt.strip()
        if not alt_clean:
            continue
        separator = "" if alt_clean[0] in ",;:" else " "
        candidate = base + separator + alt_clean
        if orphan_extend_is_valid(original, candidate, chars_per_line=chars_per_line):
            valid.append((candidate, extract_connector_phrase(alt_clean)))

    if not valid:
        return None

    for candidate, connector in valid:
        if connector not in exclude_connectors:
            return (candidate, connector)

    # Every valid alternative repeats an already-claimed connector -
    # accept the repeat rather than leave the bullet un-extended.
    return valid[0]
