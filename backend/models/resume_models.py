from pydantic import BaseModel
from typing import List, Optional


class Contact(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None


class EducationEntry(BaseModel):
    school: str
    degree: str
    major: Optional[str] = None            # e.g. "Computer Science"
    graduation_date: Optional[str] = None  # e.g. "May 2026"
    gpa: Optional[str] = None              # e.g. "3.8/4.0"
    location: Optional[str] = None
    scholarships: Optional[str] = None     # e.g. "Academic Excellence Scholarship, Carlton J Siegler Scholarship"
    relevant_coursework: Optional[str] = None  # e.g. "Systems Analysis and Design, Data Governance"


class Experience(BaseModel):
    title: str
    company: str
    location: Optional[str] = None
    start_date: Optional[str] = None       # e.g. "Jun 2024"
    end_date: Optional[str] = None         # e.g. "Present"
    bullets: List[str]


class Project(BaseModel):
    name: str
    role: Optional[str] = None
    semester: Optional[str] = None  # e.g. "Fall 2025"
    bullets: List[str]


class VolunteerWork(BaseModel):
    organization: str
    role: Optional[str] = None
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    bullets: List[str] = []


class Leadership(BaseModel):
    organization: str
    role: Optional[str] = None
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    bullets: List[str] = []


class Award(BaseModel):
    title: str
    organization: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None


class Publication(BaseModel):
    title: str
    authors: Optional[str] = None
    venue: Optional[str] = None  # journal, conference, etc.
    date: Optional[str] = None
    url: Optional[str] = None


class TechnicalSkillCategory(BaseModel):
    label: str              # e.g. "Computer Software", "Computer Languages", "Certifications"
    items: List[str] = []


class AdditionalInfo(BaseModel):
    computer_skills: Optional[str] = None
    technical_skills: Optional[str] = None  # Alternative to computer_skills for non-tech roles
    certifications: List[str] = []
    languages: List[str] = []
    work_eligibility: Optional[str] = None
    professional_memberships: List[str] = []  # e.g., "IEEE", "ACM", "AMA"
    other: Optional[str] = None            # anything extra if you want


class Resume(BaseModel):
    name: str
    contact: Optional[Contact] = None
    headline: Optional[str] = None
    summary: Optional[str] = None

    # Internal skills list – this powers tailoring.
    # On the final resume, we'll show these under "Computer Skills" in Additional Info.
    skills: List[str] = []

    # Categorized technical skills (e.g. "Computer Languages: Python, SQL, Java"),
    # rendered as its own TECHNICAL SKILLS section when present.
    technical_skills: List[TechnicalSkillCategory] = []

    education: List[EducationEntry] = []
    experience: List[Experience] = []
    projects: List[Project] = []
    leadership: List[Leadership] = []
    volunteer_work: List[VolunteerWork] = []
    awards: List[Award] = []
    publications: List[Publication] = []
    additional_info: Optional[AdditionalInfo] = None
    
    # Formatting control
    target_pages: int = 1  # Page budget for rendering: 1 or 2. Set deterministically from the uploaded PDF's own page count (never by the LLM) - a 2-page source is reformatted to 2 pages, and never squeezed by compact/ultra-compact spacing
    compact_mode: bool = False  # If True, use minimal spacing to fit on one page
    ultra_compact_mode: bool = False  # If True, also nudge the font size down slightly - set automatically by render_resume_pdf when compact spacing alone isn't enough to fit one page
    roomy_mode: bool = False  # If True, use looser-than-default spacing - set automatically by render_resume_pdf when a one-page render still leaves the page visibly underfull