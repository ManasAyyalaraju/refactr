from typing import Optional, Tuple

import pdfplumber

from core.exceptions import UnreadablePdfError

# A resume's name/title/contact block almost always spans the full page
# width even on an otherwise two-column template (Enhancv-style: sidebar
# starts below the header) - excluding this top slice from gutter detection
# avoids a full-width header being mistaken for "no gutter exists here".
_HEADER_FRACTION = 0.12
# How wide a genuinely empty vertical band must be to count as a column
# gutter, in points - wide enough that normal text spacing/kerning inside a
# single-column resume can't produce a false positive.
_MIN_GUTTER_WIDTH = 15.0
# Only look for a gutter within the middle band of the page, away from the
# outer margins - the page's own left/right margins are themselves empty
# vertical bands and would otherwise be misdetected as a "gutter".
_SEARCH_MARGIN = 0.12


def _find_column_gutter(page) -> Optional[Tuple[float, float, float]]:
    """
    Detect a two-column layout (e.g. Enhancv-style resumes with a sidebar)
    by finding the widest vertical band, below the header, that no
    character crosses anywhere on the page. Returns (gutter_x0, gutter_x1,
    header_bottom) if found, else None for an ordinary single-column resume.

    Naive text extraction (page.extract_text()) has no notion of columns -
    it joins text purely by vertical position, so a sidebar item at the
    same height as a main-column bullet gets concatenated onto that
    bullet's line, corrupting both. Splitting the page into a header slice
    plus a left/right column and extracting each separately avoids that.
    """
    header_bottom = page.height * _HEADER_FRACTION
    chars = [c for c in page.chars if c["top"] >= header_bottom]
    if len(chars) < 20:
        return None

    step = 2.0
    x_min = page.width * _SEARCH_MARGIN
    x_max = page.width * (1 - _SEARCH_MARGIN)

    blocked = set()
    for ch in chars:
        start = int(ch["x0"] // step)
        end = int(ch["x1"] // step) + 1
        blocked.update(range(start, end + 1))

    i_min, i_max = int(x_min // step), int(x_max // step)
    best_len, best_start = 0, None
    run_start = None
    for i in range(i_min, i_max + 1):
        if i not in blocked:
            if run_start is None:
                run_start = i
        elif run_start is not None:
            run_len = i - run_start
            if run_len > best_len:
                best_len, best_start = run_len, run_start
            run_start = None
    if run_start is not None:
        run_len = i_max + 1 - run_start
        if run_len > best_len:
            best_len, best_start = run_len, run_start

    if best_start is None or best_len * step < _MIN_GUTTER_WIDTH:
        return None
    return (best_start * step, (best_start + best_len) * step, header_bottom)


def _extract_page_text(page) -> str:
    gutter = _find_column_gutter(page)
    if not gutter:
        return page.extract_text() or ""

    gutter_x0, gutter_x1, header_bottom = gutter
    px0, py0, px1, py1 = page.bbox
    # Clamp against the page's own bbox - floating-point rounding between
    # page.height/page.width and the page's actual bbox can otherwise push
    # a crop a fraction of a point outside it, which pdfplumber rejects.
    gutter_x0 = max(px0, min(gutter_x0, px1))
    gutter_x1 = max(px0, min(gutter_x1, px1))
    header_bottom = max(py0, min(header_bottom, py1))

    header = page.crop((px0, py0, px1, header_bottom))
    left = page.crop((px0, header_bottom, gutter_x0, py1))
    right = page.crop((gutter_x1, header_bottom, px1, py1))
    parts = [header.extract_text() or "", left.extract_text() or "", right.extract_text() or ""]
    return "\n".join(p for p in parts if p)


def extract_text_from_pdf(path: str) -> str:
    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text += _extract_page_text(page) + "\n"
    return text.strip()


def extract_text_from_pdf_or_raise(path: str) -> str:
    """Same as extract_text_from_pdf, but raises UnreadablePdfError when the
    PDF has no real text layer (e.g. a scanned/flattened image PDF) instead
    of silently returning an empty string - used both by the resume parser
    and by the standalone pre-upload validation check, so both paths reject
    the same PDFs the same way.

    A real resume's extracted text is always at least a few dozen characters
    (name + contact line alone clears this).
    """
    raw_text = extract_text_from_pdf(path)
    if len(raw_text.strip()) < 20:
        raise UnreadablePdfError(
            "Your current resume is a scanned image, not text. Please upload "
            "a PDF with actual text instead of an image."
        )
    return raw_text
