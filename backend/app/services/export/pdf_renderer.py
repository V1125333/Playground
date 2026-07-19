from __future__ import annotations

from html import escape
from io import BytesIO

from app.services.export.document_model import (
    CertificationItem,
    EducationItem,
    ExperienceItem,
    ProjectItem,
    ResumeDocumentModel,
    SkillGroup,
)
from app.services.export.template_registry import ResumeExportTemplate


def render_pdf(model: ResumeDocumentModel, template: ResumeExportTemplate, *, paper_size: str = "letter") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

    page = A4 if paper_size.lower() == "a4" else letter
    top, bottom, left, right = template.margins
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=page,
        topMargin=top * inch,
        bottomMargin=bottom * inch,
        leftMargin=left * inch,
        rightMargin=right * inch,
        title=model.full_name,
        author=model.full_name,
        subject="Resume",
    )
    sample = getSampleStyleSheet()
    font = "Helvetica" if template.font_name == "Helvetica" else "Times-Roman"
    bold_font = "Helvetica-Bold" if template.font_name == "Helvetica" else "Times-Bold"
    italic_font = "Helvetica-Oblique" if template.font_name == "Helvetica" else "Times-Italic"
    normal = ParagraphStyle("ResumeBody", parent=sample["Normal"], fontName=font, fontSize=template.body_size, leading=template.body_size + 2, spaceAfter=2)
    small = ParagraphStyle("ResumeSmall", parent=normal, fontSize=max(template.body_size - 1, 8), leading=template.body_size + 1)
    name = ParagraphStyle("ResumeName", parent=normal, alignment=TA_CENTER, fontName=bold_font, fontSize=template.name_size, leading=template.name_size + 2, spaceAfter=2)
    title = ParagraphStyle("ResumeTitle", parent=normal, alignment=TA_CENTER, fontSize=template.body_size + 1, leading=template.body_size + 3)
    contact = ParagraphStyle("ResumeContact", parent=small, alignment=TA_CENTER, spaceAfter=5)
    heading = ParagraphStyle("ResumeSectionHeading", parent=normal, fontName=bold_font, fontSize=template.section_size, leading=template.section_size + 2, textColor=colors.HexColor(template.accent_color), spaceBefore=6, spaceAfter=2)
    role = ParagraphStyle("ResumeRoleHeading", parent=normal, fontName=bold_font, spaceBefore=2, spaceAfter=0)
    subrole = ParagraphStyle("ResumeSubRole", parent=normal, fontName=italic_font, spaceAfter=1)
    bullet_style = ParagraphStyle("ResumeBullet", parent=normal, leftIndent=12, firstLineIndent=-7, spaceAfter=1.5)

    story = [
        Paragraph(escape(model.full_name.upper()), name),
    ]
    if model.professional_title:
        story.append(Paragraph(escape(model.professional_title), title))
    if model.contact_items:
        story.append(Paragraph(escape(" | ".join(item.value for item in model.contact_items)), contact))

    for section in model.sections:
        story.append(Spacer(0, 4))
        story.append(Paragraph(escape(section.title.upper()), heading))
        story.append(HRFlowable(width="100%", thickness=0.45, color=colors.HexColor(template.accent_color), spaceAfter=3))
        if section.type == "summary":
            story.append(Paragraph(escape(str(section.content)), normal))
        elif section.type == "skills":
            for group in section.content:
                skill = group if isinstance(group, SkillGroup) else SkillGroup.model_validate(group)
                story.append(Paragraph(f"<b>{escape(skill.category)}:</b> {escape(', '.join(skill.items))}", normal))
        elif section.type == "experience":
            for item in section.content:
                exp = item if isinstance(item, ExperienceItem) else ExperienceItem.model_validate(item)
                story.extend(render_experience(exp, role, subrole, bullet_style))
        elif section.type == "projects":
            for item in section.content:
                project = item if isinstance(item, ProjectItem) else ProjectItem.model_validate(item)
                heading_text = " | ".join(part for part in [project.name, project.org, project.link] if part)
                story.append(Paragraph(escape(heading_text), role))
                if project.technologies:
                    story.append(Paragraph(f"<b>Technologies:</b> {escape(', '.join(project.technologies))}", normal))
                story.extend(bullet_list([bullet.text for bullet in project.bullets], bullet_style))
        elif section.type == "education":
            for item in section.content:
                education = item if isinstance(item, EducationItem) else EducationItem.model_validate(item)
                line = " | ".join(part for part in [education.degree, education.institution, education.location, education.grad_year, education.gpa] if part)
                story.append(Paragraph(escape(line), normal))
        elif section.type == "certifications":
            for item in section.content:
                certification = item if isinstance(item, CertificationItem) else CertificationItem.model_validate(item)
                line = " | ".join(part for part in [certification.name, certification.issuer, certification.issued_date, certification.expiry_date] if part)
                story.append(Paragraph(escape(line), normal))

    doc.build(story)
    return output.getvalue()


def render_experience(item: ExperienceItem, role_style, subrole_style, bullet_style):
    from reportlab.platypus import KeepTogether, Paragraph

    period = " - ".join(part for part in [item.start_date, item.end_date] if part)
    company_line = " | ".join(part for part in [item.company, period] if part)
    role_line = " | ".join(part for part in [item.role, item.location] if part)
    block = [Paragraph(escape(company_line), role_style)]
    if role_line:
        block.append(Paragraph(escape(role_line), subrole_style))
    block.extend(bullet_list([bullet.text for bullet in item.bullets], bullet_style))
    return [KeepTogether(block)]


def bullet_list(items: list[str], bullet_style):
    from reportlab.platypus import Paragraph

    return [Paragraph(f"&#8226;&nbsp;{escape(item)}", bullet_style) for item in items]
