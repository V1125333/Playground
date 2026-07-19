from __future__ import annotations

import re

from app.schemas.resume import (
    ProfileEvidenceItem,
    ProfileMatchSummary,
    ResumeValidationIssue,
    ResumeValidationResult,
    StructuredGeneratedResume,
)
from app.services.structured_bullets import bullet_generated_text, bullet_text, normalize_structured_resume_bullets


def validate_structured_resume(
    resume: StructuredGeneratedResume,
    evidence_index: list[ProfileEvidenceItem],
    profile_match: ProfileMatchSummary,
) -> ResumeValidationResult:
    normalized_resume = normalize_structured_resume_bullets(resume)
    if normalized_resume is not resume:
        resume.sections = normalized_resume.sections
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
    safe_requirement_ids = {match.requirement_id for match in profile_match.matched_requirements}
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

        if section.type == "experience":
            validate_experience_bullets(
                section,
                evidence_index,
                evidence_ids,
                safe_requirement_ids,
                adjacent_requirement_ids,
                unmatched_requirement_ids,
                errors,
                warnings,
                rejected,
            )

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
                    texts.extend(bullet_text(value) for value in bullets if bullet_text(value))
        return [text for text in texts if text.strip()]
    if isinstance(content, dict):
        return [str(value) for value in content.values() if isinstance(value, str) and value.strip()]
    return []


def contains_placeholder(text: str) -> bool:
    return any(marker in normalize_text(text) for marker in ("lorem ipsum", "todo", "placeholder", "insert "))


def has_metric(text: str) -> bool:
    return bool(
        re.search(
            r"\b\d+(?:\.\d+)?\s*(?:%|percent\b|users?\b|hours?\b|days?\b|teams?\b|applications?\b|defects?\b|records?\b)",
            text,
            flags=re.IGNORECASE,
        )
    )


def metric_supported(text: str, evidence_ids: list[str], evidence_index: list[ProfileEvidenceItem]) -> bool:
    generated_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", text))
    if not generated_numbers:
        return True
    evidence_by_id = {item.evidence_id: item for item in evidence_index}
    source_text = " ".join(evidence_by_id[eid].original_text for eid in evidence_ids if eid in evidence_by_id)
    source_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", source_text))
    return generated_numbers <= source_numbers


def validate_experience_bullets(
    section,
    evidence_index: list[ProfileEvidenceItem],
    evidence_ids: set[str],
    safe_requirement_ids: set[str],
    adjacent_requirement_ids: set[str],
    unmatched_requirement_ids: set[str],
    errors: list[ResumeValidationIssue],
    warnings: list[ResumeValidationIssue],
    rejected: list[str],
) -> None:
    for entry in section.content if isinstance(section.content, list) else []:
        if not isinstance(entry, dict):
            continue
        for bullet in entry.get("bullets", []):
            if not isinstance(bullet, dict):
                continue
            bullet_id = str(bullet.get("bulletId") or section.section_id)
            current = bullet_text(bullet)
            generated = bullet_generated_text(bullet)
            bullet_evidence_ids = [str(value) for value in bullet.get("supportingEvidenceIds", []) if value]
            bullet_requirement_ids = [str(value) for value in bullet.get("supportedRequirementIds", []) if value]
            bullet["userEdited"] = bullet_is_user_edited(current, generated)
            bullet_warnings: list[str] = []
            bullet_errors: list[ResumeValidationIssue] = []
            has_bullet_provenance = bool(bullet_evidence_ids or bullet_requirement_ids)

            if bullet.get("validationStatus") == "validated" and not bullet_evidence_ids:
                bullet_errors.append(issue("missing_bullet_evidence", "error", "Validated bullet has no supporting evidence IDs.", section.section_id, bullet_id))
            if not has_bullet_provenance and bullet.get("validationStatus") != "validated":
                bullet_warnings.append("Bullet has no bullet-level provenance; validation required before treating it as evidence-backed.")
            missing_evidence = [evidence_id for evidence_id in bullet_evidence_ids if evidence_id not in evidence_ids]
            if missing_evidence:
                bullet_errors.append(issue("unknown_bullet_evidence", "error", "Bullet references unknown evidence IDs.", section.section_id, bullet_id, missing_evidence))
            invalid_requirements = [req_id for req_id in bullet_requirement_ids if req_id not in safe_requirement_ids]
            if invalid_requirements:
                code = "unsafe_bullet_requirement"
                if any(req_id in adjacent_requirement_ids for req_id in invalid_requirements):
                    code = "adjacent_requirement_claimed"
                if any(req_id in unmatched_requirement_ids for req_id in invalid_requirements):
                    code = "unmatched_requirement_claimed"
                bullet_errors.append(issue(code, "error", "Bullet references a requirement that is not safe for generation.", section.section_id, bullet_id))

            if current and bullet_evidence_ids:
                bullet_errors.extend(validate_bullet_claims(section.section_id, bullet_id, current, bullet_evidence_ids, evidence_index))

            if bullet_errors:
                bullet["validationStatus"] = "rejected"
                rejected.append(bullet_id)
                errors.extend(bullet_errors)
                bullet_warnings.extend(error.message for error in bullet_errors)
            elif bullet_warnings:
                bullet["validationStatus"] = "warning"
                warnings.append(issue("bullet_warning", "warning", bullet_warnings[0], section.section_id, bullet_id, bullet_evidence_ids))
            else:
                bullet["validationStatus"] = "validated"
            bullet["warnings"] = sorted(set(bullet_warnings))


