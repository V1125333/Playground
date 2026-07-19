from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.resume import CandidateProfile, ResumeExperience, ResumeProject
from app.services.profile_service import ensure_profile_record_ids
from app.services.skill_registry import (
    REGISTERED_SKILLS,
    SkillDefinition,
    get_skill_definition,
    normalize_skill_name,
    skill_lookup_key,
)


SKILL_EVIDENCE_INDEX_VERSION = "skill-evidence-index-v1"

SKILL_EVIDENCE_INVALID_SOURCE_ID = "SKILL_EVIDENCE_INVALID_SOURCE_ID"
SKILL_EVIDENCE_DUPLICATE_ID = "SKILL_EVIDENCE_DUPLICATE_ID"
SKILL_EVIDENCE_UNKNOWN_SKILL = "SKILL_EVIDENCE_UNKNOWN_SKILL"
SKILL_EVIDENCE_PROFILE_ONLY = "SKILL_EVIDENCE_PROFILE_ONLY"
SKILL_EVIDENCE_UNSUPPORTED_INFERENCE = "SKILL_EVIDENCE_UNSUPPORTED_INFERENCE"
SKILL_EVIDENCE_INVALID_PROJECT_LINK = "SKILL_EVIDENCE_INVALID_PROJECT_LINK"
SKILL_EVIDENCE_INVALID_EXPERIENCE_LINK = "SKILL_EVIDENCE_INVALID_EXPERIENCE_LINK"
SKILL_EVIDENCE_CERTIFICATION_SCOPE_UNKNOWN = "SKILL_EVIDENCE_CERTIFICATION_SCOPE_UNKNOWN"
SKILL_EVIDENCE_BLANK_VALUE = "SKILL_EVIDENCE_BLANK_VALUE"
SKILL_EVIDENCE_METADATA_LEAKAGE = "SKILL_EVIDENCE_METADATA_LEAKAGE"
SKILL_EVIDENCE_NONDETERMINISTIC_ORDER = "SKILL_EVIDENCE_NONDETERMINISTIC_ORDER"
SKILL_NOT_REGISTERED = "SKILL_NOT_REGISTERED"
UNMAPPED_PROJECT_EXCLUDED = "UNMAPPED_PROJECT_EXCLUDED"

SkillEvidenceSourceType = Literal[
    "experience_technology",
    "experience_responsibility",
    "experience_achievement",
    "experience_metric",
    "existing_experience_bullet",
    "project_technology",
    "project_bullet",
    "profile_skill",
    "certification",
]
SkillEvidenceStrength = Literal["strong", "medium", "weak"]
SkillEvidenceRecency = Literal["current", "recent", "older", "unknown"]
SkillEvidenceValidationStatus = Literal["valid", "valid_with_warnings", "invalid"]


class SkillEvidenceRecord(BaseModel):
    skill_evidence_id: str = Field(alias="skillEvidenceId")
    original_value: str = Field(alias="originalValue")
    canonical_name: str | None = Field(default=None, alias="canonicalName")
    normalized_value: str = Field(alias="normalizedValue")
    category: str | None = None
    source_type: SkillEvidenceSourceType = Field(alias="sourceType")
    source_id: str = Field(alias="sourceId")
    evidence_id: str = Field(alias="evidenceId")
    experience_id: str | None = Field(default=None, alias="experienceId")
    project_id: str | None = Field(default=None, alias="projectId")
    linked_experience_ids: list[str] = Field(default_factory=list, alias="linkedExperienceIds")
    certification_id: str | None = Field(default=None, alias="certificationId")
    evidence_text: str = Field(alias="evidenceText")
    explicit: bool
    evidence_strength: SkillEvidenceStrength = Field(alias="evidenceStrength")
    recency: SkillEvidenceRecency
    allowed_for_skill_selection: bool = Field(alias="allowedForSkillSelection")
    inferred_from_canonical_skill: str | None = Field(default=None, alias="inferredFromCanonicalSkill")
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class SkillEvidenceSummary(BaseModel):
    canonical_name: str | None = Field(default=None, alias="canonicalName")
    normalized_value: str = Field(alias="normalizedValue")
    category: str | None = None
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")
    source_types: list[SkillEvidenceSourceType] = Field(default_factory=list, alias="sourceTypes")
    experience_ids: list[str] = Field(default_factory=list, alias="experienceIds")
    project_ids: list[str] = Field(default_factory=list, alias="projectIds")
    strongest_evidence: SkillEvidenceStrength = Field(alias="strongestEvidence")
    most_recent_evidence: SkillEvidenceRecency = Field(alias="mostRecentEvidence")
    explicit_evidence_count: int = Field(alias="explicitEvidenceCount")
    inferred_evidence_count: int = Field(alias="inferredEvidenceCount")
    profile_only: bool = Field(alias="profileOnly")
    allowed_for_skill_selection: bool = Field(alias="allowedForSkillSelection")
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class SkillEvidenceIndex(BaseModel):
    records: list[SkillEvidenceRecord] = Field(default_factory=list)
    summaries: list[SkillEvidenceSummary] = Field(default_factory=list)
    unknown_skills: list[SkillEvidenceSummary] = Field(default_factory=list, alias="unknownSkills")
    index_version: str = Field(default=SKILL_EVIDENCE_INDEX_VERSION, alias="indexVersion")
    validation_status: SkillEvidenceValidationStatus = Field(alias="validationStatus")
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


