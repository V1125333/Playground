from __future__ import annotations

import re
from typing import Any

from app.schemas.resume import (
    CandidateProfile,
    ExperienceCapabilitySelection,
    ExperienceEvidenceSelection,
    ExperienceIntelligencePlan,
    ExperiencePromptCapability,
    ExperiencePromptEvidence,
    ExperiencePromptInput,
    ExperiencePromptMetric,
    ExperiencePromptProject,
    ExperiencePromptRoleContext,
    ExperiencePromptTargetContext,
    ExperiencePromptTechnology,
    ExperiencePromptValidationResult,
    ExperienceRolePlan,
    ExperienceTechnologySelection,
    ExperienceWritingRules,
    ProfileEvidenceItem,
    ProfileEvidenceType,
    ResumeGenerationSettings,
    ResumeProject,
    TypedJobRequirement,
)
from app.services.experience_planner import EXPERIENCE_PLANNER_VERSION


EXPERIENCE_PROMPT_VERSION = "experience-prompt-v1"

PROMPT_INVALID_EVIDENCE_ID = "PROMPT_INVALID_EVIDENCE_ID"
PROMPT_WRONG_ROLE_EVIDENCE = "PROMPT_WRONG_ROLE_EVIDENCE"
PROMPT_UNMAPPED_PROJECT = "PROMPT_UNMAPPED_PROJECT"
PROMPT_UNSUPPORTED_TECHNOLOGY = "PROMPT_UNSUPPORTED_TECHNOLOGY"
PROMPT_UNSUPPORTED_CAPABILITY = "PROMPT_UNSUPPORTED_CAPABILITY"
PROMPT_UNSUPPORTED_METRIC = "PROMPT_UNSUPPORTED_METRIC"
PROMPT_CONFLICTING_EXCLUSION = "PROMPT_CONFLICTING_EXCLUSION"
PROMPT_INSUFFICIENT_EVIDENCE = "PROMPT_INSUFFICIENT_EVIDENCE"
PROMPT_DUPLICATE_EVIDENCE = "PROMPT_DUPLICATE_EVIDENCE"
PROMPT_GENERIC_THEMES_ONLY = "PROMPT_GENERIC_THEMES_ONLY"
PROMPT_BULLET_COUNT_EXCEEDS_EVIDENCE = "PROMPT_BULLET_COUNT_EXCEEDS_EVIDENCE"
PROMPT_METADATA_LEAKAGE = "PROMPT_METADATA_LEAKAGE"
PROMPT_PROJECT_NOT_LINKED = "PROMPT_PROJECT_NOT_LINKED"
PROMPT_PROJECT_WRONG_EXPERIENCE = "PROMPT_PROJECT_WRONG_EXPERIENCE"

GENERIC_THEMES = {
    "communication",
    "stakeholder collaboration",
    "technical documentation",
    "documentation",
    "agile",
    "scrum",
}


def build_experience_prompts(
    plan: ExperienceIntelligencePlan,
    profile: CandidateProfile,
    evidence_index: list[ProfileEvidenceItem],
    typed_requirements: Any,
    target_job: Any,
    generation_settings: ResumeGenerationSettings,
) -> ExperienceIntelligencePlan:
    prompts = [
        build_experience_prompt(role_plan, profile, evidence_index, typed_requirements, target_job, generation_settings)
        for role_plan in plan.roles
    ]
    warnings = [*plan.warnings]
    for prompt in prompts:
        warnings.extend(f"{prompt.experience_id}: {code}" for code in prompt.validation_result.codes)
        warnings.extend(f"{prompt.experience_id}: {warning}" for warning in prompt.validation_result.warnings)
    return plan.model_copy(
        update={
            "experience_prompt_inputs": prompts,
            "warnings": dedupe(warnings),
            "validation_status": "valid" if all(prompt.validation_result.is_valid for prompt in prompts) and not warnings else "warning",
        }
    )


