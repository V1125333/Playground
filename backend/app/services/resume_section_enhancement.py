from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.schemas.resume import (
    SectionEnhancementApplyRequest,
    SectionEnhancementRequest,
    SectionEnhancementResponse,
    SectionEnhancementSuggestion,
    StructuredGeneratedResume,
    StructuredResumeRecord,
)
from app.services.ai_usage import get_ai_service, recent_job_id


SUPPORTED_SECTION_TYPES = {
    "summary",
    "experience_bullet",
    "experience_role",
    "project_bullet",
    "custom_section_text",
}

TECH_TERMS = {
    "aws",
    "azure",
    "azure devops",
    "google cloud",
    "gcp",
    "java",
    "spring boot",
    "python",
    "react",
    "angular",
    "node.js",
    "kubernetes",
    "docker",
    "databricks",
    "spark",
    "sql server",
    "c#",
    ".net",
    "asp.net core",
    "asp.net mvc",
    "rest api",
    "t-sql",
}

LEADERSHIP_TERMS = {"led", "lead", "mentored", "managed", "architected", "owned architecture", "technical strategy"}
ARCHITECTURE_TERMS = {"architecture", "architected", "solution design", "system design"}

PROMPT_SYSTEM = (
    "You are a professional resume editor. Improve only the selected resume section. "
    "Use only the approved evidence, technologies, requirements, and facts supplied in the request. "
    "Do not introduce any new claim. Do not invent metrics, technologies, leadership, architecture ownership, "
    "team size, business impact, certifications, responsibilities, projects, dates, locations, clients, or employers. "
    "Preserve the candidate's factual meaning. Improve clarity, grammar, conciseness, professional tone, ATS readability, "
    "action verbs, and sentence flow. Return structured JSON only."
)


@dataclass(frozen=True)
class SectionTarget:
    section_index: int
    section_id: str
    section_type: str
    target_id: str
    current_text: str
    original_text: str
    supporting_evidence_ids: tuple[str, ...]
    supported_requirement_ids: tuple[str, ...]
    metadata_terms: tuple[str, ...]
    approved_terms: tuple[str, ...]
    path: tuple[Any, ...]
    nearby_text: tuple[str, ...] = ()


class SectionEnhancementError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def api_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message}


@dataclass
class PendingSuggestion:
    resume_id: str
    section_type: str
    section_id: str
    expected_revision: str
    current_text_hash: str
    suggestion: SectionEnhancementSuggestion


_PENDING: dict[str, PendingSuggestion] = {}


async def generate_section_enhancement(
    record: StructuredResumeRecord,
    request: SectionEnhancementRequest,
    *,
    user_id: str,
) -> SectionEnhancementResponse:
    if not settings.ai_section_enhancement_enabled:
        raise SectionEnhancementError("SECTION_ENHANCEMENT_UNAVAILABLE", "AI section enhancement is disabled.", 503)
    if not settings.openai_api_key:
        raise SectionEnhancementError("SECTION_ENHANCEMENT_UNAVAILABLE", "AI section enhancement is unavailable.", 503)
    if request.section_type not in SUPPORTED_SECTION_TYPES:
        raise SectionEnhancementError("SECTION_ENHANCEMENT_UNSUPPORTED_TARGET", "This section cannot be enhanced with AI.")

    resume = record.resume_json
    target = find_section_target(resume, request.section_type, request.section_id, request.parent_section_id)
    if not target.current_text.strip():
        raise SectionEnhancementError("SECTION_ENHANCEMENT_EMPTY_TEXT", "There is no text to enhance.")
    if request.expected_revision and request.expected_revision != record.updated_at:
        raise SectionEnhancementError("SECTION_ENHANCEMENT_STALE_SUGGESTION", "This resume changed. Try enhancing the section again.", 409)

    response = await _call_model_with_retry(record, request, target, user_id)
    for suggestion in response.suggestions:
        _PENDING[suggestion.suggestion_id] = PendingSuggestion(
            resume_id=record.resume_id,
            section_type=request.section_type,
            section_id=request.section_id,
            expected_revision=record.updated_at,
            current_text_hash=text_hash(target.current_text),
            suggestion=suggestion,
        )
    return response


