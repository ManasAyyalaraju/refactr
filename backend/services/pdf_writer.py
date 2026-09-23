import os
import re
import subprocess
import tempfile
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from models.resume_models import Resume


TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")

_NON_TECH_QUALIFIERS = ("computer", "programming", "coding", "software", "tech")


def _dedupe_additional_info_against_technical_skills(resume: Resume) -> None:
    """
    Mutates resume.additional_info in place to avoid showing the same content
    twice when a technical_skills category already covers it (e.g. a
    "Certifications" category in TECHNICAL SKILLS vs. additional_info.certifications).
    Only call this when the TECHNICAL SKILLS section will actually be rendered.
    """
    if not resume.additional_info or not resume.technical_skills:
        return

    labels_lower = [cat.label.lower() for cat in resume.technical_skills]

    if any("certif" in l for l in labels_lower):
        resume.additional_info.certifications = []

    if any(
        "language" in l and not any(q in l for q in _NON_TECH_QUALIFIERS)
        for l in labels_lower
    ):
        resume.additional_info.languages = []

    if any("member" in l for l in labels_lower):
        resume.additional_info.professional_memberships = []


def _dedupe_additional_info_against_leadership(resume: Resume) -> None:
    """
    Mutates resume.additional_info.professional_memberships in place to drop
    any organization already covered by a resume.leadership entry. Same
    underlying organization can legitimately end up captured twice by the
    parser - e.g. an "Organizations: Financial Leadership Association" line
    under Education alongside a full "Financial Leadership Association (FLA)
    - Member" entry under Leadership/Extracurricular elsewhere in the resume
    - and the Leadership entry (rendered either as its own LEADERSHIP section
    or the minor-leadership line under Additional Information) already names
    the organization with strictly more detail (role, dates), so repeating
    it as a bare "Professional Memberships" line is pure duplication, not
    new information. Always safe to call, unlike the technical-skills dedup
    above which is gated on use_technical_skills.
    """
    if not resume.additional_info or not resume.additional_info.professional_memberships or not resume.leadership:
        return

    def _normalize_org(name: str) -> str:
        # Strip a trailing parenthetical abbreviation - "Financial Leadership
        # Association (FLA)" and "Financial Leadership Association" should
        # match as the same organization.
        return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip().lower()

    leadership_orgs = {_normalize_org(lead.organization) for lead in resume.leadership if lead.organization}

    resume.additional_info.professional_memberships = [
        m for m in resume.additional_info.professional_memberships
        if _normalize_org(m) not in leadership_orgs
    ]


_CONTROL_CHARS_RE = re.compile(
    "[" + "".join(chr(c) for c in range(0x00, 0x20) if chr(c) not in "\t\n\r") + chr(0x7F) + "]"
)


def escape_latex(text: str) -> str:
    """
    Escape special LaTeX characters in text.
    IMPORTANT: Backslash must be escaped FIRST before other characters!
    """
    if not text:
        return ""

    if not isinstance(text, str):
        text = str(text)

    # Strip C0/DEL control characters (never legitimate in resume text) -
    # pdflatex fails outright on a raw control byte like U+0002 rather than
    # rendering it as anything. These occasionally slip in as a rare LLM
    # sampling artifact in rewritten bullet text.
    text = _CONTROL_CHARS_RE.sub("", text)

    # Escape backslash first, then other characters
    # Order matters! Do backslash first so other escapes work correctly
    text = text.replace('\\', r'\textbackslash{}')
    
    # Then escape other special characters
    replacements = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
    }
    
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    
    return text


def ensure_url_scheme(url: str) -> str:
    """
    Prepend https:// when a URL has no scheme (e.g. "linkedin.com/in/x").
    Without this, hyperref's \\href classifies the link as a local file
    rather than a URL - which silently breaks click-through in most PDF
    viewers and also skips our custom link color for the same reason.
    """
    if not url:
        return ""
    if not isinstance(url, str):
        url = str(url)
    if "://" in url:
        return url
    return f"https://{url}"