def build_skill_evidence_index(
    profile: CandidateProfile,
    *,
    registry: Iterable[SkillDefinition] = REGISTERED_SKILLS,
    reference_date: date | None = None,
) -> SkillEvidenceIndex:
    try:
        stable_profile = ensure_profile_record_ids(profile)
    except ValueError:
        # Some legacy/raw profile payloads may contain stale project links that
        # the canonical profile schema now rejects. The evidence index should
        # report those links deterministically instead of hiding them behind a
        # construction-time validation error.
        stable_profile = profile
    registry_items = sorted((item for item in registry if item.active), key=lambda item: (item.display_order, item.canonical_name))
    context = _IndexContext(stable_profile, registry_items, reference_date or date.today())
    records: list[SkillEvidenceRecord] = []

    records.extend(_profile_skill_records(stable_profile, context))
    for experience in stable_profile.experience:
        records.extend(_experience_records(experience, context))
    for project in stable_profile.projects:
        records.extend(_project_records(project, context))
    records.extend(_certification_records(stable_profile, context))

    records = sorted(records, key=_record_sort_key)
    validation_warnings = _validate_records(records, stable_profile, context)
    summaries = _build_summaries(records)
    unknown_skills = [item for item in summaries if item.canonical_name is None]
    warnings = _dedupe_preserve([*context.warnings, *validation_warnings, *[warning for summary in summaries for warning in summary.warnings]])
    validation_status: SkillEvidenceValidationStatus = "valid"
    if warnings:
        validation_status = "invalid" if _has_invalid_warning(warnings) else "valid_with_warnings"
    return SkillEvidenceIndex(
        records=records,
        summaries=summaries,
        unknownSkills=unknown_skills,
        validationStatus=validation_status,
        warnings=warnings,
    )


class _IndexContext:
    def __init__(self, profile: CandidateProfile, registry: list[SkillDefinition], reference_date: date) -> None:
        self.profile = profile
        self.registry = registry
        self.reference_date = reference_date
        self.experience_ids = {item.experience_id for item in profile.experience if item.experience_id}
        self.metadata_keys = _profile_metadata_keys(profile)
        self.warnings: list[str] = []


def _profile_skill_records(profile: CandidateProfile, context: _IndexContext) -> list[SkillEvidenceRecord]:
    records: list[SkillEvidenceRecord] = []
    for category_index, group in enumerate(profile.skills):
        for skill_index, value in enumerate(group.items):
            records.extend(
                _record_from_value(
                    value,
                    source_type="profile_skill",
                    source_id=f"profile-skill:{group.category_id or group.category}:{category_index}:{skill_index}",
                    evidence_text=value,
                    explicit=True,
                    evidence_strength="weak",
                    recency="unknown",
                    allowed_if_known=True,
                    context=context,
                )
            )
    return records


