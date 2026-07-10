from __future__ import annotations

from dataclasses import dataclass


class TemplateNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class ResumeExportTemplate:
    template_id: str
    name: str
    font_name: str
    accent_color: str
    name_size: int
    body_size: int
    section_size: int
    margins: tuple[float, float, float, float]


TEMPLATES: dict[str, ResumeExportTemplate] = {
    "classic-ats": ResumeExportTemplate(
        template_id="classic-ats",
        name="Classic ATS",
        font_name="Times",
        accent_color="#111111",
        name_size=18,
        body_size=10,
        section_size=10,
        margins=(0.62, 0.62, 0.62, 0.62),
    ),
    "modern-clean": ResumeExportTemplate(
        template_id="modern-clean",
        name="Modern Clean",
        font_name="Helvetica",
        accent_color="#0f7891",
        name_size=20,
        body_size=10,
        section_size=10,
        margins=(0.65, 0.65, 0.68, 0.68),
    ),
}


def resolve_template(template_id: str | None) -> ResumeExportTemplate:
    key = (template_id or "classic-ats").strip() or "classic-ats"
    template = TEMPLATES.get(key)
    if not template:
        raise TemplateNotFoundError(f"Unsupported resume export template: {key}")
    return template