# Custom Jinja2 environment for LaTeX
# Use VAR{} instead of {{ }} to avoid conflicts with LaTeX
env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    block_start_string='%{',
    block_end_string='%}',
    variable_start_string='VAR{',
    variable_end_string='}',
    comment_start_string='%#{',
    comment_end_string='#%}',
    trim_blocks=True,
    autoescape=False,
    auto_reload=True,  # Force template reload on every render
    cache_size=0,  # Disable template caching
)

# Add escape_latex as a filter
env.filters['escape_latex'] = escape_latex
env.filters['ensure_url_scheme'] = ensure_url_scheme


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    from io import BytesIO
    from PyPDF2 import PdfReader

    return len(PdfReader(BytesIO(pdf_bytes)).pages)


# A genuinely full page's content should reach at least this far down before
# the bottom margin - below it, the page reads as leaving an unintentional
# gap rather than a deliberately spaced layout. Chosen empirically (real
# examples underfilled to ~68-78%); not exact science, but the mechanism is
# self-correcting either way - see render_resume_pdf.
ROOMY_FILL_THRESHOLD = 0.85


def _content_fill_ratio(pdf_bytes: bytes) -> float:
    """
    Fraction (0-1) of page 1's height actually used by content, measured
    from the top down to the lowest character on the page. The fill-ratio
    counterpart to _count_pdf_pages's overflow check - same idea, opposite
    direction: detects a one-page render that's leaving the page visibly
    underfull instead of one that's overflowing it.
    """
    import pdfplumber
    from io import BytesIO

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[0]
        bottoms = [c["bottom"] for c in page.chars]
        if not bottoms:
            return 0.0
        return max(bottoms) / page.height


def render_resume_pdf(resume: Resume, use_technical_skills: bool = True) -> bytes:
    """
    Render a Resume model into a PDF bytes object using a LaTeX template.
    Uses pdflatex for professional typography and precise formatting.

    use_technical_skills: when False, renders the "regular" template - the
    categorized TECHNICAL SKILLS section is omitted even if the resume has
    parsed technical_skills data (falls back to the single-line skills format).

    Page fit is corrected by measuring the actual render and stepping one
    spacing tier at a time - compact_mode's bullet-count heuristic is only a
    starting guess, and even a correctly-compact-flagged resume can still
    render underfull once its bullets are compressed (observed directly: a
    24-bullet resume flagged compact_mode still left ~25-30% of the page
    blank). Two independent corrections, applied in sequence:
    1. Overflow: if compact_mode still doesn't fit one page, retry once with
       ultra_compact_mode - a tighter margin/spacing/font tier (not just a
       font nudge; a resume dense enough to overflow compact_mode needs
       real page real estate back, not just smaller glyphs).
    2. Underfill: if the (possibly still-compact) one-page render leaves the
       page visibly underfull (see _content_fill_ratio), step one tier
       looser - compact_mode off, or roomy_mode on - and keep that render
       only if it's still one page. Bounded to a single step per direction
       (mirrors the one-retry pattern used elsewhere, e.g. bullet_verifier's
       re-ask) rather than an open-ended search, and never touches bullet
       text or content - typography only, same principle as the
       short-wrapped-line fix. Content (e.g. headline/summary) is never
       added here or by any caller - a resume that was missing one going
       in stays that way; underfill is corrected with spacing alone.
    """
    render_target = resume.model_copy(deep=True)
    if use_technical_skills:
        _dedupe_additional_info_against_technical_skills(render_target)
    else:
        render_target.technical_skills = []
    _dedupe_additional_info_against_leadership(render_target)

    if render_target.target_pages >= 2:
        return _render_multi_page_pdf(render_target)

    pdf_bytes = _compile_resume_pdf(render_target)

    try:
        page_count = _count_pdf_pages(pdf_bytes)
    except Exception:
        # If page counting fails for any reason, ship the first render
        # rather than guess further.
        return pdf_bytes

    if page_count > 1:
        if render_target.compact_mode and not render_target.ultra_compact_mode:
            render_target.ultra_compact_mode = True
            pdf_bytes = _compile_resume_pdf(render_target)
        return pdf_bytes

    try:
        if _content_fill_ratio(pdf_bytes) < ROOMY_FILL_THRESHOLD:
            if render_target.compact_mode:
                render_target.compact_mode = False
            elif not render_target.roomy_mode:
                render_target.roomy_mode = True
            else:
                return pdf_bytes

            looser_pdf_bytes = _compile_resume_pdf(render_target)
            # Loosening spacing can push borderline content onto a 2nd page -
            # overflow is worse than an underfull page, so only keep it if
            # it's still one page.
            if _count_pdf_pages(looser_pdf_bytes) == 1:
                pdf_bytes = looser_pdf_bytes
    except Exception:
        pass

    return pdf_bytes