def build_experience_prompt(
    role_plan: ExperienceRolePlan,
    profile: CandidateProfile,
    evidence_index: list[ProfileEvidenceItem],
    typed_requirements: Any,
    target_job: Any,
    generation_settings: ResumeGenerationSettings,
) -> ExperiencePromptInput:
    _ = generation_settings
    role = role_for_plan(profile, role_plan)
    evidence_by_id = {item.evidence_id: item for item in evidence_index}
    selected_evidence = list(role_plan.selected_evidence)
    approved_evidence = [
        prompt_evidence(item, evidence_by_id.get(item.evidence_id))
        for item in selected_evidence
        if evidence_boundary_valid(role_plan, item, evidence_by_id.get(item.evidence_id))
    ]
    approved_evidence_ids = {item.evidence_id for item in approved_evidence}
    approved_technologies = [
        prompt_technology(item, approved_evidence_ids, selected_evidence)
        for item in role_plan.selected_technologies
        if set(item.evidence_ids) & approved_evidence_ids
    ]
    approved_capabilities = [
        prompt_capability(item, approved_evidence_ids)
        for item in role_plan.selected_capabilities
        if set(item.evidence_ids) & approved_evidence_ids
    ]
    approved_metrics = [
        ExperiencePromptMetric(value=item.text, context=item.text, evidenceIds=[item.evidence_id])
        for item in selected_evidence
        if item.evidence_type == "metric" and item.evidence_id in approved_evidence_ids
    ]
    linked_projects = prompt_projects(role_plan, profile.projects, selected_evidence, approved_evidence_ids, approved_technologies)
    bullet_count = min(role_plan.bullet_count, len(approved_evidence))
    prompt = ExperiencePromptInput(
        experienceId=role_plan.experience_id,
        roleContext=ExperiencePromptRoleContext(
            roleTitle=role.role if role else role_plan.role_title,
            companyName=role.company if role else role_plan.company,
            clientName=role.client_name if role else None,
            isCurrentRole=bool(role.is_current_role) if role else False,
            roleFamily=role_plan.role_family,
        ),
        targetContext=ExperiencePromptTargetContext(
            targetRole=(getattr(target_job, "target_role", "") or "").strip(),
            targetCompany=(getattr(target_job, "target_company", "") or "").strip(),
            level=(getattr(target_job, "level", "") or "Senior").strip() or "Senior",
            targetThemes=role_plan.bullet_themes,
        ),
        approvedEvidence=approved_evidence,
        approvedTechnologies=approved_technologies,
        approvedCapabilities=approved_capabilities,
        approvedMetrics=approved_metrics,
        linkedProjects=linked_projects,
        bulletThemes=role_plan.bullet_themes,
        supportedRequirementIds=role_plan.supported_requirement_ids,
        excludedTerms=role_plan.excluded_jd_terms,
        writingRules=ExperienceWritingRules(
            bulletCount=bullet_count,
            maximumWordsPerBullet=30,
        ),
        plannerVersion=EXPERIENCE_PLANNER_VERSION,
        promptVersion=EXPERIENCE_PROMPT_VERSION,
        validationResult=ExperiencePromptValidationResult(isValid=True),
    )
    return prompt.model_copy(update={"validation_result": validate_experience_prompt(prompt, role_plan, profile, evidence_index, typed_requirements)})


def role_for_plan(profile: CandidateProfile, role_plan: ExperienceRolePlan):
    return next((item for item in profile.experience if item.experience_id == role_plan.experience_id), None)


def prompt_evidence(selection: ExperienceEvidenceSelection, indexed: ProfileEvidenceItem | None) -> ExperiencePromptEvidence:
    return ExperiencePromptEvidence(
        evidenceId=selection.evidence_id,
        evidenceType=prompt_evidence_type(selection.evidence_type),
        text=selection.text,
        sourceRecordId=selection.source_record_id,
        projectId=selection.project_id or (indexed.project_id if indexed else None) or None,
    )


def prompt_evidence_type(value: str) -> str:
    if value == "project_technology":
        return "technology"
    if value == "existing_bullet":
        return "existing_bullet"
    if value in {"responsibility", "achievement", "metric", "technology", "project"}:
        return value
    return value or "responsibility"


def prompt_technology(
    selection: ExperienceTechnologySelection,
    approved_evidence_ids: set[str],
    selected_evidence: list[ExperienceEvidenceSelection],
) -> ExperiencePromptTechnology:
    evidence_ids = [evidence_id for evidence_id in selection.evidence_ids if evidence_id in approved_evidence_ids]
    approved_names = [item.text for item in selected_evidence if item.evidence_id in evidence_ids]
    return ExperiencePromptTechnology(name=normalize_technology(selection.name, approved_names), evidenceIds=evidence_ids)