def validate_bullet_claims(
    section_id: str,
    bullet_id: str,
    text: str,
    evidence_ids: list[str],
    evidence_index: list[ProfileEvidenceItem],
) -> list[ResumeValidationIssue]:
    errors: list[ResumeValidationIssue] = []
    normalized = normalize_text(text)
    evidence_text = normalize_text(" ".join(item.original_text for item in evidence_index if item.evidence_id in evidence_ids))

    if has_unsupported_phrase(normalized, evidence_text, ("led", "managed", "mentored", "supervised", "directed", "owned", "headed")):
        errors.append(issue("unsupported_leadership_claim", "error", "Edited bullet contains unsupported leadership or ownership wording.", section_id, bullet_id, evidence_ids))
    if has_unsupported_phrase(normalized, evidence_text, ("architecture", "architected", "greenfield", "system design", "enterprise-wide")):
        errors.append(issue("unsupported_architecture_claim", "error", "Edited bullet contains unsupported architecture or scale wording.", section_id, bullet_id, evidence_ids))
    if has_unsupported_phrase(normalized, evidence_text, ("epic bridges", "hl7", "fhir", "certified", "certification")):
        errors.append(issue("unsupported_product_or_certification", "error", "Edited bullet contains unsupported product, standard, or certification wording.", section_id, bullet_id, evidence_ids))
    if has_unsupported_phrase(normalized, evidence_text, ("kubernetes", "azure api management", "microservices", "react", "aws", "azure")):
        errors.append(issue("unsupported_technology_claim", "error", "Edited bullet contains a technology not present in supporting evidence.", section_id, bullet_id, evidence_ids))
    if has_compound_integration_claim(normalized) and not has_compound_integration_claim(evidence_text):
        errors.append(issue("unsupported_compound_relationship", "error", "Edited bullet claims an integration relationship not present in supporting evidence.", section_id, bullet_id, evidence_ids))
    if has_metric(text) and not metric_supported(text, evidence_ids, evidence_index):
        errors.append(issue("unsupported_metric", "error", "Edited bullet contains a metric not present in supporting evidence.", section_id, bullet_id, evidence_ids))
    return errors


def bullet_is_user_edited(current: str, generated: str) -> bool:
    if generated:
        return normalized_bullet_text(current) != normalized_bullet_text(generated)
    return bool(current.strip())


def normalized_bullet_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def has_unsupported_phrase(text: str, evidence_text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text and phrase not in evidence_text for phrase in phrases)


def has_compound_integration_claim(text: str) -> bool:
    return (
        "react" in text
        and ("asp.net core" in text or "asp net core" in text or "api" in text)
        and any(term in text for term in ("integrated with", "connected to", "consumed", "calling", "wired to"))
    )


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def requirement_appears_in_text(requirement: str, text: str) -> bool:
    if len(requirement) < 2:
        return False
    escaped = re.escape(requirement)
    return bool(re.search(rf"(?<![a-z0-9+#.]){escaped}(?![a-z0-9+#.])", text))