async def _call_model_with_retry(
    record: StructuredResumeRecord,
    request: SectionEnhancementRequest,
    target: SectionTarget,
    user_id: str,
) -> SectionEnhancementResponse:
    validation_errors: list[str] = []
    attempts = max(1, settings.section_enhancement_max_retries + 1)
    for attempt in range(attempts):
        payload = build_model_payload(record, request, target, validation_errors)
        try:
            ai_result = await get_ai_service().chat_completion(
                feature="resume_section_enhancement",
                purpose=f"Enhance {request.section_type}",
                model_key="section_enhancement",
                user=user_id,
                resume_id=record.resume_id,
                job_id=recent_job_id(record.job_description, record.target_job_title, record.target_company),
                messages=[
                    {"role": "system", "content": PROMPT_SYSTEM},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
                ],
                response_format={"type": "json_object"},
                temperature=0.25,
            )
        except Exception as exc:
            raise SectionEnhancementError(
                "SECTION_ENHANCEMENT_AI_UNAVAILABLE",
                section_enhancement_provider_message(exc),
                503,
            ) from exc
        try:
            suggestions = parse_suggestions(ai_result.content, request, target, ai_result.model)
            warnings = []
            valid_suggestions: list[SectionEnhancementSuggestion] = []
            for suggestion in suggestions:
                errors = validate_section_enhancement(target, suggestion)
                if errors:
                    validation_errors = errors
                    warnings.extend(errors)
                    continue
                valid_suggestions.append(suggestion)
            if valid_suggestions:
                return SectionEnhancementResponse(
                    suggestions=valid_suggestions[:3],
                    validationStatus="valid",
                    warnings=dedupe(warnings),
                    resumeRevision=record.updated_at,
                )
        except Exception as exc:
            validation_errors = ["SECTION_ENHANCEMENT_INVALID_OUTPUT", str(exc)[:160]]
    raise SectionEnhancementError(
        "SECTION_ENHANCEMENT_INVALID_OUTPUT",
        "AI could not produce a safe enhancement for this section. The original text was unchanged.",
        422,
    )


def build_model_payload(record: StructuredResumeRecord, request: SectionEnhancementRequest, target: SectionTarget, validation_errors: list[str]) -> dict[str, Any]:
    return {
        "task": "section_resume_text_enhancement",
        "promptVersion": settings.section_enhancement_prompt_version,
        "sectionType": request.section_type,
        "mode": request.enhancement_mode,
        "customInstruction": safe_instruction(request.instruction),
        "preserveLength": request.preserve_length,
        "maximumWords": request.maximum_words or default_word_limit(request.section_type),
        "selectedText": target.current_text,
        "originalGeneratedText": target.original_text,
        "nearbyTextForDuplicationCheck": list(target.nearby_text)[:6],
        "approvedFacts": {
            "supportingEvidenceIds": list(target.supporting_evidence_ids),
            "supportedRequirementIds": list(target.supported_requirement_ids),
            "approvedTermsAlreadySupported": list(target.approved_terms),
            "metadataTermsThatMustNotChange": list(target.metadata_terms),
        },
        "outputContract": {
            "suggestions": [
                {
                    "enhancedText": "string",
                    "explanation": "string",
                    "supportingEvidenceIds": ["string"],
                    "supportedRequirementIds": ["string"],
                }
            ]
        },
        "previousValidationErrors": validation_errors,
    }


def parse_suggestions(content: str, request: SectionEnhancementRequest, target: SectionTarget, model: str) -> list[SectionEnhancementSuggestion]:
    data = json.loads(content or "{}")
    items = data.get("suggestions")
    if not isinstance(items, list):
        raise ValueError("Model response did not include suggestions.")
    now = datetime.now(UTC).isoformat()
    output: list[SectionEnhancementSuggestion] = []
    for item in items[:3]:
        if not isinstance(item, dict):
            continue
        enhanced = clean_enhanced_text(str(item.get("enhancedText") or ""), request.section_type)
        if not enhanced:
            continue
        output.append(
            SectionEnhancementSuggestion(
                suggestionId=str(uuid.uuid4()),
                sectionType=request.section_type,
                sectionId=request.section_id,
                originalText=target.current_text,
                enhancedText=enhanced,
                explanation=clean_text(str(item.get("explanation") or "Polished wording while preserving supported facts.")),
                supportingEvidenceIds=valid_subset(item.get("supportingEvidenceIds"), target.supporting_evidence_ids),
                supportedRequirementIds=valid_subset(item.get("supportedRequirementIds"), target.supported_requirement_ids),
                validationStatus="valid",
                warnings=[],
                model=model,
                promptVersion=settings.section_enhancement_prompt_version,
                createdAt=now,
            )
        )
    if not output:
        raise ValueError("Model response did not include usable enhanced text.")
    return output