def prompt_capability(selection: ExperienceCapabilitySelection, approved_evidence_ids: set[str]) -> ExperiencePromptCapability:
    return ExperiencePromptCapability(
        name=selection.name,
        evidenceIds=[evidence_id for evidence_id in selection.evidence_ids if evidence_id in approved_evidence_ids],
        supportedRequirementIds=selection.supported_requirement_ids,
    )


def prompt_projects(
    role_plan: ExperienceRolePlan,
    projects: list[ResumeProject],
    selected_evidence: list[ExperienceEvidenceSelection],
    approved_evidence_ids: set[str],
    approved_technologies: list[ExperiencePromptTechnology],
) -> list[ExperiencePromptProject]:
    project_by_id = {project.project_id: project for project in projects if project.project_id}
    technology_by_evidence = {
        evidence_id: technology.name
        for technology in approved_technologies
        for evidence_id in technology.evidence_ids
    }
    output: list[ExperiencePromptProject] = []
    for project_id in dedupe([item.project_id for item in selected_evidence if item.project_id]):
        evidence = [
            item
            for item in selected_evidence
            if item.project_id == project_id and item.evidence_id in approved_evidence_ids and role_plan.experience_id in item.linked_experience_ids
        ]
        if not evidence:
            continue
        project = project_by_id.get(project_id)
        output.append(
            ExperiencePromptProject(
                projectId=project_id,
                projectName=project.name if project else project_id,
                evidenceIds=[item.evidence_id for item in evidence],
                technologies=dedupe([technology_by_evidence[item.evidence_id] for item in evidence if item.evidence_id in technology_by_evidence]),
                approvedFacts=[item.text for item in evidence if prompt_evidence_type(item.evidence_type) != "technology"],
            )
        )
    return output


def evidence_boundary_valid(role_plan: ExperienceRolePlan, selection: ExperienceEvidenceSelection, indexed: ProfileEvidenceItem | None) -> bool:
    if not indexed:
        return False
    role_record_id = f"experience-{role_plan.experience_id}"
    if selection.source_record_id == role_record_id:
        return True
    if indexed.evidence_type == ProfileEvidenceType.project:
        return bool(selection.project_id and role_plan.experience_id in selection.linked_experience_ids)
    return False