def _experience_records(experience: ResumeExperience, context: _IndexContext) -> list[SkillEvidenceRecord]:
    records: list[SkillEvidenceRecord] = []
    recency = _experience_recency(experience, context.reference_date)
    tech_strength: SkillEvidenceStrength = "strong" if recency in {"current", "recent"} else "medium"
    text_strength: SkillEvidenceStrength = "strong" if recency in {"current", "recent"} else "medium"

    for index, value in enumerate(experience.technologies):
        records.extend(
            _record_from_value(
                value,
                source_type="experience_technology",
                source_id=f"experience:{experience.experience_id}:technology:{index}",
                evidence_text=value,
                explicit=True,
                evidence_strength=tech_strength,
                recency=recency,
                allowed_if_known=True,
                context=context,
                experience_id=experience.experience_id,
            )
        )

    for source_type, values in (
        ("experience_responsibility", experience.responsibilities),
        ("experience_achievement", experience.achievements),
        ("existing_experience_bullet", experience.bullets),
    ):
        for index, text in enumerate(values):
            for canonical_name in _registered_skills_in_text(text, context.registry):
                records.append(
                    _known_record(
                        original_value=canonical_name,
                        canonical_name=canonical_name,
                        source_type=source_type,  # type: ignore[arg-type]
                        source_id=f"experience:{experience.experience_id}:{source_type}:{index}:{skill_lookup_key(canonical_name)}",
                        evidence_text=text,
                        explicit=False,
                        evidence_strength=text_strength if source_type != "existing_experience_bullet" else "medium",
                        recency=recency,
                        allowed=True,
                        experience_id=experience.experience_id,
                    )
                )

    for index, metric in enumerate(experience.metrics):
        text = " ".join(item for item in (metric.label, metric.value) if item)
        for canonical_name in _registered_skills_in_text(text, context.registry):
            records.append(
                _known_record(
                    original_value=canonical_name,
                    canonical_name=canonical_name,
                    source_type="experience_metric",
                    source_id=f"experience:{experience.experience_id}:metric:{metric.metric_id or index}:{skill_lookup_key(canonical_name)}",
                    evidence_text=text,
                    explicit=False,
                    evidence_strength="medium",
                    recency=recency,
                    allowed=True,
                    experience_id=experience.experience_id,
                )
            )

    return records


def _project_records(project: ResumeProject, context: _IndexContext) -> list[SkillEvidenceRecord]:
    records: list[SkillEvidenceRecord] = []
    valid_links = [experience_id for experience_id in project.linked_experience_ids if experience_id in context.experience_ids]
    invalid_links = [experience_id for experience_id in project.linked_experience_ids if experience_id not in context.experience_ids]
    if invalid_links:
        context.warnings.append(SKILL_EVIDENCE_INVALID_PROJECT_LINK)
    if not project.linked_experience_ids:
        context.warnings.append(UNMAPPED_PROJECT_EXCLUDED)

    project_strength: SkillEvidenceStrength = "strong" if project.bullets else "medium"
    for index, value in enumerate(project.technologies):
        records.extend(
            _record_from_value(
                value,
                source_type="project_technology",
                source_id=f"project:{project.project_id}:technology:{index}",
                evidence_text=value,
                explicit=True,
                evidence_strength=project_strength,
                recency="unknown",
                allowed_if_known=True,
                context=context,
                project_id=project.project_id,
                linked_experience_ids=valid_links,
            )
        )
    for index, text in enumerate(project.bullets):
        for canonical_name in _registered_skills_in_text(text, context.registry):
            records.append(
                _known_record(
                    original_value=canonical_name,
                    canonical_name=canonical_name,
                    source_type="project_bullet",
                    source_id=f"project:{project.project_id}:bullet:{index}:{skill_lookup_key(canonical_name)}",
                    evidence_text=text,
                    explicit=False,
                    evidence_strength="medium",
                    recency="unknown",
                    allowed=True,
                    project_id=project.project_id,
                    linked_experience_ids=valid_links,
                )
            )
    return records