def validate_section_enhancement(target: SectionTarget, suggestion: SectionEnhancementSuggestion) -> list[str]:
    errors: list[str] = []
    original = target.current_text
    enhanced = suggestion.enhanced_text
    if not enhanced.strip():
        return ["SECTION_ENHANCEMENT_INVALID_OUTPUT"]
    for evidence_id in suggestion.supporting_evidence_ids:
        if evidence_id not in target.supporting_evidence_ids:
            errors.append("SECTION_ENHANCEMENT_INVALID_EVIDENCE_ID")
    for requirement_id in suggestion.supported_requirement_ids:
        if requirement_id not in target.supported_requirement_ids:
            errors.append("SECTION_ENHANCEMENT_INVALID_REQUIREMENT_ID")
    added_terms = terms_in(enhanced) - terms_in(original) - {term.casefold() for term in target.approved_terms}
    if added_terms:
        errors.append(f"SECTION_ENHANCEMENT_UNSUPPORTED_TECHNOLOGY: {', '.join(sorted(added_terms)[:4])}")
    if added_metric(original, enhanced):
        errors.append("SECTION_ENHANCEMENT_UNSUPPORTED_METRIC")
    if added_claim(original, enhanced, LEADERSHIP_TERMS):
        errors.append("SECTION_ENHANCEMENT_UNSUPPORTED_LEADERSHIP")
    if added_claim(original, enhanced, ARCHITECTURE_TERMS):
        errors.append("SECTION_ENHANCEMENT_UNSUPPORTED_ARCHITECTURE")
    if any(metadata_changed(term, original, enhanced) for term in target.metadata_terms if term):
        errors.append("SECTION_ENHANCEMENT_METADATA_CHANGED")
    if re.search(r"\b(I|me|my|we|our)\b", enhanced):
        errors.append("SECTION_ENHANCEMENT_INVALID_OUTPUT")
    if len(enhanced.split()) > max(160, len(original.split()) * 2 + 20):
        errors.append("SECTION_ENHANCEMENT_TOO_LONG")
    if normalized(enhanced) in {normalized(text) for text in target.nearby_text if text != original}:
        errors.append("SECTION_ENHANCEMENT_DUPLICATE_TEXT")
    return dedupe(errors)