def validate_experience_prompt(
    prompt: ExperiencePromptInput,
    role_plan: ExperienceRolePlan,
    profile: CandidateProfile,
    evidence_index: list[ProfileEvidenceItem],
    typed_requirements: Any,
) -> ExperiencePromptValidationResult:
    codes: list[str] = []
    warnings: list[str] = []
    evidence_by_id = {item.evidence_id: item for item in evidence_index}
    valid_requirement_ids = requirement_ids(typed_requirements)
    valid_project_ids = {project.project_id for project in profile.projects if project.project_id}
    prompt_evidence_ids = [item.evidence_id for item in prompt.approved_evidence]
    if len(prompt_evidence_ids) != len(set(prompt_evidence_ids)):
        codes.append(PROMPT_DUPLICATE_EVIDENCE)
    if role_plan.bullet_count > 0 and not prompt.approved_evidence:
        codes.append(PROMPT_INSUFFICIENT_EVIDENCE)
    if prompt.writing_rules.bullet_count > len(prompt.approved_evidence):
        codes.append(PROMPT_BULLET_COUNT_EXCEEDS_EVIDENCE)
    if role_plan.bullet_count > len(prompt.approved_evidence):
        warnings.append(PROMPT_BULLET_COUNT_EXCEEDS_EVIDENCE)
    if prompt.bullet_themes and all(normalized(theme) in GENERIC_THEMES for theme in prompt.bullet_themes):
        warnings.append(PROMPT_GENERIC_THEMES_ONLY)
    for evidence in prompt.approved_evidence:
        indexed = evidence_by_id.get(evidence.evidence_id)
        if not indexed:
            codes.append(PROMPT_INVALID_EVIDENCE_ID)
            continue
        if metadata_leakage(evidence.text, prompt):
            codes.append(PROMPT_METADATA_LEAKAGE)
        if evidence.source_record_id == f"experience-{prompt.experience_id}":
            continue
        if indexed.evidence_type != ProfileEvidenceType.project:
            codes.append(PROMPT_WRONG_ROLE_EVIDENCE)
            continue
        if not indexed.linked_experience_ids:
            codes.append(PROMPT_UNMAPPED_PROJECT)
        if prompt.experience_id not in indexed.linked_experience_ids:
            codes.append(PROMPT_PROJECT_WRONG_EXPERIENCE)
        if evidence.project_id not in valid_project_ids:
            codes.append(PROMPT_PROJECT_NOT_LINKED)
    valid_evidence_ids = set(prompt_evidence_ids)
    for technology in prompt.approved_technologies:
        if not technology.evidence_ids or not set(technology.evidence_ids) <= valid_evidence_ids:
            codes.append(PROMPT_UNSUPPORTED_TECHNOLOGY)
    for capability in prompt.approved_capabilities:
        if not capability.evidence_ids or not set(capability.evidence_ids) <= valid_evidence_ids:
            codes.append(PROMPT_UNSUPPORTED_CAPABILITY)
        unsupported_requirements = [rid for rid in capability.supported_requirement_ids if valid_requirement_ids and rid not in valid_requirement_ids]
        if unsupported_requirements:
            codes.append(PROMPT_UNSUPPORTED_CAPABILITY)
    for metric in prompt.approved_metrics:
        if not metric.evidence_ids or not set(metric.evidence_ids) <= valid_evidence_ids:
            codes.append(PROMPT_UNSUPPORTED_METRIC)
        if not all("-metric-" in evidence_id for evidence_id in metric.evidence_ids):
            codes.append(PROMPT_UNSUPPORTED_METRIC)
    approved_terms = {normalized(item.name) for item in [*prompt.approved_technologies, *prompt.approved_capabilities]}
    if any(normalized(term) in approved_terms for term in prompt.excluded_terms):
        codes.append(PROMPT_CONFLICTING_EXCLUSION)
    for project in prompt.linked_projects:
        if project.project_id not in valid_project_ids:
            codes.append(PROMPT_PROJECT_NOT_LINKED)
        if not set(project.evidence_ids) <= valid_evidence_ids:
            codes.append(PROMPT_PROJECT_NOT_LINKED)
    return ExperiencePromptValidationResult(isValid=not codes, codes=dedupe(codes), warnings=dedupe(warnings))


def normalize_technology(value: str, approved_names: list[str]) -> str:
    text = " ".join(str(value or "").strip().split())
    key = normalized(text)
    approved = {normalized(item) for item in approved_names}
    if key in {"microsoft sql server", "ms sql server"}:
        return "SQL Server"
    if key in {"restful web api", "restful api", "web api"}:
        return "REST APIs"
    if "microsoft azure" in key and "azure" in approved:
        return "Azure"
    return text


def requirement_ids(typed_requirements: Any) -> set[str]:
    output: set[str] = set()
    for attr in (
        "technical_requirements",
        "responsibility_requirements",
        "experience_requirements",
        "education_requirements",
        "certification_requirements",
        "leadership_requirements",
        "soft_skill_requirements",
        "domain_requirements",
        "inferred_requirements",
    ):
        for item in getattr(typed_requirements, attr, []) or []:
            if isinstance(item, TypedJobRequirement):
                output.add(item.requirement_id)
            else:
                requirement_id = getattr(item, "requirement_id", "") or getattr(item, "requirementId", "")
                if requirement_id:
                    output.add(str(requirement_id))
    return output


def metadata_leakage(text: str, prompt: ExperiencePromptInput) -> bool:
    value = normalized(text)
    if not value:
        return False
    if re.search(r"[^@\s]+@[^@\s]+\.[^@\s]+", text):
        return True
    if re.search(r"\+?\d[\d\s().-]{7,}", text):
        return True
    metadata_values = {
        normalized(prompt.role_context.company_name),
        normalized(prompt.role_context.client_name or ""),
    }
    return value in {item for item in metadata_values if item}


def normalized(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


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
    "EXPERIENCE_PROMPT_VERSION",
    "build_experience_prompt",
    "build_experience_prompts",
    "validate_experience_prompt",
]