def _certification_records(profile: CandidateProfile, context: _IndexContext) -> list[SkillEvidenceRecord]:
    records: list[SkillEvidenceRecord] = []
    for index, certification in enumerate(profile.certifications):
        text = " ".join(value for value in (certification.name, certification.issuer) if value)
        canonical_names = _certification_skill_scope(text)
        if not canonical_names and text.strip():
            context.warnings.append(SKILL_EVIDENCE_CERTIFICATION_SCOPE_UNKNOWN)
            continue
        for canonical_name in canonical_names:
            records.append(
                _known_record(
                    original_value=canonical_name,
                    canonical_name=canonical_name,
                    source_type="certification",
                    source_id=f"certification:{certification.certification_id or index}:{skill_lookup_key(canonical_name)}",
                    evidence_text=text,
                    explicit=True,
                    evidence_strength="medium",
                    recency="unknown",
                    allowed=True,
                    certification_id=certification.certification_id,
                    warnings=["CERTIFICATION_SCOPED"],
                )
            )
    return records


def _record_from_value(
    value: str,
    *,
    source_type: SkillEvidenceSourceType,
    source_id: str,
    evidence_text: str,
    explicit: bool,
    evidence_strength: SkillEvidenceStrength,
    recency: SkillEvidenceRecency,
    allowed_if_known: bool,
    context: _IndexContext,
    experience_id: str | None = None,
    project_id: str | None = None,
    linked_experience_ids: list[str] | None = None,
) -> list[SkillEvidenceRecord]:
    original = _clean_text(value)
    if not original:
        context.warnings.append(SKILL_EVIDENCE_BLANK_VALUE)
        return []
    warnings: list[str] = []
    if skill_lookup_key(original) in context.metadata_keys:
        warnings.append(SKILL_EVIDENCE_METADATA_LEAKAGE)
    normalized = normalize_skill_name(original)
    if not normalized.canonical_name:
        return [
            SkillEvidenceRecord(
                skillEvidenceId=_stable_id("skill-evidence", source_id, normalized.normalized_value or original),
                originalValue=original,
                canonicalName=None,
                normalizedValue=normalized.normalized_value,
                category=None,
                sourceType=source_type,
                sourceId=source_id,
                evidenceId=_stable_id("evidence", source_id, original),
                experienceId=experience_id,
                projectId=project_id,
                linkedExperienceIds=linked_experience_ids or [],
                evidenceText=evidence_text,
                explicit=explicit,
                evidenceStrength=evidence_strength,
                recency=recency,
                allowedForSkillSelection=False,
                inferredFromCanonicalSkill=None,
                warnings=_dedupe_preserve([SKILL_NOT_REGISTERED, SKILL_EVIDENCE_UNKNOWN_SKILL, *warnings]),
            )
        ]
    return [
        _known_record(
            original_value=original,
            canonical_name=normalized.canonical_name,
            source_type=source_type,
            source_id=source_id,
            evidence_text=evidence_text,
            explicit=explicit,
            evidence_strength=evidence_strength,
            recency=recency,
            allowed=allowed_if_known and not warnings,
            experience_id=experience_id,
            project_id=project_id,
            linked_experience_ids=linked_experience_ids or [],
            warnings=warnings,
        )
    ]


def _known_record(
    *,
    original_value: str,
    canonical_name: str,
    source_type: SkillEvidenceSourceType,
    source_id: str,
    evidence_text: str,
    explicit: bool,
    evidence_strength: SkillEvidenceStrength,
    recency: SkillEvidenceRecency,
    allowed: bool,
    experience_id: str | None = None,
    project_id: str | None = None,
    linked_experience_ids: list[str] | None = None,
    certification_id: str | None = None,
    warnings: list[str] | None = None,
) -> SkillEvidenceRecord:
    definition = get_skill_definition(canonical_name)
    category = definition.category if definition else None
    normalized = skill_lookup_key(canonical_name)
    return SkillEvidenceRecord(
        skillEvidenceId=_stable_id("skill-evidence", source_id, canonical_name),
        originalValue=original_value,
        canonicalName=canonical_name,
        normalizedValue=normalized,
        category=category,
        sourceType=source_type,
        sourceId=source_id,
        evidenceId=_stable_id("evidence", source_id, evidence_text, canonical_name),
        experienceId=experience_id,
        projectId=project_id,
        linkedExperienceIds=linked_experience_ids or [],
        certificationId=certification_id,
        evidenceText=evidence_text,
        explicit=explicit,
        evidenceStrength=evidence_strength,
        recency=recency,
        allowedForSkillSelection=allowed,
        inferredFromCanonicalSkill=None,
        warnings=warnings or [],
    )


