import re
from datetime import datetime
from core.config import settings
from services.pdf_reader import extract_text_from_pdf_or_raise
from models.resume_models import Resume
from services.llm_client import client, _extract_parsed


ENRICHMENT_PATTERNS = {
    "next.js": r"\bnext\.?js\b",
    "typescript": r"\btypescript\b",
    "javascript": r"\bjavascript\b",
    "html5": r"\bhtml5\b",
    "css": r"\bcss\b",
    "react": r"\breact\b",
    "node.js": r"\bnode\.?js\b",
    "python": r"\bpython\b",
    "sql": r"\bsql\b",
    "postgresql": r"\bpostgresql\b|\bpostgres\b",
    "mysql": r"\bmysql\b",
    "jira": r"\bjira\b",
    "tableau": r"\btableau\b",
    "power bi": r"\bpower\s*bi\b",
    "excel": r"\bexcel\b",
    "loRa": r"\blora\b",
}


def _merge_and_dedupe_skills(existing: list[str], new_items: list[str]) -> list[str]:
    merged: list[str] = []
    seen = set()
    for item in [*(existing or []), *(new_items or [])]:
        clean = item.strip()
        if not clean:
            continue
        key = clean.lower()
        if key not in seen:
            seen.add(key)
            merged.append(clean)
    return merged


def _enrich_skills_from_text(raw_text: str, current_skills: list[str]) -> list[str]:
    if not raw_text:
        return current_skills

    found = []
    lower_text = raw_text.lower()
    for canonical, pattern in ENRICHMENT_PATTERNS.items():
        if re.search(pattern, lower_text, re.IGNORECASE):
            found.append(canonical)

    return _merge_and_dedupe_skills(current_skills, found)


def format_date(date_str: str) -> str:
    """
    Convert date from YYYY-MM format to "Month YYYY" format.
    If already in readable format, return as-is.
    Examples:
    - "2026-12" -> "December 2026"
    - "2021-04" -> "April 2021"
    - "December 2026" -> "December 2026" (unchanged)
    """
    if not date_str or date_str == "Present":
        return date_str

    # Check if already in readable format (contains month name)
    month_names = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    if any(month in date_str for month in month_names):
        return date_str

    # Try to parse YYYY-MM format
    match = re.match(r'(\d{4})-(\d{2})', date_str)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        try:
            date_obj = datetime(year, month, 1)
            return date_obj.strftime("%B %Y")
        except ValueError:
            return date_str

    return date_str


