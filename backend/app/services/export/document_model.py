from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.resume import ResumeContact, StructuredGeneratedResume
from app.services.export.template_registry import ResumeExportTemplate


class ContactItem(BaseModel):
    label: str
    value: str
    url: str | None = None


class SkillGroup(BaseModel):
    category: str
    items: list[str] = Field(default_factory=list)


class BulletItem(BaseModel):
    text: str
    order: int = 0


class ExperienceItem(BaseModel):
    company: str
    role: str
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    bullets: list[BulletItem] = Field(default_factory=list)


class ProjectItem(BaseModel):
    name: str
    org: str = ""
    link: str = ""
    technologies: list[str] = Field(default_factory=list)
    bullets: list[BulletItem] = Field(default_factory=list)


class EducationItem(BaseModel):
    degree: str
    institution: str
    location: str = ""
    grad_year: str = ""
    gpa: str = ""


class CertificationItem(BaseModel):
    name: str
    issuer: str = ""
    issued_date: str = ""
    expiry_date: str = ""


class DocumentSection(BaseModel):
    id: str
    type: str
    title: str
    order: int
    visible: bool = True
    content: Any


class ExportMetadata(BaseModel):
    resume_id: str
    resume_version: int
    template_id: str
    renderer_version: str
    generated_at: str
    warnings: list[str] = Field(default_factory=list)


class ResumeDocumentModel(BaseModel):
    resume_id: str
    resume_version: int
    template_id: str
    full_name: str
    professional_title: str = ""
    contact_items: list[ContactItem] = Field(default_factory=list)
    sections: list[DocumentSection] = Field(default_factory=list)
    export_metadata: ExportMetadata


def build_document_model(
    resume: StructuredGeneratedResume,
    *,
    template: ResumeExportTemplate,
    renderer_version: str,
    warnings: list[str] | None = None,
) -> ResumeDocumentModel:
    resume_copy = deepcopy(resume)
    full_name = derive_full_name(resume_copy)
    metadata = ExportMetadata(
        resume_id=resume_copy.resume_id,
        resume_version=resume_copy.version_number,
        template_id=template.template_id,
        renderer_version=renderer_version,
        generated_at=datetime.now(timezone.utc).isoformat(),
        warnings=warnings or [],
    )
    sections = [
        normalize_section(section)
        for section in sorted(resume_copy.sections, key=lambda item: item.order)
        if section.visible is not False and content_has_value(section.content)
    ]
    return ResumeDocumentModel(
        resume_id=resume_copy.resume_id,
        resume_version=resume_copy.version_number,
        template_id=template.template_id,
        full_name=full_name,
        professional_title=derive_professional_title(resume_copy),
        contact_items=contact_items(resume_copy.contact),
        sections=[section for section in sections if content_has_value(section.content)],
        export_metadata=metadata,
    )


def normalize_section(section) -> DocumentSection:
    return DocumentSection(
        id=section.section_id,
        type=section.type,
        title=section.title,
        order=section.order,
        visible=section.visible,
        content=normalize_content(section.type, section.content),
    )


def normalize_content(section_type: str, content: Any) -> Any:
    if section_type == "summary":
        return text_value(content)
    if section_type == "skills":
        groups: list[SkillGroup] = []
        for item in as_list(content):
            category = text_value(item.get("category") if isinstance(item, dict) else "")
            values = item.get("items", []) if isinstance(item, dict) else []
            skills = dedupe([text_value(value) for value in as_list(values)])
            if category and skills:
                groups.append(SkillGroup(category=category, items=skills))
        return groups
    if section_type == "experience":
        return [entry for entry in (normalize_experience(item) for item in as_list(content)) if entry.bullets or entry.company or entry.role]
    if section_type == "projects":
        return [entry for entry in (normalize_project(item) for item in as_list(content)) if entry.bullets or entry.name]
    if section_type == "education":
        return [entry for entry in (normalize_education(item) for item in as_list(content)) if entry.degree or entry.institution]
    if section_type == "certifications":
        return [entry for entry in (normalize_certification(item) for item in as_list(content)) if entry.name]
    return content


def normalize_experience(item: Any) -> ExperienceItem:
    data = item if isinstance(item, dict) else {}
    return ExperienceItem(
        company=text_value(data.get("company")),
        role=text_value(data.get("role")),
        location=text_value(data.get("location")),
        start_date=text_value(data.get("startDate") or data.get("start_date")),
        end_date=text_value(data.get("endDate") or data.get("end_date")),
        bullets=normalize_bullets(data.get("bullets", [])),
    )


def normalize_project(item: Any) -> ProjectItem:
    data = item if isinstance(item, dict) else {}
    return ProjectItem(
        name=text_value(data.get("name")),
        org=text_value(data.get("org")),
        link=safe_url(text_value(data.get("link"))),
        technologies=dedupe([text_value(value) for value in as_list(data.get("technologies", []))]),
        bullets=normalize_bullets(data.get("bullets", [])),
    )


def normalize_education(item: Any) -> EducationItem:
    data = item if isinstance(item, dict) else {}
    return EducationItem(
        degree=text_value(data.get("degree")),
        institution=text_value(data.get("institution")),
        location=text_value(data.get("location")),
        grad_year=text_value(data.get("gradYear") or data.get("grad_year")),
        gpa=text_value(data.get("gpa")),
    )


def normalize_certification(item: Any) -> CertificationItem:
    data = item if isinstance(item, dict) else {}
    return CertificationItem(
        name=text_value(data.get("name")),
        issuer=text_value(data.get("issuer")),
        issued_date=text_value(data.get("issuedDate") or data.get("issued_date")),
        expiry_date=text_value(data.get("expiryDate") or data.get("expiry_date")),
    )


def normalize_bullets(values: Any) -> list[BulletItem]:
    bullets: list[BulletItem] = []
    for index, item in enumerate(as_list(values)):
        if isinstance(item, dict) and item.get("deleted"):
            continue
        text = text_value(item.get("currentText") or item.get("generatedText") or item.get("text") if isinstance(item, dict) else item)
        if text:
            order = int(item.get("order", index + 1)) if isinstance(item, dict) else index + 1
            bullets.append(BulletItem(text=text, order=order))
    return sorted(bullets, key=lambda item: item.order)


def derive_full_name(resume: StructuredGeneratedResume) -> str:
    name = resume.resume_name.replace(f" - {resume.target_job_title}", "").strip()
    return name or "Resume"


def derive_professional_title(resume: StructuredGeneratedResume) -> str:
    for section in resume.sections:
        if section.type == "experience":
            entries = as_list(section.content)
            if entries and isinstance(entries[0], dict):
                return text_value(entries[0].get("role"))
    return ""


def contact_items(contact: ResumeContact) -> list[ContactItem]:
    order = [
        ("Email", contact.email, f"mailto:{contact.email}" if contact.email else ""),
        ("Phone", contact.phone, ""),
        ("Location", contact.location, ""),
        ("LinkedIn", contact.linkedin, contact.linkedin),
        ("GitHub", contact.github, contact.github),
        ("Portfolio", contact.portfolio, contact.portfolio),
    ]
    return [
        ContactItem(label=label, value=value.strip(), url=safe_url(url))
        for label, value, url in order
        if value and value.strip()
    ]


def safe_url(value: str) -> str | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if lowered.startswith(("https://", "http://", "mailto:")):
        return cleaned
    return None


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def text_value(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = value.casefold().strip()
        if value and key not in seen:
            output.append(value)
            seen.add(key)
    return output


def content_has_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, dict):
        return any(content_has_value(item) for item in value.values())
    return value is not None