def apply_section_enhancement_to_resume(
    record: StructuredResumeRecord,
    request: SectionEnhancementApplyRequest,
) -> StructuredGeneratedResume:
    pending = _PENDING.get(request.suggestion_id)
    if not pending or pending.resume_id != record.resume_id:
        raise SectionEnhancementError("SECTION_ENHANCEMENT_NOT_FOUND", "Enhancement suggestion expired. Try again.", 404)
    if request.expected_revision and request.expected_revision != record.updated_at:
        raise SectionEnhancementError("SECTION_ENHANCEMENT_STALE_SUGGESTION", "This resume changed. Try enhancing the section again.", 409)
    if pending.expected_revision != record.updated_at:
        raise SectionEnhancementError("SECTION_ENHANCEMENT_STALE_SUGGESTION", "This resume changed. Try enhancing the section again.", 409)

    resume = record.resume_json.model_copy(deep=True)
    target = find_section_target(resume, request.section_type, request.section_id, "")
    if text_hash(target.current_text) != pending.current_text_hash:
        raise SectionEnhancementError("SECTION_ENHANCEMENT_STALE_SUGGESTION", "This text changed. Try enhancing it again.", 409)

    updated = write_target_text(resume, target, pending.suggestion.enhanced_text)
    history = list(updated.enhancement_history)
    history.append(
        {
            "enhancementId": request.suggestion_id,
            "sectionType": request.section_type,
            "sectionId": request.section_id,
            "beforeText": pending.suggestion.original_text,
            "afterText": pending.suggestion.enhanced_text,
            "mode": pending.suggestion.prompt_version,
            "accepted": True,
            "model": pending.suggestion.model,
            "promptVersion": pending.suggestion.prompt_version,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )
    _PENDING.pop(request.suggestion_id, None)
    return updated.model_copy(update={"enhancement_history": history, "updated_at": datetime.now(UTC).isoformat()})


def find_section_target(resume: StructuredGeneratedResume, section_type: str, section_id: str, parent_section_id: str = "") -> SectionTarget:
    for section_index, section in enumerate(resume.sections):
        if parent_section_id and section.section_id != parent_section_id:
            continue
        if section_type in {"summary", "custom_section_text"} and section.section_id == section_id and isinstance(section.content, str):
            return target_from_section(section_index, section, section.content, section.content, (section_index, "content"))
        if section_type == "experience_bullet" and section.type == "experience":
            found = find_bullet_target(section_index, section, section_id, project=False)
            if found:
                return found
        if section_type == "experience_role" and section.type == "experience":
            found = find_role_target(section_index, section, section_id)
            if found:
                return found
        if section_type == "project_bullet" and section.type == "projects":
            found = find_bullet_target(section_index, section, section_id, project=True)
            if found:
                return found
    raise SectionEnhancementError("SECTION_ENHANCEMENT_SECTION_NOT_FOUND", "Selected resume section was not found.", 404)


def target_from_section(section_index: int, section, current: str, original: str, path: tuple[Any, ...], metadata: tuple[str, ...] = (), nearby: tuple[str, ...] = ()) -> SectionTarget:
    approved = tuple(sorted({*terms_in(current), *terms_in(original)}))
    return SectionTarget(
        section_index=section_index,
        section_id=section.section_id,
        section_type=section.type,
        target_id=section.section_id,
        current_text=current,
        original_text=original,
        supporting_evidence_ids=tuple(section.provenance.supporting_evidence_ids),
        supported_requirement_ids=tuple(section.provenance.supported_requirement_ids),
        metadata_terms=metadata,
        approved_terms=approved,
        path=path,
        nearby_text=nearby,
    )


def find_bullet_target(section_index: int, section, section_id: str, *, project: bool) -> SectionTarget | None:
    content = section.content if isinstance(section.content, list) else []
    for entry_index, entry in enumerate(content):
        if not isinstance(entry, dict):
            continue
        bullets = entry.get("bullets") if isinstance(entry.get("bullets"), list) else []
        for bullet_index, bullet in enumerate(bullets):
            bullet_id = bullet.get("bulletId") if isinstance(bullet, dict) else ""
            fallback_id = f"{entry.get('sourceRecordId') or entry.get('name') or entry_index}:bullet:{bullet_index}"
            if section_id not in {bullet_id, fallback_id}:
                continue
            current = bullet_text(bullet)
            generated = str(bullet.get("generatedText") or "") if isinstance(bullet, dict) else current
            metadata = metadata_terms(entry)
            evidence_ids = tuple(bullet.get("supportingEvidenceIds") or section.provenance.supporting_evidence_ids) if isinstance(bullet, dict) else tuple(section.provenance.supporting_evidence_ids)
            requirement_ids = tuple(bullet.get("supportedRequirementIds") or section.provenance.supported_requirement_ids) if isinstance(bullet, dict) else tuple(section.provenance.supported_requirement_ids)
            approved = tuple(sorted({*terms_in(current), *terms_in(generated), *terms_in(" ".join(entry.get("technologies") or []))}))
            return SectionTarget(
                section_index=section_index,
                section_id=section.section_id,
                section_type="project_bullet" if project else "experience_bullet",
                target_id=section_id,
                current_text=current,
                original_text=generated,
                supporting_evidence_ids=evidence_ids,
                supported_requirement_ids=requirement_ids,
                metadata_terms=metadata,
                approved_terms=approved,
                path=(section_index, "content", entry_index, "bullets", bullet_index),
                nearby_text=tuple(bullet_text(item) for item in bullets),
            )
    return None


def find_role_target(section_index: int, section, section_id: str) -> SectionTarget | None:
    content = section.content if isinstance(section.content, list) else []
    for entry_index, entry in enumerate(content):
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("sourceRecordId") or f"experience:{entry_index}")
        if section_id != entry_id:
            continue
        bullets = entry.get("bullets") if isinstance(entry.get("bullets"), list) else []
        text = "\n".join(f"- {bullet_text(bullet)}" for bullet in bullets if bullet_text(bullet))
        return SectionTarget(
            section_index=section_index,
            section_id=section.section_id,
            section_type="experience_role",
            target_id=section_id,
            current_text=text,
            original_text=text,
            supporting_evidence_ids=tuple(section.provenance.supporting_evidence_ids),
            supported_requirement_ids=tuple(section.provenance.supported_requirement_ids),
            metadata_terms=metadata_terms(entry),
            approved_terms=tuple(sorted(terms_in(text))),
            path=(section_index, "content", entry_index, "bullets"),
            nearby_text=tuple(bullet_text(item) for item in bullets),
        )
    return None