def _registered_skills_in_text(text: str, registry: list[SkillDefinition]) -> list[str]:
    normalized_text = f" {skill_lookup_key(text)} "
    if not normalized_text.strip():
        return []
    found: list[tuple[int, str]] = []
    for definition in registry:
        phrases = [definition.canonical_name, *definition.aliases]
        if any(f" {skill_lookup_key(phrase)} " in normalized_text for phrase in phrases if skill_lookup_key(phrase)):
            found.append((definition.display_order, definition.canonical_name))
    return [name for _, name in sorted(found)]


def _certification_skill_scope(text: str) -> list[str]:
    key = skill_lookup_key(text)
    scopes: list[str] = []
    if "azure fundamentals" in key or "az 900" in key:
        scopes.append("Azure")
    if "databricks" in key:
        scopes.append("Azure Databricks")
    if "aws certified" in key or "aws cloud practitioner" in key:
        scopes.append("AWS")
    return [scope for scope in scopes if get_skill_definition(scope)]


def _build_summaries(records: list[SkillEvidenceRecord]) -> list[SkillEvidenceSummary]:
    grouped: dict[tuple[str, str], list[SkillEvidenceRecord]] = {}
    for record in records:
        key = (record.canonical_name or "", record.normalized_value)
        grouped.setdefault(key, []).append(record)

    summaries: list[SkillEvidenceSummary] = []
    for (_, _), items in grouped.items():
        first = items[0]
        source_types = _dedupe_preserve([item.source_type for item in items])
        profile_only = all(item.source_type == "profile_skill" for item in items)
        warnings = _dedupe_preserve([warning for item in items for warning in item.warnings])
        if profile_only:
            warnings.append(SKILL_EVIDENCE_PROFILE_ONLY)
        if first.canonical_name is None:
            warnings = _dedupe_preserve([SKILL_NOT_REGISTERED, SKILL_EVIDENCE_UNKNOWN_SKILL, *warnings])
        summaries.append(
            SkillEvidenceSummary(
                canonicalName=first.canonical_name,
                normalizedValue=first.normalized_value,
                category=first.category,
                evidenceIds=_dedupe_preserve([item.evidence_id for item in items]),
                sourceTypes=source_types,
                experienceIds=_dedupe_preserve([item.experience_id for item in items if item.experience_id]),
                projectIds=_dedupe_preserve([item.project_id for item in items if item.project_id]),
                strongestEvidence=max((item.evidence_strength for item in items), key=_strength_rank),
                mostRecentEvidence=max((item.recency for item in items), key=_recency_rank),
                explicitEvidenceCount=sum(1 for item in items if item.explicit),
                inferredEvidenceCount=sum(1 for item in items if not item.explicit),
                profileOnly=profile_only,
                allowedForSkillSelection=any(item.allowed_for_skill_selection for item in items) and first.canonical_name is not None,
                warnings=warnings,
            )
        )
    return sorted(summaries, key=_summary_sort_key)


def _validate_records(records: list[SkillEvidenceRecord], profile: CandidateProfile, context: _IndexContext) -> list[str]:
    warnings: list[str] = []
    seen: set[str] = set()
    for record in records:
        if not record.source_id.strip() or not record.evidence_id.strip():
            warnings.append(SKILL_EVIDENCE_INVALID_SOURCE_ID)
        if record.skill_evidence_id in seen:
            warnings.append(SKILL_EVIDENCE_DUPLICATE_ID)
        seen.add(record.skill_evidence_id)
        if record.experience_id and record.experience_id not in context.experience_ids:
            warnings.append(SKILL_EVIDENCE_INVALID_EXPERIENCE_LINK)
        for experience_id in record.linked_experience_ids:
            if experience_id not in context.experience_ids:
                warnings.append(SKILL_EVIDENCE_INVALID_PROJECT_LINK)
    if [item.skill_evidence_id for item in records] != sorted(item.skill_evidence_id for item in records):
        # Sorting is handled by this service. This warning is retained as a guard
        # if callers later bypass build_skill_evidence_index and validate records directly.
        warnings.append(SKILL_EVIDENCE_NONDETERMINISTIC_ORDER)
    return _dedupe_preserve(warnings)


