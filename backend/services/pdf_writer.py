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


def render_resume_pdf(resume: Resume, use_technical_skills: bool = True) -> bytes:
    """
    Render a Resume model into a PDF bytes object using a LaTeX template.
    Uses pdflatex for professional typography and precise formatting.

    use_technical_skills: when False, renders the "regular" template - the
    categorized TECHNICAL SKILLS section is omitted even if the resume has
    parsed technical_skills data (falls back to the single-line skills format).

    If compact_mode is on and the rendered PDF still doesn't fit on one page,
    retries once with ultra_compact_mode (a small font-size nudge) rather than
    guessing upfront whether a given resume needs it - so the extra
    compression only ever gets applied to resumes that actually overflow.
    """
    render_target = resume.model_copy(deep=True)
    if use_technical_skills:
        _dedupe_additional_info_against_technical_skills(render_target)
    else:
        render_target.technical_skills = []

    pdf_bytes = _compile_resume_pdf(render_target)

    if render_target.compact_mode and not render_target.ultra_compact_mode:
        try:
            if _count_pdf_pages(pdf_bytes) > 1:
                render_target.ultra_compact_mode = True
                pdf_bytes = _compile_resume_pdf(render_target)
        except Exception:
            # If page counting fails for any reason, fall back to the
            # already-successful first render rather than blocking the user.
            pass

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



