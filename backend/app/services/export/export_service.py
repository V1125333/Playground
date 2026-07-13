from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum

from app.schemas.resume import ProfileEvidenceItem, ProfileMatchSummary, ResumeValidationResult, StructuredResumeRecord
from app.services.export.document_model import ResumeDocumentModel, build_document_model
from app.services.export.docx_renderer import render_docx
from app.services.export.filename import build_export_filename
from app.services.export.pdf_renderer import render_pdf
from app.services.export.template_registry import TemplateNotFoundError, resolve_template
from app.services.resume_validator import validate_structured_resume


EXPORT_RENDERER_VERSION = "resume-export-v1-structured"
EXPORT_WARNING_ONLY_CODES = {"unknown_evidence_id", "duplicate_bullet"}


class ExportFormat(StrEnum):
    pdf = "pdf"
    docx = "docx"


class ResumeExportValidationError(ValueError):
    def __init__(self, message: str, validation: ResumeValidationResult | None = None):
        super().__init__(message)
        self.validation = validation


@dataclass(frozen=True)
class ExportResult:
    content: bytes
    filename: str
    content_type: str
    resume_version: int
    template_id: str
    renderer_version: str
    warnings: list[str]
    duration_ms: int


def export_resume_record(
    record: StructuredResumeRecord,
    *,
    export_format: ExportFormat,
    template_id: str | None = None,
    paper_size: str = "letter",
    requested_filename: str = "",
) -> ExportResult:
    started = time.perf_counter()
    template = resolve_template(template_id or record.template_id or record.resume_json.template_id)
    validation = validate_exportable_resume(record)
    if validation.errors:
        raise ResumeExportValidationError(validation.errors[0].message, validation)

    model = build_document_model(
        record.resume_json,
        template=template,
        renderer_version=EXPORT_RENDERER_VERSION,
        warnings=[issue.message for issue in validation.warnings],
    )
    if not model.full_name.strip() or model.full_name == "Resume":
        raise ResumeExportValidationError("Resume header identity is required before export.", validation)

    if export_format == ExportFormat.pdf:
        content = render_pdf(model, template, paper_size=paper_size)
        content_type = "application/pdf"
    else:
        content = render_docx(model, template, paper_size=paper_size)
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    filename = build_export_filename(
        full_name=model.full_name,
        target_role=record.target_job_title,
        company=record.target_company,
        version_number=record.version_number,
        extension=export_format.value,
        requested_filename=requested_filename,
    )
    return ExportResult(
        content=content,
        filename=filename,
        content_type=content_type,
        resume_version=record.version_number,
        template_id=template.template_id,
        renderer_version=EXPORT_RENDERER_VERSION,
        warnings=[issue.message for issue in validation.warnings],
        duration_ms=round((time.perf_counter() - started) * 1000),
    )


def validate_exportable_resume(record: StructuredResumeRecord) -> ResumeValidationResult:
    profile_match = ProfileMatchSummary.model_validate(record.profile_match_json or {})
    evidence = collect_evidence(profile_match)
    validation = validate_structured_resume(record.resume_json, evidence, profile_match)
    return downgrade_export_quality_errors(validation)


def downgrade_export_quality_errors(validation: ResumeValidationResult) -> ResumeValidationResult:
    warning_only_errors = [issue for issue in validation.errors if issue.code in EXPORT_WARNING_ONLY_CODES]
    if not warning_only_errors:
        return validation
    blocking_errors = [issue for issue in validation.errors if issue.code not in EXPORT_WARNING_ONLY_CODES]
    warnings = [
        *validation.warnings,
        *[issue.model_copy(update={"severity": "warning"}) for issue in warning_only_errors],
    ]
    rejected_ids = {
        issue.content_id
        for issue in blocking_errors
        if issue.content_id
    }
    return validation.model_copy(
        update={
            "is_valid": not blocking_errors,
            "errors": blocking_errors,
            "warnings": warnings,
            "rejected_content_ids": sorted(rejected_ids),
        }
    )


def collect_evidence(profile_match: ProfileMatchSummary) -> list[ProfileEvidenceItem]:
    seen: set[str] = set()
    output: list[ProfileEvidenceItem] = []
    for match in [
        *profile_match.matched_requirements,
        *profile_match.partially_matched_requirements,
        *profile_match.unmatched_requirements,
    ]:
        for item in [*match.evidence, *match.adjacent_evidence]:
            if item.evidence_id not in seen:
                output.append(item)
                seen.add(item.evidence_id)
    return output
