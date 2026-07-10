from __future__ import annotations

import re

from app.schemas.resume import (
    ProfileEvidenceItem,
    ProfileMatchSummary,
    ResumeValidationIssue,
    ResumeValidationResult,
    StructuredGeneratedResume,
)


def validate_structured_resume(
    resume: StructuredGeneratedResume,
    evidence_index: list[ProfileEvidenceItem],
    profile_match: ProfileMatchSummary,
) -> ResumeValidationResult:
    evidence_ids = {item.evidence_id for item in evidence_index}
    matched_requirement_ids = {
        match.requirement_id
        for match in [
            *profile_match.matched_requirements,
            *profile_match.partially_matched_requirements,
            *profile_match.unmatched_requirements,
        ]
    }
    unmatched_requirement_ids = {match.requirement_id for match in profile_match.unmatched_requirements}
    unmatched_requirement_values = {
        normalize_text(match.requirement_value): match.requirement_value
        for match in profile_match.unmatched_requirements
        if match.requirement_value.strip()
    }
    adjacent_requirement_ids = {match.requirement_id for match in profile_match.partially_matched_requirements}
    errors: list[ResumeValidationIssue] = []
    warnings: list[ResumeValidationIssue] = []
    rejected: list[str] = []
    seen_bullets: set[str] = set()

    for section in resume.sections:
        provenance = section.provenance
        missing_evidence = [evidence_id for evidence_id in provenance.supporting_evidence_ids if evidence_id not in evidence_ids]
        if missing_evidence:
            errors.append(issue("unknown_evidence_id", "error", "Section references unknown evidence IDs.", section.section_id, section.section_id, missing_evidence))
            rejected.append(section.section_id)
        missing_requirements = [
            requirement_id
            for requirement_id in provenance.supported_requirement_ids
            if requirement_id not in matched_requirement_ids
        ]
        if missing_requirements:
            errors.append(issue("unknown_requirement_id", "error", "Section references unknown requirement IDs.", section.section_id, section.section_id))
            rejected.append(section.section_id)
        if any(requirement_id in unmatched_requirement_ids for requirement_id in provenance.supported_requirement_ids):
            errors.append(issue("unmatched_requirement_claimed", "error", "Unmatched requirement is referenced by generated content.", section.section_id, section.section_id))
            rejected.append(section.section_id)
        if any(requirement_id in adjacent_requirement_ids for requirement_id in provenance.supported_requirement_ids):
            warnings.append(issue("adjacent_requirement_context", "warning", "Adjacent requirement may be used only as transferable context.", section.section_id, section.section_id))

        texts = section_texts(section.content)
        if not texts:
            warnings.append(issue("empty_section", "warning", "Empty section omitted or needs review.", section.section_id, section.section_id))
        for text in texts:
            normalized = normalize_text(text)
            for normalized_requirement, requirement_value in unmatched_requirement_values.items():
                if requirement_appears_in_text(normalized_requirement, normalized):
                    warnings.append(
                        issue(
                            "unmatched_requirement_in_content",
                            "warning",
                            f"The draft mentions {requirement_value}, but no supporting profile evidence was found.",
                            section.section_id,
                            section.section_id,
                        )
                    )
            if normalized in seen_bullets and section.type == "experience":
                errors.append(issue("duplicate_bullet", "error", "Duplicate generated bullet detected.", section.section_id, section.section_id))
                rejected.append(section.section_id)
            seen_bullets.add(normalized)
            if contains_placeholder(text):
                errors.append(issue("placeholder_content", "error", "Generated content contains placeholder wording.", section.section_id, section.section_id))
                rejected.append(section.section_id)
            if has_metric(text) and not metric_supported(text, section.provenance.supporting_evidence_ids, evidence_index):
                errors.append(issue("unsupported_metric", "error", "Generated metric is not present in supporting evidence.", section.section_id, section.section_id, section.provenance.supporting_evidence_ids))
                rejected.append(section.section_id)

    return ResumeValidationResult(
        isValid=not errors,
        errors=errors,
        warnings=warnings,
        rejectedContentIds=sorted(set(rejected)),
    )


def issue(code: str, severity: str, message: str, section_id: str, content_id: str, evidence_ids: list[str] | None = None) -> ResumeValidationIssue:
    return ResumeValidationIssue(
        code=code,
        severity=severity,
        message=message,
        sectionId=section_id,
        contentId=content_id,
        evidenceIds=evidence_ids or [],
    )


def section_texts(content) -> list[str]:
    if isinstance(content, str):
        return [content] if content.strip() else []
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict):
                texts.extend(str(value) for value in item.values() if isinstance(value, str))
                bullets = item.get("bullets")
                if isinstance(bullets, list):
                    texts.extend(str(value) for value in bullets)
        return [text for text in texts if text.strip()]
    if isinstance(content, dict):
        return [str(value) for value in content.values() if isinstance(value, str) and value.strip()]
    return []


def contains_placeholder(text: str) -> bool:
    return any(marker in normalize_text(text) for marker in ("lorem ipsum", "todo", "placeholder", "insert "))


def has_metric(text: str) -> bool:
    return bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:%|percent|users?|hours?|days?|teams?|applications?|defects?|records?)\b", text, flags=re.IGNORECASE))


def metric_supported(text: str, evidence_ids: list[str], evidence_index: list[ProfileEvidenceItem]) -> bool:
    generated_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", text))
    if not generated_numbers:
        return True
    evidence_by_id = {item.evidence_id: item for item in evidence_index}
    source_text = " ".join(evidence_by_id[eid].original_text for eid in evidence_ids if eid in evidence_by_id)
    source_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", source_text))
    return generated_numbers <= source_numbers


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def requirement_appears_in_text(requirement: str, text: str) -> bool:
    if len(requirement) < 2:
        return False
    escaped = re.escape(requirement)
    return bool(re.search(rf"(?<![a-z0-9+#.]){escaped}(?![a-z0-9+#.])", text))
