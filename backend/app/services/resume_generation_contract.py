from pathlib import Path


def load_resume_prompt() -> str:
    prompt_path = Path(__file__).resolve().parents[3] / "resume_prompt.md"
    fallback = """
You are a resume generation assistant acting as an ATS expert, a senior typography/UX designer,
and a Microsoft Word + PDF rendering engineer. Generate an ATS-ready resume tailored to the job
description using only facts supported by the candidate profile. Never fabricate experience,
employers, dates, links, or metrics.
"""
    try:
        return prompt_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return fallback


RESUME_GENERATION_SYSTEM_PROMPT = (
    load_resume_prompt()
    + """

Application integration rule:
- For this API call, return only valid JSON matching the requested schema. Do not return markdown,
  prose, DOCX bytes, PDF bytes, or file paths. The app will use this structured JSON for preview,
  ATS scoring, and later DOCX/PDF export.
- Treat resume_prompt.md as the governing resume generation engine. Follow its recruiter analysis,
  requirement ranking, truthful experience mapping, career progression, distinct company-story,
  ATS optimization, validation, and final reviewer instructions before returning JSON.
- Preserve the existing schema exactly: do not add, remove, or rename fields. Put categories only in
  skills[].category, skill values only in skills[].items, and prose only in summary/bullets.
- Keep resume.title equal to the candidate profile's current title. Use targetRole and targetCompany
  only for tailoring content. Do not force targetRole into the header or summary.
- Summary must be exactly 3 plain-prose sentences. Experience bullets must be 4-6 per role, unique,
  technically specific, business-contextual, and non-repetitive.
- Validate internally before returning: no duplicate skills, no category-label leaks, no repeated
  bullet structures, no weak/generic bullets, and important supported JD requirements covered
  naturally without keyword stuffing.
"""
)


RESUME_LAYOUT_CONTRACT = {
    "font": "Times New Roman",
    "fallbackFonts": ["Georgia", "serif"],
    "fontSizesPt": {
        "name": 22,
        "title": 12,
        "contact": 11,
        "sectionHeading": 11,
        "body": 11,
        "dates": 11,
    },
    "marginsIn": {"top": 0.55, "bottom": 0.55, "left": 0.60, "right": 0.60},
    "spacingPt": {
        "sectionHeadingAbove": 6,
        "sectionHeadingBelow": 4,
        "companyBlockAbove": 8,
        "roleLineBelow": 2,
        "betweenBullets": 3.5,
        "betweenSections": 12,
    },
    "sectionOrder": [
        "SUMMARY",
        "TECHNICAL SKILLS",
        "PROFESSIONAL EXPERIENCE",
        "PROJECTS",
        "EDUCATION",
        "CERTIFICATIONS",
    ],
    "prohibitedElements": [
        "tables",
        "text boxes",
        "floating elements",
        "multiple columns",
        "icons",
        "images",
        "progress bars",
        "star ratings",
        "graphics",
    ],
}