async def parse_pdf_resume_to_json(file_path: str) -> Resume:
    """
    1) Extract raw text from the PDF
    2) Ask the LLM to convert it into the Resume structure (schema enforced
       via structured outputs - response_format=Resume - so the shape itself
       doesn't need to be spelled out in the prompt, only the semantic
       extraction rules below)
    3) Run deterministic post-processing (skill enrichment, date formatting)
    """
    if not client:
        raise RuntimeError("OpenAI client not configured - OPENAI_API_KEY is missing.")

    raw_text = extract_text_from_pdf_or_raise(file_path)

    prompt = f"""
You are a resume parser.

I will give you RAW TEXT extracted from a PDF resume. Convert it into the resume structure, following these rules:

- Extract ONLY information that actually appears in the resume text.
- Do NOT invent jobs, dates, companies, or skills.
- If a field is missing, leave it empty.
- **NAME EXTRACTION**: The "name" field should be extracted from the very top of the resume, typically the largest text at the beginning. Extract the COMPLETE full name EXACTLY as it appears, including ALL letters. Do NOT truncate or skip any characters. If the name appears incomplete or garbled in the text extraction, check the email address for clues (e.g., if email is "Aswath.Manu@utdallas.edu", the name is likely "Aswath Manu" not "Swath Manu"). Examples of CORRECT extraction: "Aswath Manu", "John Smith", "Maria Garcia-Lopez".
- "education" MUST be a list (it can have just 1 item, or empty list if no education section).
- **EDUCATION PARSING**: Separate degree and major into two fields:
  * "degree": The degree type (e.g., "Bachelor of Science", "Master of Arts", "PhD")
  * "major": The field of study/major (e.g., "Computer Science", "Business Administration", "Biology")
  * If the resume shows "Bachelor of Science in Computer Science" or "B.S., Computer Science", split it into degree="Bachelor of Science" and major="Computer Science"
- If a GPA is present, put it in the "gpa" field as a short string (e.g. "3.6"). If no GPA is present, leave "gpa" empty.
- If an education entry lists a "Relevant Coursework" (or "Related Coursework") line, put the course names in that education entry's "relevant_coursework" field as a single comma-separated string, exactly as listed. If not present, leave it empty.
- DATE FORMATTING: Format all dates as "Month YYYY" (e.g., "December 2026", "October 2025", "April 2021"). Do NOT use "YYYY-MM" format. If only year is available, use just "YYYY" - do NOT invent a month. For example, if the source shows "2013 - 2021" with no month anywhere, output start_date="2013" and end_date="2021", NOT "January 2013"/"December 2021". Never default a missing month to January or December.
- **PROJECTS SECTION**: The "projects" field should include content from sections labeled as:
  * "PROJECTS" or "Projects"
  * "EXTRACURRICULAR ACTIVITIES" or "Extracurricular Activities"
  * Any similar section that describes projects, activities, or initiatives (not work experience)
  * If the resume has "EXTRACURRICULAR ACTIVITIES" instead of "PROJECTS", map that content to the "projects" field
- "projects" is OPTIONAL - only include if the resume has a projects or extracurricular activities section. If no projects, use empty list.
- **PROJECT DATE/SEMESTER EXTRACTION**: For projects, extract ANY date or semester information (e.g., "Fall 2025", "Spring 2024", "September 2025", "December 2023", etc.) and put it in the "semester" field. Dates can be in "Month YYYY" format (like "September 2025") or semester format (like "Fall 2025").
- **CRITICAL**: Do NOT include dates or semesters in the "role" field. The "role" field should only contain the role/title (e.g., "Officer/Education Lead"), and the date/semester should ALWAYS go in the "semester" field. If a project entry shows "Organization Name – Role – Date", extract the date separately into the "semester" field, not as part of the role.
- **CRITICAL**: "name" and "role" must NEVER be the same text. "name" is the organization/club/project name (typically the bolded heading the entry starts with); "role" is the candidate's title within it (e.g. "Financial Analyst", "President"). A raw-text layout can flatten these onto adjacent lines in a way that makes the role look like it belongs in both fields - if you find yourself about to output identical text for "name" and "role", that's a sign you've misread the entry: look again for the actual organization/project name elsewhere in that entry's text (it is a different string, not the role repeated).
- **LEADERSHIP SECTION**: The "leadership" field should include content from sections labeled as:
  * "LEADERSHIP" or "Leadership"
  * "LEADERSHIP EXPERIENCE" or "Leadership Experience"
  * "LEADERSHIP EXPERIENCE AND ACTIVITIES" or "Leadership Experience and Activities"
  * "LEADERSHIP ACTIVITIES" or similar variations
  * Any section that describes leadership roles in organizations, clubs, or groups
  * Examples: President of a club, Founder of an organization, Officer positions, Committee leadership, etc.
- "leadership" is OPTIONAL - only include if the resume has a dedicated leadership section. If no leadership section, use empty list.
- **LEADERSHIP vs VOLUNTEER WORK**: Distinguish between leadership roles and volunteer work:
  * LEADERSHIP: Roles with titles like President, Founder, Officer, Director, Chair, Lead, etc. in organizations/clubs
  * VOLUNTEER WORK: Actual volunteer service activities (food banks, community service, tutoring, charity work)
  * If a position has both leadership and volunteer aspects, classify as "leadership" if it emphasizes a leadership role
- **VOLUNTEER WORK CLASSIFICATION**: Only classify entries as "volunteer_work" if they are actual volunteer activities (e.g., volunteering at a food bank, community service, charity work). Do NOT classify the following as volunteer work:
  * Professional organizations or associations (e.g., "Financial Leadership Association", "IEEE", "ACM")
  * Student clubs or academic organizations (unless explicitly described as volunteer work)
  * Professional memberships - these should go in "additional_info.professional_memberships" instead
  * Extracurricular activities that are not explicitly volunteer work - these should go in "projects" instead
- "volunteer_work", "awards", "publications", and "leadership" are OPTIONAL - only include if present in the resume. Use empty lists if not present.
- SKILLS EXTRACTION: Extract ALL skills, tools, technologies, and competencies mentioned anywhere in the resume (do NOT limit to a dedicated skills section):
  * From dedicated skills sections (e.g., "Skills", "Technical Skills", "Computer Skills", "Core Competencies")
  * From experience bullet points (e.g., "Used Python and SQL to...")
  * From project descriptions (e.g., "Next.js", "TypeScript", "PostgreSQL", "Jira", "Tableau", "Power BI")
  * From education coursework
  * Include: programming languages, software, frameworks, methodologies, tools, platforms, etc.
  * Put all extracted skills in the top-level "skills" array (do NOT leave this empty if skills appear outside the dedicated section).
- "additional_info.computer_skills" or "additional_info.technical_skills": If there's a dedicated skills section in the resume, extract the raw text here (as a single string, preserving separators like commas, pipes, etc.). This is separate from the structured "skills" array.
- **TECHNICAL SKILLS SECTION (categorized)**: If the resume has a dedicated skills section formatted as CATEGORIZED bullets or lines (e.g. "Computer Software: Excel, Tableau, Jira" / "Computer Languages: Python, SQL, Java" / "Frameworks: React, Django"), extract each category as one object in "technical_skills" with:
  * "label": the category name EXACTLY as written in the resume (e.g. "Computer Software", "Computer Languages", "Certifications") — do NOT invent or rename categories, and do NOT merge multiple categories into one.
  * "items": the comma-separated values after the colon, split into a list, each trimmed of whitespace.
  * Preserve the EXACT ORDER the categories appear in the resume.
  * If the skills section is just a flat, uncategorized list (no "Label:" prefixes), leave "technical_skills" as an empty list — the flat list still goes in "skills" as usual.
- "additional_info.certifications" MUST be a list of strings (one cert per element).
- "additional_info.languages" MUST be a list of strings (one language per element).
- "additional_info.professional_memberships" MUST be a list of strings (e.g., ["IEEE", "ACM", "American Medical Association"]).
- Put email, phone number, LinkedIn URL, personal website/portfolio URL, and location inside the `contact` object (do NOT repeat them as top-level fields).
- Extract "headline" if there's a professional title/headline below the name.
- Extract "summary" if there's a professional summary, objective, or profile section. Copy it COMPLETELY and VERBATIM, sentence for sentence - do not shorten it, paraphrase it, or silently drop any sentence from it, even one that seems redundant with the headline or skills.

RAW RESUME TEXT:
\"\"\"{raw_text}\"\"\"
"""

    response = await client.chat.completions.parse(
        model=settings.openai_model_fast,
        messages=[{"role": "user", "content": prompt}],
        response_format=Resume,
        temperature=0,
    )
    resume_obj = _extract_parsed(response.choices[0].message)

    # Enrich skills with direct text scan (to capture tools in bullets/projects)
    resume_obj.skills = _enrich_skills_from_text(raw_text, resume_obj.skills or [])

    # Trim whitespace on categorized technical skills, drop empty categories
    cleaned_categories = []
    for cat in resume_obj.technical_skills or []:
        label = (cat.label or "").strip()
        items = [i.strip() for i in (cat.items or []) if i and i.strip()]
        if label and items:
            cleaned_categories.append(cat.__class__(label=label, items=items))
    resume_obj.technical_skills = cleaned_categories

    # Format dates to readable format (Month YYYY)
    for edu in resume_obj.education:
        if edu.graduation_date:
            edu.graduation_date = format_date(edu.graduation_date)

    for exp in resume_obj.experience:
        if exp.start_date:
            exp.start_date = format_date(exp.start_date)
        if exp.end_date and exp.end_date != "Present":
            exp.end_date = format_date(exp.end_date)

    return resume_obj
