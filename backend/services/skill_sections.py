"""
Deterministic detection of a skills section laid out as category HEADINGS,
each followed by a paragraph of comma-separated skills:

    Cloud & Enterprise Architecture            <- bold heading line
    Azure, AWS, GCP (IaaS/PaaS), Azure Migrate, cloud-native architecture, ...

The LLM parser doesn't recognize this layout (it only handles "Label: a, b"):
it files the headings as if they were skills, drops the category structure,
and (about half the time) drops the tool names inside parentheses. The layout
is easy to detect from the PDF itself - headings are bold, their paragraphs
are regular weight - so it's handled here without the LLM, which also makes
the result identical on every run.
"""
import re
from typing import List, Optional, Tuple

import pdfplumber

from services.pdf_reader import _find_column_gutter

# A run this long of heading+paragraph pairs is a categorized skills section;
# fewer is too weak a signal (a lone bold line followed by a comma-rich line
# is also what a job title above a "Company, City, State" line looks like).
MIN_CATEGORIES = 3
_MAX_HEADING_WORDS = 8
_MIN_PARAGRAPH_COMMAS = 2
_MAX_MEDIAN_ITEM_WORDS = 4
_MAX_ITEM_WORDS = 12
_MARKER = re.compile(r"^\s*(?:[•●▪■◦∙·*\-–]|\(cid:\d+\))")


def _is_bold(fontname: str) -> bool:
    name = (fontname or "").lower()
    return any(tag in name for tag in ("bold", "black", "heavy", "semibold", "demi"))


def _line_is_bold(line) -> bool:
    letters = [c for c in line["chars"] if c["text"].strip()]
    if not letters:
        return False
    return sum(_is_bold(c.get("fontname", "")) for c in letters) / len(letters) >= 0.9


def split_top_level_commas(text: str) -> List[str]:
    """Split on commas that are not inside parentheses."""
    parts, depth, current = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def atomize_skill(item: str) -> List[str]:
    """
    "AI/ML libraries (pandas, scikit-learn)" -> ["AI/ML libraries", "pandas",
    "scikit-learn"]. Tool names listed inside parentheses are real keywords
    in their own right and must not be lost with the parenthetical.
    """
    inners = re.findall(r"\(([^()]*)\)", item)
    if not inners:
        return [item.strip()]
    head = re.sub(r"\s+", " ", re.sub(r"\([^()]*\)", "", item)).strip()
    tokens = [head] if head else []
    for inner in inners:
        tokens.extend(t.strip() for t in inner.split(",") if t.strip())
    return tokens


def extract_heading_skill_categories(path: str) -> List[Tuple[str, List[str]]]:
    """
    Returns [(category label, [atomic skill items])] for a categorized skills
    section in heading-then-paragraph layout, or [] when the resume doesn't
    have one. Only single-column pages are considered - on a multi-column
    page, lines from different columns interleave and adjacency means nothing.
    """
    best: List[Tuple[str, str]] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            if _find_column_gutter(page) is not None:
                continue
            lines = page.extract_text_lines(strip=True, return_chars=True)
            run: List[Tuple[str, str]] = []
            run_end = -1  # index of the line right after the last block in `run`
            i = 0
            while i < len(lines):
                block = _read_block(lines, i)
                if block is None:
                    i += 1
                    continue
                heading, paragraph, end = block
                if run and i == run_end:
                    run.append((heading, paragraph))
                else:
                    run = [(heading, paragraph)]
                run_end = end
                if len(run) > len(best):
                    best = list(run)
                i = end

    if len(best) < MIN_CATEGORIES:
        return []

    categories: List[Tuple[str, List[str]]] = []
    for heading, paragraph in best:
        items: List[str] = []
        seen = set()
        for raw_item in split_top_level_commas(paragraph):
            for atom in atomize_skill(raw_item):
                if atom.lower() not in seen:
                    seen.add(atom.lower())
                    items.append(atom)
        categories.append((heading, items))
    return categories


def _read_block(lines, i: int) -> Optional[Tuple[str, str, int]]:
    """A bold, comma-free heading line at `i` followed by regular-weight
    lines that together form a comma-separated list. Returns (heading,
    paragraph, index of the first line after the block) or None."""
    heading_line = lines[i]
    heading = heading_line["text"].strip()
    if not (
        _line_is_bold(heading_line)
        and "," not in heading
        and 1 <= len(heading.split()) <= _MAX_HEADING_WORDS
        and not _MARKER.match(heading)
    ):
        return None
    j = i + 1
    paragraph: List[str] = []
    while j < len(lines) and not _line_is_bold(lines[j]) and not _MARKER.match(lines[j]["text"]):
        paragraph.append(lines[j]["text"].strip())
        j += 1
    joined = " ".join(paragraph)
    if paragraph and _looks_like_skill_list(joined):
        return heading, joined, j
    return None


_SENTENCE_BREAK = re.compile(r"[a-z]{2}[.!?]\s+[A-Z]")


def _looks_like_skill_list(paragraph: str) -> bool:
    """A comma-separated list of short items - not prose that merely
    contains commas (a summary or philosophy paragraph under a bold
    heading would otherwise qualify)."""
    items = split_top_level_commas(paragraph)
    if len(items) - 1 < _MIN_PARAGRAPH_COMMAS:
        return False
    if _SENTENCE_BREAK.search(paragraph):
        return False
    word_counts = sorted(len(item.split()) for item in items)
    median = word_counts[len(word_counts) // 2]
    return median <= _MAX_MEDIAN_ITEM_WORDS and word_counts[-1] <= _MAX_ITEM_WORDS