def _experience_recency(experience: ResumeExperience, reference_date: date) -> SkillEvidenceRecency:
    if experience.is_current_role or experience.end_date.strip().casefold() == "present":
        return "current"
    end_date = _parse_profile_date(experience.end_date)
    if not end_date:
        return "unknown"
    months = (reference_date.year - end_date.year) * 12 + (reference_date.month - end_date.month)
    return "recent" if months <= 36 else "older"


def _parse_profile_date(value: str) -> date | None:
    text = _clean_text(value)
    if not text:
        return None
    match = re.search(r"(\d{4})[-/](\d{1,2})", text)
    if match:
        return date(int(match.group(1)), max(1, min(12, int(match.group(2)))), 1)
    match = re.search(r"(\d{4})", text)
    if match:
        return date(int(match.group(1)), 1, 1)
    return None


def _profile_metadata_keys(profile: CandidateProfile) -> set[str]:
    values: list[str] = [
        profile.name,
        profile.first_name,
        profile.last_name,
        profile.title,
        profile.contact.email,
        profile.contact.phone,
        profile.contact.location,
        profile.contact.linkedin,
        profile.contact.github,
        profile.contact.portfolio,
    ]
    for experience in profile.experience:
        values.extend([experience.company, experience.client_name or "", experience.role, experience.location, experience.start_date, experience.end_date])
    for project in profile.projects:
        values.extend([project.name, project.org, project.link])
    return {skill_lookup_key(value) for value in values if skill_lookup_key(value)}


def _record_sort_key(record: SkillEvidenceRecord) -> tuple[str, str, str]:
    return (record.skill_evidence_id, record.source_type, record.source_id)


def _summary_sort_key(summary: SkillEvidenceSummary) -> tuple[int, str]:
    if summary.canonical_name:
        definition = get_skill_definition(summary.canonical_name)
        return (definition.display_order if definition else 10_000, summary.canonical_name.casefold())
    return (20_000, summary.normalized_value)


def _strength_rank(value: SkillEvidenceStrength) -> int:
    return {"weak": 0, "medium": 1, "strong": 2}[value]


def _recency_rank(value: SkillEvidenceRecency) -> int:
    return {"unknown": 0, "older": 1, "recent": 2, "current": 3}[value]


def _has_invalid_warning(warnings: list[str]) -> bool:
    invalid = {
        SKILL_EVIDENCE_DUPLICATE_ID,
        SKILL_EVIDENCE_INVALID_SOURCE_ID,
        SKILL_EVIDENCE_INVALID_PROJECT_LINK,
        SKILL_EVIDENCE_INVALID_EXPERIENCE_LINK,
        SKILL_EVIDENCE_METADATA_LEAKAGE,
        SKILL_EVIDENCE_NONDETERMINISTIC_ORDER,
    }
    return any(warning in invalid for warning in warnings)


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "|".join(_clean_text(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _dedupe_preserve(values: Iterable) -> list:
    output = []
    seen: set[str] = set()
    for value in values:
        key = str(value)
        if key and key not in seen:
            seen.add(key)
            output.append(value)
    return output


__all__ = [
    "SKILL_EVIDENCE_INDEX_VERSION",
    "SKILL_EVIDENCE_INVALID_SOURCE_ID",
    "SKILL_EVIDENCE_DUPLICATE_ID",
    "SKILL_EVIDENCE_UNKNOWN_SKILL",
    "SKILL_EVIDENCE_PROFILE_ONLY",
    "SKILL_EVIDENCE_UNSUPPORTED_INFERENCE",
    "SKILL_EVIDENCE_INVALID_PROJECT_LINK",
    "SKILL_EVIDENCE_INVALID_EXPERIENCE_LINK",
    "SKILL_EVIDENCE_CERTIFICATION_SCOPE_UNKNOWN",
    "SKILL_EVIDENCE_BLANK_VALUE",
    "SKILL_EVIDENCE_METADATA_LEAKAGE",
    "SKILL_EVIDENCE_NONDETERMINISTIC_ORDER",
    "SKILL_NOT_REGISTERED",
    "SkillEvidenceRecord",
    "SkillEvidenceSummary",
    "SkillEvidenceIndex",
    "build_skill_evidence_index",
]
