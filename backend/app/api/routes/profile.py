import re
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter()

ROLE_WORDS = (
    "engineer",
    "developer",
    "manager",
    "analyst",
    "designer",
    "architect",
    "consultant",
    "lead",
    "specialist",
)

SECTION_HEADERS = {
    "skills",
    "technical skills",
    "experience",
    "work experience",
    "professional experience",
    "education",
    "projects",
    "certifications",
    "summary",
}

SKILL_KEYWORDS = [
    "React",
    "TypeScript",
    "JavaScript",
    "Python",
    "Java",
    "C#",
    ".NET",
    "SQL",
    "PostgreSQL",
    "AWS",
    "Azure",
    "Docker",
    "Kubernetes",
    "GraphQL",
    "REST",
    "CI/CD",
    "WCAG",
    "Storybook",
    "Node.js",
    "FastAPI",
]


@router.post("/extract")
async def extract_profile_from_resume(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    content = await file.read()

    try:
        if suffix in {".txt", ".md"}:
            text = content.decode("utf-8", errors="ignore")
        elif suffix == ".docx":
            text = extract_docx_text(content)
        elif suffix == ".pdf":
            text = extract_pdf_text(content)
        else:
            raise HTTPException(status_code=400, detail="Upload a PDF, DOCX, TXT, or MD resume.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not extract text from that resume.") from exc

    return parse_resume_text(text)


def extract_docx_text(content: bytes) -> str:
    from docx import Document

    document = Document(BytesIO(content))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def extract_pdf_text(content: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_resume_text(text: str) -> dict:
    lines = [line.strip().lstrip("\ufeff") for line in text.splitlines() if line.strip()]
    compact_text = "\n".join(lines)

    email = first_match(r"[\w.+-]+@[\w-]+\.[\w.-]+", compact_text)
    phone = first_match(r"(?:\+?\d[\d\s().-]{7,}\d)", compact_text)
    linkedin = first_match(r"(?:https?://)?(?:www\.)?linkedin\.com/[^\s,;]+", compact_text)
    github = first_match(r"(?:https?://)?(?:www\.)?github\.com/[^\s,;]+", compact_text)
    portfolio = first_portfolio_link(compact_text, linkedin, github)

    name = guess_name(lines)
    first_name, last_name = split_name(name)
    title = guess_title(lines, name)
    location = guess_location(lines)
    skills = guess_skills(compact_text)
    experience = guess_experience(lines)
    education = guess_education(lines)
    certifications = guess_certifications(lines)

    return {
        "firstName": first_name,
        "lastName": last_name,
        "title": title,
        "email": email,
        "phone": phone,
        "location": location,
        "linkedin": linkedin,
        "github": github,
        "portfolio": portfolio,
        "skills": ", ".join(skills),
        "experience": experience
        or [
            {
                "id": "exp-1",
                "company": "",
                "role": "",
                "location": "",
                "startDate": "",
                "endDate": "",
            }
        ],
        "education": education
        or [
            {
                "id": "edu-1",
                "degree": "",
                "institution": "",
                "location": "",
                "gradYear": "",
                "gpa": "",
            }
        ],
        "certifications": certifications
        or [
            {
                "id": "cert-1",
                "name": "",
                "issuer": "",
                "issuedDate": "",
                "expiryDate": "",
            }
        ],
    }


def first_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(0).strip() if match else ""


def first_portfolio_link(text: str, linkedin: str, github: str) -> str:
    links = re.findall(r"(?:https?://)?(?:www\.)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/[^\s,;]+", text)
    for link in links:
        if link != linkedin and link != github:
            return link.strip()
    return ""


def guess_name(lines: list[str]) -> str:
    for line in lines[:8]:
        lower = line.lower()
        if (
            "@" in line
            or re.search(r"\d", line)
            or re.search(r"\b[A-Z][a-zA-Z .]+,\s*[A-Z]{2}\b", line)
            or "linkedin" in lower
            or lower in SECTION_HEADERS
            or any(word in lower for word in ROLE_WORDS)
        ):
            continue
        words = line.split()
        if 2 <= len(words) <= 4 and all(word[:1].isalpha() for word in words):
            return line
    return ""


def split_name(name: str) -> tuple[str, str]:
    parts = name.split()
    if not parts:
        return "", ""
    return parts[0], " ".join(parts[1:])


def guess_title(lines: list[str], name: str) -> str:
    for line in lines[:12]:
        lower = line.lower()
        if (
            line == name
            or "@" in line
            or "linkedin" in lower
            or "github" in lower
            or lower in SECTION_HEADERS
            or re.search(r"(?:19|20)\d{2}|present", lower)
        ):
            continue
        if any(word in lower for word in ROLE_WORDS):
            return line[:120]
    return ""


def guess_location(lines: list[str]) -> str:
    for line in lines[:12]:
        if re.search(r"\b[A-Z][a-zA-Z .]+,\s*[A-Z]{2}\b", line):
            return line
        if any(token in line.lower() for token in ["remote", "india", "canada", "united states"]):
            return line[:120]
    return ""


def guess_skills(text: str) -> list[str]:
    lower = text.lower()
    found = [skill for skill in SKILL_KEYWORDS if skill.lower() in lower]
    return sorted(dict.fromkeys(found))


def guess_experience(lines: list[str]) -> list[dict]:
    date_pattern = re.compile(r"((?:19|20)\d{2}(?:-\d{2})?|Present)", re.IGNORECASE)
    experience: list[dict] = []

    for index, line in enumerate(lines):
        if not date_pattern.search(line):
            continue

        pipe_parts = [part.strip() for part in line.split("|")]
        if len(pipe_parts) >= 3:
            role = clean_date_noise(pipe_parts[0])
            company = clean_date_noise(pipe_parts[1])
            dates = date_pattern.findall(pipe_parts[-1])
            if role or company:
                experience.append(
                    {
                        "id": f"exp-{len(experience) + 1}",
                        "company": company,
                        "role": role,
                        "location": "",
                        "startDate": normalize_date(dates[0]) if dates else "",
                        "endDate": normalize_date(dates[-1])
                        if len(dates) > 1
                        else ("Present" if "present" in line.lower() else ""),
                    }
                )
                continue

        context = " | ".join(lines[max(0, index - 2) : index + 1])
        role = ""
        company = ""

        for part in re.split(r"\s+[|•-]\s+|\s+ at \s+", context):
            lower_part = part.lower().strip()
            if lower_part in SECTION_HEADERS:
                continue
            if any(word in lower_part for word in ROLE_WORDS) and not role:
                role = clean_date_noise(part)
            elif not company and not date_pattern.search(part) and len(part.split()) <= 5:
                company = part.strip()

        dates = date_pattern.findall(context)
        start_date = normalize_date(dates[0]) if dates else ""
        end_date = normalize_date(dates[-1]) if len(dates) > 1 else ("Present" if "present" in context.lower() else "")

        if role or company:
            experience.append(
                {
                    "id": f"exp-{len(experience) + 1}",
                    "company": company,
                    "role": role,
                    "location": "",
                    "startDate": start_date,
                    "endDate": end_date,
                }
            )

    return experience[:6]


def clean_date_noise(value: str) -> str:
    return re.sub(r"((?:19|20)\d{2}(?:-\d{2})?|Present)", "", value, flags=re.IGNORECASE).strip(" |,-")


def normalize_date(value: str) -> str:
    if value.lower() == "present":
        return "Present"
    return value


def guess_education(lines: list[str]) -> list[dict]:
    education: list[dict] = []
    for line in lines:
        lower = line.lower()
        if not any(term in lower for term in ["bachelor", "master", "degree", "university", "college", "computer science"]):
            continue
        year = first_match(r"(?:19|20)\d{2}", line)
        degree = line
        institution = ""
        location = ""
        if " - " in line:
            left, right = [part.strip() for part in line.split(" - ", 1)]
            degree, institution = left, clean_date_noise(right)
        elif "," in line:
            parts = [part.strip() for part in line.split(",")]
            degree = parts[0]
            institution = parts[1] if len(parts) > 1 else ""
            location = ", ".join(parts[2:]) if len(parts) > 2 else ""
        education.append(
            {
                "id": f"edu-{len(education) + 1}",
                "degree": clean_date_noise(degree),
                "institution": institution,
                "location": location,
                "gradYear": year,
                "gpa": guess_gpa(line),
            }
        )
    return education[:4]


def guess_certifications(lines: list[str]) -> list[dict]:
    certifications: list[dict] = []
    in_cert_section = False
    for line in lines:
        lower = line.lower()
        if lower in {"certifications", "certifications / professional awards:", "certifications / professional awards"}:
            in_cert_section = True
            continue
        if in_cert_section and lower in SECTION_HEADERS and "certification" not in lower:
            break
        if not in_cert_section and not any(term in lower for term in ["certified", "certification", "certificate"]):
            continue
        clean = line.strip(":- ")
        if not clean or clean.lower() in SECTION_HEADERS:
            continue
        parts = [part.strip() for part in re.split(r"\s+-\s+|\s+—\s+", clean, maxsplit=1)]
        certifications.append(
            {
                "id": f"cert-{len(certifications) + 1}",
                "name": parts[0],
                "issuer": parts[1] if len(parts) > 1 else "",
                "issuedDate": "",
                "expiryDate": "",
            }
        )
    return certifications[:8]


def guess_gpa(line: str) -> str:
    match = re.search(r"GPA[:\s]+([0-9.]+)", line, flags=re.IGNORECASE)
    return match.group(1) if match else ""