def write_target_text(resume: StructuredGeneratedResume, target: SectionTarget, text: str) -> StructuredGeneratedResume:
    sections = [section.model_copy(deep=True) for section in resume.sections]
    section = sections[target.section_index]
    path = target.path
    if path[-1] == "content":
        section.content = text
        section.provenance.validation_status = "needs_review"
        section.provenance.warnings = dedupe([*section.provenance.warnings, "AI enhanced this section; review before export."])
    elif len(path) >= 5 and path[-2] == "bullets":
        content = list(section.content)
        entry = dict(content[path[2]])
        bullets = list(entry.get("bullets") or [])
        bullet = bullets[path[4]]
        bullets[path[4]] = updated_bullet(bullet, text)
        entry["bullets"] = bullets
        content[path[2]] = entry
        section.content = content
    elif path[-1] == "bullets":
        content = list(section.content)
        entry = dict(content[path[2]])
        existing = list(entry.get("bullets") or [])
        lines = [line.strip(" -\t") for line in text.splitlines() if line.strip(" -\t")]
        entry["bullets"] = [updated_bullet(existing[index] if index < len(existing) else {}, line) for index, line in enumerate(lines[: len(existing)])]
        content[path[2]] = entry
        section.content = content
    sections[target.section_index] = section
    return resume.model_copy(update={"sections": sections})


def updated_bullet(bullet: Any, text: str) -> Any:
    if isinstance(bullet, dict):
        warnings = dedupe([*(bullet.get("warnings") or []), "AI enhanced this bullet; review before export."])
        return {**bullet, "currentText": text, "userEdited": True, "validationStatus": "needs_review", "warnings": warnings}
    return text


def bullet_text(bullet: Any) -> str:
    if isinstance(bullet, dict):
        return str(bullet.get("currentText") or bullet.get("generatedText") or "")
    return str(bullet or "")


def metadata_terms(entry: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(entry.get(key) or "").strip() for key in ("company", "role", "location", "name", "org", "startDate", "endDate") if str(entry.get(key) or "").strip())


def terms_in(text: str) -> set[str]:
    normalized_text = normalized(text)
    return {term for term in TECH_TERMS if term in normalized_text}


def added_metric(original: str, enhanced: str) -> bool:
    metric_pattern = r"(\d+(?:\.\d+)?\s?%|\$\d+|\b\d+\+?\s?(users|teams|projects|hours|days|months|records|defects|releases)\b)"
    return bool(re.search(metric_pattern, enhanced, re.I)) and not bool(re.search(metric_pattern, original, re.I))


def added_claim(original: str, enhanced: str, terms: set[str]) -> bool:
    original_text = normalized(original)
    enhanced_text = normalized(enhanced)
    return any(term in enhanced_text and term not in original_text for term in terms)


def metadata_changed(term: str, original: str, enhanced: str) -> bool:
    key = normalized(term)
    if not key or key not in normalized(original):
        return False
    return key not in normalized(enhanced)


def valid_subset(value: Any, allowed: tuple[str, ...]) -> list[str]:
    if not isinstance(value, list):
        return list(allowed)
    allowed_set = set(allowed)
    selected = [str(item) for item in value if str(item) in allowed_set]
    return selected or list(allowed)


def default_word_limit(section_type: str) -> int:
    return 90 if section_type == "summary" else 38


def safe_instruction(value: str) -> str:
    return clean_text(value)[:240]


def clean_text(value: str) -> str:
    return " ".join(value.replace("\r", "\n").split())


def section_enhancement_provider_message(exc: Exception) -> str:
    message = str(exc).casefold()
    if "insufficient_quota" in message or "exceeded your current quota" in message:
        return "OpenAI quota is exhausted for this API key. Check billing/quota, then try Enhance with AI again."
    if "model_not_found" in message or "does not exist or you do not have access" in message:
        model = settings.openai_section_enhancement_model
        return f"The configured OpenAI model for section enhancement is unavailable: {model}."
    if "api key" in message or "authentication" in message:
        return "OpenAI authentication failed. Check the API key before using Enhance with AI."
    return "AI section enhancement is temporarily unavailable. The original resume text was not changed."


def clean_enhanced_text(value: str, section_type: str) -> str:
    if section_type != "experience_role":
        return clean_text(value)
    lines = [clean_text(line.strip(" -\t")) for line in value.replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line)


def normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def text_hash(value: str) -> str:
    return hashlib.sha256(normalized(value).encode("utf-8")).hexdigest()


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = normalized(value)
        if key and key not in seen:
            seen.add(key)
            output.append(value)
    return output


__all__ = [
    "SectionEnhancementError",
    "apply_section_enhancement_to_resume",
    "generate_section_enhancement",
]
