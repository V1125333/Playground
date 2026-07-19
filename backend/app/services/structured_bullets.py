from __future__ import annotations

import hashlib
from typing import Any

from app.schemas.resume import GeneratedResumeBullet, StructuredGeneratedResume


LEGACY_BULLET_WARNING = "Legacy bullet has no provenance; validation required before treating it as evidence-backed."


def make_generated_bullet(
    *,
    resume_scope: str,
    source_record_id: str,
    evidence_id: str,
    order: int,
    text: str,
    requirement_ids: list[str],
) -> dict:
    bullet = GeneratedResumeBullet(
        bulletId=stable_bullet_id(resume_scope, source_record_id, evidence_id, order),
        order=order,
        generatedText=text,
        currentText=text,
        userEdited=False,
        supportedRequirementIds=requirement_ids,
        supportingEvidenceIds=[evidence_id],
        validationStatus="validated",
        warnings=[],
        generationMethod="deterministic",
    )
    return bullet.model_dump(mode="json", by_alias=True)


def normalize_structured_resume_bullets(resume: StructuredGeneratedResume) -> StructuredGeneratedResume:
    changed = False
    sections = []
    for section in resume.sections:
        if section.type not in {"experience", "projects"}:
            sections.append(section)
            continue
        content = []
        for entry_index, entry in enumerate(as_list(section.content)):
            if not isinstance(entry, dict):
                content.append(entry)
                continue
            source_record_id = str(entry.get("sourceRecordId") or f"{section.section_id}-{entry_index + 1}")
            bullets = [
                normalize_bullet_item(item, index + 1, section.section_id, source_record_id)
                for index, item in enumerate(as_list(entry.get("bullets", [])))
            ]
            if bullets != entry.get("bullets", []):
                changed = True
            content.append({**entry, "bullets": bullets})
        sections.append(section.model_copy(update={"content": content}))
    return resume.model_copy(update={"sections": sections}) if changed else resume


def normalize_bullet_item(item: Any, order: int, section_id: str, source_record_id: str) -> dict:
    if isinstance(item, dict):
        current = bullet_text(item)
        if "generatedText" in item:
            generated = str(item.get("generatedText") or "")
        elif "generated_text" in item:
            generated = str(item.get("generated_text") or "")
        else:
            generated = current
        bullet_id = str(item.get("bulletId") or item.get("bullet_id") or stable_bullet_id(section_id, source_record_id, current, order))
        status = str(item.get("validationStatus") or item.get("validation_status") or ("validated" if item.get("supportingEvidenceIds") else "pending_validation"))
        warning_values = [str(value) for value in as_list(item.get("warnings", [])) if str(value).strip()]
        bullet = GeneratedResumeBullet(
            bulletId=bullet_id,
            order=int(item.get("order") or order),
            generatedText=generated,
            currentText=current,
            userEdited=bool(item.get("userEdited") or item.get("user_edited") or (generated and current != generated)),
            supportedRequirementIds=[str(value) for value in as_list(item.get("supportedRequirementIds") or item.get("supported_requirement_ids"))],
            supportingEvidenceIds=[str(value) for value in as_list(item.get("supportingEvidenceIds") or item.get("supporting_evidence_ids"))],
            validationStatus=status,
            warnings=warning_values,
            generationMethod=str(item.get("generationMethod") or item.get("generation_method") or "deterministic"),
            model=str(item.get("model") or ""),
            promptVersion=str(item.get("promptVersion") or item.get("prompt_version") or ""),
        )
        normalized = bullet.model_dump(mode="json", by_alias=True)
        item.clear()
        item.update(normalized)
        return item

    text = str(item or "").strip()
    bullet = GeneratedResumeBullet(
        bulletId=stable_bullet_id(section_id, source_record_id, text, order),
        order=order,
        generatedText="",
        currentText=text,
        userEdited=True,
        supportedRequirementIds=[],
        supportingEvidenceIds=[],
        validationStatus="pending_validation",
        warnings=[LEGACY_BULLET_WARNING] if text else [],
        generationMethod="legacy",
    )
    return bullet.model_dump(mode="json", by_alias=True)


def bullet_text(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("currentText") or item.get("current_text") or item.get("generatedText") or item.get("generated_text") or item.get("text") or "").strip()
    return str(item or "").strip()


def bullet_generated_text(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("generatedText") or item.get("generated_text") or "").strip()
    return ""


def stable_bullet_id(*parts: Any) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"bullet-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