def _render_multi_page_pdf(render_target: Resume) -> bytes:
    """
    Render a resume whose page budget is 2 pages (it was uploaded as 2).

    Everything the one-page path does to force a fit is off here:
    ultra_compact_mode is reserved for dense ONE-page resumes and never
    applies, and neither does the underfill/roomy stepping (it measures
    page 1's fill, which is meaningless when content is meant to flow onto
    a second page). Content starts at the default spacing; only if it
    overflows the 2-page budget does it step down to compact_mode - the
    single bounded correction available - and if that still doesn't fit,
    the best render is shipped rather than compressing further.
    """
    render_target.compact_mode = False
    render_target.ultra_compact_mode = False
    render_target.roomy_mode = False

    pdf_bytes = _compile_resume_pdf(render_target)

    try:
        page_count = _count_pdf_pages(pdf_bytes)
    except Exception:
        return pdf_bytes

    if page_count > render_target.target_pages:
        render_target.compact_mode = True
        pdf_bytes = _compile_resume_pdf(render_target)

    return pdf_bytes


def _compile_resume_pdf(render_target: Resume) -> bytes:
    # Create a temporary directory for LaTeX compilation
    temp_dir = tempfile.mkdtemp()

    try:
        # Render the LaTeX template
        # LaTeX escaping is handled by the |escape_latex filter in the template
        template = env.get_template("resume_template.tex")
        latex_str = template.render(resume=render_target)
        
        # Write LaTeX file
        tex_path = os.path.join(temp_dir, "resume.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(latex_str)
        
        # Compile with pdflatex
        # Run twice to resolve references and get correct spacing
        for _ in range(2):
            result = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "-output-directory", temp_dir, tex_path],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=120  # Longer timeout for first-time package installation
            )
            
            if result.returncode != 0:
                # Check if pdflatex is installed
                if "not found" in result.stderr or "No such file" in result.stderr:
                    raise RuntimeError(
                        "pdflatex not found. Please install TeX Live or MiKTeX.\n"
                        "Linux: sudo apt-get install texlive-latex-base texlive-fonts-recommended\n"
                        "Mac: brew install --cask mactex-no-gui\n"
                        "Windows: Download and install MiKTeX from https://miktex.org/"
                    )
                
                # LaTeX compilation error
                log_path = os.path.join(temp_dir, "resume.log")
                error_msg = "LaTeX compilation failed."
                if os.path.exists(log_path):
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                        log_content = f.read()
                        # Extract error lines
                        error_lines = [line for line in log_content.split('\n') if '!' in line or 'Error' in line]
                        if error_lines:
                            error_msg += f"\n{chr(10).join(error_lines[:5])}"
                
                raise RuntimeError(error_msg)
        
        # Read the generated PDF
        pdf_path = os.path.join(temp_dir, "resume.pdf")
        if not os.path.exists(pdf_path):
            raise RuntimeError("PDF file was not generated by pdflatex")
        
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        
        return pdf_bytes
    
    finally:
        # Clean up temporary directory
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass  # Ignore cleanup errors



