from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.schemas.resume import (
    EvidenceInspection,
    ExperienceBulletInspection,
    ExperienceOverview,
    ExperienceRoleInspection,
    ExcludedSkillInspection,
    InspectionMetrics,
    InspectorWarning,
    RequirementCoverageInspection,
    RequirementInspection,
    ResumeIntelligenceInspection,
    SkillsOverview,
    SkillInspection,
    SummaryInspection,
    VersionInspection,
)
from app.services.resume_intelligence_store import experience_intelligence_stale_reasons, normalized
from app.services.skills_rendering import SkillsRenderingPolicy
from app.services.skills_planner import skills_intelligence_stale_reasons
from app.services.summary_generation_service import SUMMARY_PROMPT_VERSION
from app.services.summary_intelligence import summary_model_configuration_hash


INSPECTOR_SUMMARY_INTELLIGENCE_MISSING = "INSPECTOR_SUMMARY_INTELLIGENCE_MISSING"
INSPECTOR_EXPERIENCE_INTELLIGENCE_MISSING = "INSPECTOR_EXPERIENCE_INTELLIGENCE_MISSING"
INSPECTOR_SKILLS_INTELLIGENCE_MISSING = "INSPECTOR_SKILLS_INTELLIGENCE_MISSING"
INSPECTOR_EVIDENCE_NOT_FOUND = "INSPECTOR_EVIDENCE_NOT_FOUND"
INSPECTOR_REQUIREMENT_NOT_FOUND = "INSPECTOR_REQUIREMENT_NOT_FOUND"
INSPECTOR_VERSION_METADATA_MISSING = "INSPECTOR_VERSION_METADATA_MISSING"
INSPECTOR_INVALID_EVIDENCE_REFERENCE = "INSPECTOR_INVALID_EVIDENCE_REFERENCE"
INSPECTOR_INVALID_REQUIREMENT_REFERENCE = "INSPECTOR_INVALID_REQUIREMENT_REFERENCE"
INSPECTOR_DUPLICATE_BULLET_ID = "INSPECTOR_DUPLICATE_BULLET_ID"
INSPECTOR_DUPLICATE_SKILL_ID = "INSPECTOR_DUPLICATE_SKILL_ID"
INSPECTOR_INCLUDED_EXCLUDED_CONFLICT = "INSPECTOR_INCLUDED_EXCLUDED_CONFLICT"
INSPECTOR_COVERAGE_COUNT_MISMATCH = "INSPECTOR_COVERAGE_COUNT_MISMATCH"
INSPECTOR_METADATA_LEAKAGE = "INSPECTOR_METADATA_LEAKAGE"


def inspect_resume_intelligence_package(package, profile_record=None) -> ResumeIntelligenceInspection:
    context = _InspectionContext(package, profile_record)
    summary = inspect_summary(package, context=context)
    experience = _experience_overview(package, context)
    skills = _skills_overview(package, context)
    coverage = _requirement_coverage(package, summary, experience, skills, context)
    stale_reasons = _stale_reasons(package, profile_record)
    warnings = _stable_warnings(
        [
            *context.warnings,
            *summary.warnings,
            *experience_warnings(experience),
            *skill_warnings(skills),
            *_coverage_warnings(coverage),
            *[_stale_warning(reason) for reason in stale_reasons],
        ]
    )
    metrics = _metrics(summary, experience, skills, coverage, warnings)
    covered_count = sum(1 for item in coverage if item.covered)
    if metrics.covered_requirement_count != covered_count:
        warnings = _stable_warnings([*warnings, _warning(INSPECTOR_COVERAGE_COUNT_MISMATCH, "Requirement coverage counts do not match coverage rows.")])
        metrics.warning_count = len(warnings)
    return ResumeIntelligenceInspection(
        packageId=str(_field(package, "id", "packageId") or ""),
        status=str(_field(package, "validation_status", "validationStatus") or ""),
        stale=_is_stale(package, stale_reasons),
        staleReasons=stale_reasons,
        warnings=warnings,
        profileId=str(_field(package, "profile_id", "profileId") or ""),
        profileVersion=int(_field(package, "profile_version", "profileVersion") or 0),
        profileHash=str(_field(package, "profile_content_hash", "profileHash") or ""),
        jdHash=str(_field(package, "job_description_hash", "jobDescriptionHash") or ""),
        targetRole=str(_field(package, "target_role", "targetRole") or ""),
        targetCompany=str(_field(package, "target_company", "targetCompany") or ""),
        targetLevel=str(_field(package, "level", "targetLevel") or ""),
        createdAt=_to_iso(_field(package, "created_at", "createdAt")),
        summary=summary,
        experienceOverview=experience,
        skillsOverview=skills,
        requirementCoverage=coverage,
        versions=_versions(package),
        metrics=metrics,
    )


def inspect_summary(package, context: "_InspectionContext | None" = None) -> SummaryInspection:
    context = context or _InspectionContext(package)
    data = _json_field(package, "summary_intelligence_json", "summaryIntelligence")
    if not data:
        warning = _warning(INSPECTOR_SUMMARY_INTELLIGENCE_MISSING, "Summary Intelligence is missing from this package.")
        return SummaryInspection(warnings=[warning])
    evidence_ids = _string_list(_get(data, "usedEvidenceIds", "used_evidence_ids"))
    requirement_ids = _string_list(_get(data, "supportedRequirementIds", "supported_requirement_ids"))
    warnings = [_warning("SUMMARY_VALIDATION_WARNING", item) for item in _string_list(_get(data, "validationWarnings", "validation_warnings"))]
    warnings.extend(context.reference_warnings(evidence_ids, requirement_ids))
    return SummaryInspection(
        generatedText=_safe_text(_get(data, "summary")),
        currentText=_safe_text(_get(data, "summary")),
        validationStatus=str(_get(data, "validationStatus", "validation_status") or ""),
        supportingEvidenceIds=evidence_ids,
        supportedRequirementIds=requirement_ids,
        plannerVersion=str(_get(data, "plannerVersion", "planner_version") or ""),
        promptVersion=str(_get(data, "promptVersion", "prompt_version") or ""),
        model=str(_get(data, "model") or ""),
        warnings=_stable_warnings(warnings),
        evidenceDetails=context.evidence_details(evidence_ids),
        requirementDetails=context.requirement_details(requirement_ids),
    )


def inspect_experience_role(package, experience_id: str) -> ExperienceRoleInspection:
    context = _InspectionContext(package)
    for role in _experience_overview(package, context).roles:
        if role.experience_id == experience_id:
            return role
    return ExperienceRoleInspection(
        experienceId=experience_id,
        validationStatus="missing",
        warnings=[_warning(INSPECTOR_REQUIREMENT_NOT_FOUND, f"Experience role not found: {experience_id}")],
    )


def inspect_experience_bullet(package, experience_id: str, bullet_id: str) -> ExperienceBulletInspection:
    role = inspect_experience_role(package, experience_id)
    for bullet in role.bullets:
        if bullet.bullet_id == bullet_id:
            return bullet
    return ExperienceBulletInspection(
        bulletId=bullet_id,
        experienceId=experience_id,
        validationStatus="missing",
        warnings=[_warning(INSPECTOR_REQUIREMENT_NOT_FOUND, f"Experience bullet not found: {bullet_id}")],
    )


def inspect_skill(package, skill_id: str) -> SkillInspection:
    context = _InspectionContext(package)
    for skill in _skills_overview(package, context).skills:
        if skill.skill_id == skill_id:
            return skill
    return SkillInspection(
        skillId=skill_id,
        warnings=[_warning(INSPECTOR_REQUIREMENT_NOT_FOUND, f"Skill not found: {skill_id}")],
    )


def inspect_excluded_skill(package, requirement_id: str) -> ExcludedSkillInspection:
    context = _InspectionContext(package)
    for skill in _skills_overview(package, context).excluded_skills:
        if requirement_id in skill.requirement_ids:
            return skill
    return ExcludedSkillInspection(
        requirementIds=[requirement_id],
        exclusionCode="not_found",
        reason=f"Excluded skill not found for requirement {requirement_id}.",
    )


def inspect_requirement_coverage(package, requirement_id: str) -> RequirementCoverageInspection:
    inspection = inspect_resume_intelligence_package(package)
    for item in inspection.requirement_coverage:
        if item.requirement_id == requirement_id:
            return item
    return RequirementCoverageInspection(
        requirementId=requirement_id,
        warnings=[_warning(INSPECTOR_REQUIREMENT_NOT_FOUND, f"Requirement not found: {requirement_id}")],
    )


class _InspectionContext:
    def __init__(self, package, profile_record=None):
        self.package = package
        self.profile_record = profile_record
        self.requirements = _requirement_map(package)
        self.evidence = _evidence_map(package)
        self.warnings: list[InspectorWarning] = []

    def evidence_details(self, evidence_ids: list[str]) -> list[EvidenceInspection]:
        details: list[EvidenceInspection] = []
        for evidence_id in _dedupe(evidence_ids):
            detail = self.evidence.get(evidence_id)
            if detail:
                details.append(detail)
            else:
                details.append(
                    EvidenceInspection(
                        evidenceId=evidence_id,
                        warnings=[_warning(INSPECTOR_EVIDENCE_NOT_FOUND, f"Evidence not found: {evidence_id}")],
                    )
                )
        return details

    def requirement_details(self, requirement_ids: list[str]) -> list[RequirementInspection]:
        details: list[RequirementInspection] = []
        for requirement_id in _dedupe(requirement_ids):
            detail = self.requirements.get(requirement_id)
            if detail:
                details.append(detail)
            else:
                details.append(
                    RequirementInspection(
                        requirementId=requirement_id,
                        warnings=[_warning(INSPECTOR_REQUIREMENT_NOT_FOUND, f"Requirement not found: {requirement_id}")],
                    )
                )
        return details

    def reference_warnings(self, evidence_ids: list[str], requirement_ids: list[str]) -> list[InspectorWarning]:
        warnings: list[InspectorWarning] = []
        for evidence_id in evidence_ids:
            if evidence_id and evidence_id not in self.evidence:
                warnings.append(_warning(INSPECTOR_INVALID_EVIDENCE_REFERENCE, f"Evidence reference does not resolve: {evidence_id}"))
        for requirement_id in requirement_ids:
            if requirement_id and requirement_id not in self.requirements:
                warnings.append(_warning(INSPECTOR_INVALID_REQUIREMENT_REFERENCE, f"Requirement reference does not resolve: {requirement_id}"))
        return warnings


def _experience_overview(package, context: _InspectionContext) -> ExperienceOverview:
    data = _json_field(package, "experience_intelligence_json", "experienceIntelligence")
    if not data:
        return ExperienceOverview(
            roles=[],
        )
    plans = {str(_get(item, "experienceId", "experience_id")): item for item in _list(_get(data, "roles"))}
    prompts = {str(_get(item, "experienceId", "experience_id")): item for item in _list(_get(data, "experiencePromptInputs", "experience_prompt_inputs"))}
    roles: list[ExperienceRoleInspection] = []
    bullet_ids: list[str] = []
    for role_data in _list(_get(data, "roleIntelligence", "role_intelligence")):
        experience_id = str(_get(role_data, "experienceId", "experience_id") or "")
        plan = plans.get(experience_id, {})
        prompt = prompts.get(experience_id, {})
        bullets = [_bullet_inspection(item, role_data, plan, prompt, context) for item in _list(_get(role_data, "bullets"))]
        bullet_ids.extend(item.bullet_id for item in bullets)
        role_warnings = [_warning("EXPERIENCE_ROLE_WARNING", item) for item in _string_list(_get(role_data, "warnings"))]
        roles.append(
            ExperienceRoleInspection(
                experienceId=experience_id,
                roleTitle=str(_get(plan, "roleTitle", "role_title") or _get(_get(prompt, "roleContext", "role_context") or {}, "roleTitle", "role_title") or ""),
                roleFamily=str(_get(plan, "roleFamily", "role_family") or _get(data, "roleFamily", "role_family") or ""),
                bulletCount=len(bullets),
                plannerVersion=str(_get(data, "plannerVersion", "planner_version") or ""),
                promptVersion=str(_get(prompt, "promptVersion", "prompt_version") or _get(role_data, "promptVersion", "prompt_version") or ""),
                model=str(_get(role_data, "model") or _get(data, "writerModel", "writer_model") or ""),
                validationStatus=str(_get(role_data, "validationStatus", "validation_status") or ""),
                warnings=_stable_warnings(role_warnings),
                bullets=bullets,
            )
        )
    duplicate_bullets = [item for item, count in Counter(bullet_ids).items() if item and count > 1]
    if duplicate_bullets and roles:
        roles[0].warnings.extend(_warning(INSPECTOR_DUPLICATE_BULLET_ID, f"Duplicate bullet IDs: {', '.join(sorted(duplicate_bullets))}") for _ in [0])
    bullet_count = sum(len(role.bullets) for role in roles)
    return ExperienceOverview(
        roleCount=len(roles),
        bulletCount=bullet_count,
        validBulletCount=sum(1 for role in roles for bullet in role.bullets if bullet.validation_status in {"valid", "validated"}),
        warningBulletCount=sum(1 for role in roles for bullet in role.bullets if bullet.warnings or bullet.validation_status in {"warning", "valid_with_warnings"}),
        fallbackBulletCount=sum(1 for role in roles for bullet in role.bullets if bullet.generation_method == "fallback"),
        roles=roles,
    )


def _bullet_inspection(item: dict, role_data: dict, plan: dict, prompt: dict, context: _InspectionContext) -> ExperienceBulletInspection:
    evidence_ids = _string_list(_get(item, "supportingEvidenceIds", "supporting_evidence_ids"))
    requirement_ids = _string_list(_get(item, "supportedRequirementIds", "supported_requirement_ids"))
    source_technologies = [
        str(_get(tech, "name") or "")
        for tech in _list(_get(plan, "selectedTechnologies", "selected_technologies"))
        if set(_string_list(_get(tech, "evidenceIds", "evidence_ids"))) & set(evidence_ids)
    ]
    source_projects = [
        str(_get(project, "projectName", "project_name") or _get(project, "projectId", "project_id") or "")
        for project in _list(_get(prompt, "linkedProjects", "linked_projects"))
        if set(_string_list(_get(project, "evidenceIds", "evidence_ids"))) & set(evidence_ids)
    ]
    warnings = [_warning("EXPERIENCE_BULLET_WARNING", text) for text in _string_list(_get(item, "warnings"))]
    warnings.extend(context.reference_warnings(evidence_ids, requirement_ids))
    return ExperienceBulletInspection(
        bulletId=str(_get(item, "bulletId", "bullet_id") or ""),
        experienceId=str(_get(role_data, "experienceId", "experience_id") or ""),
        generatedText=_safe_text(_get(item, "generatedText", "generated_text")),
        currentText=_safe_text(_get(item, "currentText", "current_text")),
        userEdited=bool(_get(item, "userEdited", "user_edited") or False),
        supportingEvidenceIds=evidence_ids,
        supportedRequirementIds=requirement_ids,
        validationStatus=str(_get(item, "validationStatus", "validation_status") or ""),
        generationMethod=str(_get(item, "generationMethod", "generation_method") or ""),
        model=str(_get(item, "model") or _get(role_data, "model") or ""),
        promptVersion=str(_get(item, "promptVersion", "prompt_version") or _get(role_data, "promptVersion", "prompt_version") or ""),
        warnings=_stable_warnings(warnings),
        evidenceDetails=context.evidence_details(evidence_ids),
        requirementDetails=context.requirement_details(requirement_ids),
        sourceTechnologies=[item for item in source_technologies if item],
        sourceProjects=[item for item in source_projects if item],
    )


def _skills_overview(package, context: _InspectionContext) -> SkillsOverview:
    data = _json_field(package, "skills_intelligence_json", "skillsIntelligence")
    if not data:
        return SkillsOverview()
    skills: list[SkillInspection] = []
    seen_skill_ids: list[str] = []
    for category in _list(_get(data, "categories")):
        for item in _list(_get(category, "skills")):
            skills.append(_skill_inspection(item, context))
            seen_skill_ids.append(str(_get(item, "skillId", "skill_id") or ""))
    if not skills:
        for item in _list(_get(data, "includedSkills", "included_skills")):
            skills.append(_skill_inspection(item, context))
            seen_skill_ids.append(str(_get(item, "skillId", "skill_id") or ""))
    excluded = [_excluded_skill_inspection(item, context) for item in _list(_get(data, "excludedSkills", "excluded_skills"))]
    duplicates = [item for item, count in Counter(seen_skill_ids).items() if item and count > 1]
    if duplicates and skills:
        skills[0].warnings = _stable_warnings(
            [*skills[0].warnings, _warning(INSPECTOR_DUPLICATE_SKILL_ID, f"Duplicate skill IDs: {', '.join(sorted(duplicates))}")]
        )
    included_requirement_ids = {rid for skill in skills for rid in skill.supported_requirement_ids}
    excluded_requirement_ids = {rid for skill in excluded for rid in skill.requirement_ids}
    conflicts = sorted(included_requirement_ids & excluded_requirement_ids)
    if conflicts and skills:
        skills[0].warnings = _stable_warnings(
            [*skills[0].warnings, _warning(INSPECTOR_INCLUDED_EXCLUDED_CONFLICT, f"Included and excluded skill conflict for requirements: {', '.join(conflicts)}")]
        )
    return SkillsOverview(
        skillCount=len(skills),
        primarySkillCount=sum(1 for item in skills if item.tier == "primary"),
        secondarySkillCount=sum(1 for item in skills if item.tier == "secondary"),
        supportingSkillCount=sum(1 for item in skills if item.tier == "supporting"),
        excludedSkillCount=len(excluded),
        skills=skills,
        excludedSkills=excluded,
    )


def _skill_inspection(item: dict, context: _InspectionContext) -> SkillInspection:
    evidence_ids = _string_list(_get(item, "supportingEvidenceIds", "supporting_evidence_ids"))
    requirement_ids = _string_list(_get(item, "supportedRequirementIds", "supported_requirement_ids"))
    warnings = [_warning("SKILL_WARNING", text) for text in _string_list(_get(item, "warnings"))]
    warnings.extend(context.reference_warnings(evidence_ids, requirement_ids))
    return SkillInspection(
        skillId=str(_get(item, "skillId", "skill_id") or ""),
        canonicalName=str(_get(item, "canonicalName", "canonical_name") or ""),
        displayName=str(_get(item, "displayName", "display_name") or ""),
        category=str(_get(item, "category") or ""),
        tier=str(_get(item, "tier") or ""),
        score=int(_get(item, "score") or 0),
        scoreBreakdown=_dict(_get(item, "scoreBreakdown", "score_breakdown")),
        matchType=str(_get(item, "matchType", "match_type") or ""),
        matchStrength=str(_get(item, "matchStrength", "match_strength") or ""),
        evidenceStrength=str(_get(item, "evidenceStrength", "evidence_strength") or ""),
        recency=str(_get(item, "recency") or ""),
        profileOnly=bool(_get(item, "profileOnly", "profile_only") or False),
        supportingEvidenceIds=evidence_ids,
        supportedRequirementIds=requirement_ids,
        inclusionReason=str(_get(item, "inclusionReason", "inclusion_reason") or ""),
        warnings=_stable_warnings(warnings),
        evidenceDetails=context.evidence_details(evidence_ids),
        requirementDetails=context.requirement_details(requirement_ids),
    )


def _excluded_skill_inspection(item: dict, context: _InspectionContext) -> ExcludedSkillInspection:
    requirement_ids = _string_list(_get(item, "requirementIds", "requirement_ids"))
    return ExcludedSkillInspection(
        originalRequirementValue=str(_get(item, "originalRequirementValue", "original_requirement_value") or ""),
        canonicalName=str(_get(item, "canonicalName", "canonical_name") or ""),
        requirementIds=requirement_ids,
        exclusionCode=str(_get(item, "exclusionCode", "exclusion_code") or ""),
        reason=str(_get(item, "reason") or ""),
        requirementDetails=context.requirement_details(requirement_ids),
    )


def _requirement_coverage(
    package,
    summary: SummaryInspection,
    experience: ExperienceOverview,
    skills: SkillsOverview,
    context: _InspectionContext,
) -> list[RequirementCoverageInspection]:
    by_requirement: dict[str, dict[str, Any]] = {
        requirement_id: {
            "summary": False,
            "bullets": [],
            "skills": [],
            "exclusion": "",
        }
        for requirement_id in context.requirements
    }
    for requirement_id in summary.supported_requirement_ids:
        by_requirement.setdefault(requirement_id, {"summary": False, "bullets": [], "skills": [], "exclusion": ""})["summary"] = True
    for role in experience.roles:
        for bullet in role.bullets:
            for requirement_id in bullet.supported_requirement_ids:
                by_requirement.setdefault(requirement_id, {"summary": False, "bullets": [], "skills": [], "exclusion": ""})["bullets"].append(bullet.bullet_id)
    for skill in skills.skills:
        for requirement_id in skill.supported_requirement_ids:
            by_requirement.setdefault(requirement_id, {"summary": False, "bullets": [], "skills": [], "exclusion": ""})["skills"].append(skill.skill_id)
    for excluded in skills.excluded_skills:
        for requirement_id in excluded.requirement_ids:
            by_requirement.setdefault(requirement_id, {"summary": False, "bullets": [], "skills": [], "exclusion": ""})["exclusion"] = excluded.reason
    output: list[RequirementCoverageInspection] = []
    for requirement_id in sorted(by_requirement):
        detail = context.requirements.get(requirement_id) or RequirementInspection(requirementId=requirement_id)
        row = by_requirement[requirement_id]
        bullet_ids = _dedupe(row["bullets"])
        skill_ids = _dedupe(row["skills"])
        sources = []
        if row["summary"]:
            sources.append("summary")
        if bullet_ids:
            sources.append("experience")
        if skill_ids:
            sources.append("skills")
        if row["exclusion"]:
            sources.append("excluded")
        covered = bool(row["summary"] or bullet_ids or skill_ids)
        output.append(
            RequirementCoverageInspection(
                requirementId=requirement_id,
                requirementText=detail.original_text,
                normalizedValue=detail.normalized_value,
                type=detail.requirement_type,
                priority=detail.priority,
                covered=covered,
                coverageSources=sources,
                summarySupport=bool(row["summary"]),
                experienceBulletIds=bullet_ids,
                skillIds=skill_ids,
                exclusionReason=row["exclusion"],
                warnings=detail.warnings,
            )
        )
    return output


def _requirement_map(package) -> dict[str, RequirementInspection]:
    output: dict[str, RequirementInspection] = {}
    normalized = _json_field(package, "normalized_requirements_json", "normalizedRequirements")
    for group_name, values in sorted(_dict(normalized).items()):
        if not isinstance(values, list):
            continue
        for item in values:
            requirement_id = str(_get(item, "requirementId", "requirement_id") or "")
            if not requirement_id:
                continue
            original_terms = _string_list(_get(item, "originalTerms", "original_terms"))
            text = str(_get(item, "canonicalTerm", "canonical_term") or "")
            output[requirement_id] = RequirementInspection(
                requirementId=requirement_id,
                originalText=_safe_text(original_terms[0] if original_terms else text),
                normalizedValue=_safe_text(text),
                requirementType=str(_get(item, "category") or group_name),
                priority=str(_get(item, "priority") or ""),
                explicit=bool(_get(item, "explicit")),
                placementStrategy={},
                supported=False,
                supportSources=[],
            )
    job_intelligence = _json_field(package, "job_intelligence_json", "jobIntelligence")
    for item in _list(_get(job_intelligence, "keywords")):
        requirement_id = str(_get(item, "id") or "")
        if requirement_id and requirement_id not in output:
            output[requirement_id] = RequirementInspection(
                requirementId=requirement_id,
                originalText=_safe_text(_get(item, "value", "term")),
                normalizedValue=_safe_text(_get(item, "normalizedValue", "normalized_value") or _get(item, "value", "term")),
                requirementType=str(_get(item, "category") or ""),
                priority=str(_get(item, "priority") or ""),
                explicit=bool(_get(item, "directFromJD", "direct_from_jd") or _get(item, "explicit")),
            )
    return output


def _evidence_map(package) -> dict[str, EvidenceInspection]:
    output: dict[str, EvidenceInspection] = {}
    match = _json_field(package, "profile_match_json", "profileMatch")
    for requirement in [
        *_list(_get(match, "matchedRequirements", "matched_requirements")),
        *_list(_get(match, "partiallyMatchedRequirements", "partially_matched_requirements")),
        *_list(_get(match, "unmatchedRequirements", "unmatched_requirements")),
    ]:
        for evidence in [*_list(_get(requirement, "evidence")), *_list(_get(requirement, "adjacentEvidence", "adjacent_evidence"))]:
            detail = _evidence_from_profile_match(evidence)
            if detail.evidence_id:
                output[detail.evidence_id] = detail
    experience = _json_field(package, "experience_intelligence_json", "experienceIntelligence")
    for prompt in _list(_get(experience, "experiencePromptInputs", "experience_prompt_inputs")):
        for evidence in _list(_get(prompt, "approvedEvidence", "approved_evidence")):
            evidence_id = str(_get(evidence, "evidenceId", "evidence_id") or "")
            if evidence_id and evidence_id not in output:
                output[evidence_id] = EvidenceInspection(
                    evidenceId=evidence_id,
                    sourceType=str(_get(evidence, "evidenceType", "evidence_type") or ""),
                    sourceId=str(_get(evidence, "sourceRecordId", "source_record_id") or ""),
                    experienceId=str(_get(prompt, "experienceId", "experience_id") or ""),
                    projectId=str(_get(evidence, "projectId", "project_id") or ""),
                    sourceLabel=str(_get(_get(prompt, "roleContext", "role_context") or {}, "roleTitle", "role_title") or ""),
                    evidenceText=_safe_evidence_text(evidence_id, str(_get(evidence, "sourceRecordId", "source_record_id") or ""), _get(evidence, "text")),
                    warnings=_metadata_warnings(evidence_id, str(_get(evidence, "sourceRecordId", "source_record_id") or "")),
                )
        for project in _list(_get(prompt, "linkedProjects", "linked_projects")):
            for evidence_id in _string_list(_get(project, "evidenceIds", "evidence_ids")):
                if evidence_id and evidence_id not in output:
                    output[evidence_id] = EvidenceInspection(
                        evidenceId=evidence_id,
                        sourceType="project",
                        sourceId=str(_get(project, "projectId", "project_id") or ""),
                        experienceId=str(_get(prompt, "experienceId", "experience_id") or ""),
                        projectId=str(_get(project, "projectId", "project_id") or ""),
                        sourceLabel=str(_get(project, "projectName", "project_name") or ""),
                        evidenceText=_safe_text(" ".join(_string_list(_get(project, "approvedFacts", "approved_facts")))),
                    )
    return output


def _evidence_from_profile_match(evidence: dict) -> EvidenceInspection:
    evidence_type = str(_get(evidence, "evidenceType", "evidence_type") or "")
    evidence_id = str(_get(evidence, "evidenceId", "evidence_id") or "")
    source_id = str(_get(evidence, "sourceRecordId", "source_record_id") or "")
    return EvidenceInspection(
        evidenceId=evidence_id,
        sourceType=evidence_type,
        sourceId=source_id,
        experienceId=_experience_id_from_source(source_id),
        projectId=str(_get(evidence, "projectId", "project_id") or ""),
        sourceLabel=_safe_text(_get(evidence, "sourceLabel", "source_label")),
        evidenceText=_safe_evidence_text(evidence_id, source_id, _get(evidence, "originalText", "original_text")),
        strength=str(_get(evidence, "strengthScore", "strength_score") or ""),
        linkedExperienceIds=_string_list(_get(evidence, "linkedExperienceIds", "linked_experience_ids")),
        warnings=_metadata_warnings(evidence_id, source_id),
    )


def _versions(package) -> VersionInspection:
    summary = _json_field(package, "summary_intelligence_json", "summaryIntelligence")
    experience = _json_field(package, "experience_intelligence_json", "experienceIntelligence")
    skills = _json_field(package, "skills_intelligence_json", "skillsIntelligence")
    prompt_inputs = _list(_get(experience, "experiencePromptInputs", "experience_prompt_inputs"))
    first_prompt = prompt_inputs[0] if prompt_inputs else {}
    policy = SkillsRenderingPolicy()
    return VersionInspection(
        jobAnalysisVersion=str(_get(_json_field(package, "job_intelligence_json", "jobIntelligence"), "analysisVersion", "analysis_version") or ""),
        profileMatchVersion=str(_get(_json_field(package, "profile_match_json", "profileMatch"), "matchingAlgorithmVersion", "matching_algorithm_version") or ""),
        summaryPlannerVersion=str(_get(summary, "plannerVersion", "planner_version") or ""),
        summaryPromptVersion=str(_get(summary, "promptVersion", "prompt_version") or ""),
        experiencePlannerVersion=str(_get(experience, "plannerVersion", "planner_version") or ""),
        experiencePromptVersion=str(_get(first_prompt, "promptVersion", "prompt_version") or ""),
        experienceWriterPromptVersion=str(_get(experience, "writerPromptVersion", "writer_prompt_version") or ""),
        experienceModel=str(_get(experience, "writerModel", "writer_model") or ""),
        experienceModelConfigurationHash=str(_get(experience, "modelConfigurationHash", "model_configuration_hash") or ""),
        skillRegistryVersion=str(_get(skills, "skillRegistryVersion", "skill_registry_version") or ""),
        skillEvidenceIndexVersion=str(_get(skills, "skillEvidenceIndexVersion", "skill_evidence_index_version") or ""),
        skillsPlannerVersion=str(_get(skills, "plannerVersion", "planner_version") or ""),
        skillsRenderingPolicyVersion=policy.policy_version,
        summaryModelConfigurationHash=str(_get(summary, "modelConfigurationHash", "model_configuration_hash") or ""),
    )


def _metrics(
    summary: SummaryInspection,
    experience: ExperienceOverview,
    skills: SkillsOverview,
    coverage: list[RequirementCoverageInspection],
    warnings: list[InspectorWarning],
) -> InspectionMetrics:
    requirement_count = len(coverage)
    covered = sum(1 for item in coverage if item.covered)
    return InspectionMetrics(
        requirementCount=requirement_count,
        coveredRequirementCount=covered,
        coveragePercent=round(covered * 100 / requirement_count) if requirement_count else 0,
        summaryEvidenceCount=len(summary.supporting_evidence_ids),
        roleCount=experience.role_count,
        bulletCount=experience.bullet_count,
        fallbackBulletCount=experience.fallback_bullet_count,
        skillCount=skills.skill_count,
        primarySkillCount=skills.primary_skill_count,
        secondarySkillCount=skills.secondary_skill_count,
        supportingSkillCount=skills.supporting_skill_count,
        excludedSkillCount=skills.excluded_skill_count,
        warningCount=len(warnings),
    )


def _stale_reasons(package, profile_record=None) -> list[str]:
    reasons = _string_list(_field(package, "validation_warnings", "validationWarnings"))
    if profile_record is not None:
        if str(_field(package, "profile_id", "profileId") or "") != str(_field(profile_record, "profile_id", "profileId") or ""):
            reasons.append(
                f"profileId changed: stored={_field(package, 'profile_id', 'profileId')} current={_field(profile_record, 'profile_id', 'profileId')}"
            )
        if int(_field(package, "profile_version", "profileVersion") or 0) != int(_field(profile_record, "profile_version", "profileVersion") or 0):
            reasons.append(
                f"profileVersion changed: stored={_field(package, 'profile_version', 'profileVersion')} current={_field(profile_record, 'profile_version', 'profileVersion')}"
            )
        if str(_field(package, "profile_content_hash", "profileHash") or "") != str(_field(profile_record, "content_hash", "contentHash") or ""):
            reasons.append("profile hash changed")
    experience = _json_field(package, "experience_intelligence_json", "experienceIntelligence")
    skills = _json_field(package, "skills_intelligence_json", "skillsIntelligence")
    summary = _json_field(package, "summary_intelligence_json", "summaryIntelligence")
    if summary:
        reasons.extend(_summary_stale_reasons(summary, package, profile_record))
    else:
        reasons.append("summary intelligence missing")
    if experience:
        reasons.extend(experience_intelligence_stale_reasons(experience))
    else:
        reasons.append("experience intelligence missing")
    reasons.extend(skills_intelligence_stale_reasons(skills))
    if _field(package, "validation_status", "validationStatus") == "stale":
        return sorted(_dedupe(reasons), key=str.casefold)
    return sorted([reason for reason in _dedupe(reasons) if "changed" in reason.casefold() or "missing" in reason.casefold()], key=str.casefold)


def _summary_stale_reasons(summary: dict, package, profile_record=None) -> list[str]:
    reasons: list[str] = []
    if profile_record is not None:
        if str(_get(summary, "profileId", "profile_id") or "") != str(_field(profile_record, "profile_id", "profileId") or ""):
            reasons.append("summary profileId changed")
        if int(_get(summary, "profileVersion", "profile_version") or 0) != int(_field(profile_record, "profile_version", "profileVersion") or 0):
            reasons.append("summary profileVersion changed")
        if str(_get(summary, "profileHash", "profile_hash") or "") != str(_field(profile_record, "content_hash", "contentHash") or ""):
            reasons.append("summary profile hash changed")
    if str(_get(summary, "jobDescriptionHash", "job_description_hash") or "") != str(_field(package, "job_description_hash", "jobDescriptionHash") or ""):
        reasons.append("summary job description changed")
    if normalized(str(_get(summary, "targetRole", "target_role") or "")) != normalized(str(_field(package, "target_role", "targetRole") or "")):
        reasons.append("summary target role changed")
    if normalized(str(_get(summary, "targetCompany", "target_company") or "")) != normalized(str(_field(package, "target_company", "targetCompany") or "")):
        reasons.append("summary target company changed")
    if normalized(str(_get(summary, "level") or "")) != normalized(str(_field(package, "level", "targetLevel") or "Senior")):
        reasons.append("summary experience level changed")
    if str(_get(summary, "promptVersion", "prompt_version") or "") != SUMMARY_PROMPT_VERSION:
        reasons.append("summary prompt version changed")
    if str(_get(summary, "modelConfigurationHash", "model_configuration_hash") or "") != summary_model_configuration_hash(str(_get(summary, "model") or "") or None):
        reasons.append("summary model configuration changed")
    return reasons


def _is_stale(package, stale_reasons: list[str] | None = None) -> bool:
    return _field(package, "validation_status", "validationStatus") == "stale" or bool(stale_reasons or [])


def experience_warnings(experience: ExperienceOverview) -> list[InspectorWarning]:
    return [warning for role in experience.roles for warning in role.warnings] + [warning for role in experience.roles for bullet in role.bullets for warning in bullet.warnings]


def skill_warnings(skills: SkillsOverview) -> list[InspectorWarning]:
    return [warning for skill in skills.skills for warning in skill.warnings]


def _coverage_warnings(coverage: list[RequirementCoverageInspection]) -> list[InspectorWarning]:
    return [warning for item in coverage for warning in item.warnings]


def _json_field(package, *names: str) -> dict:
    value = _field(package, *names)
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    return value if isinstance(value, dict) else {}


def _field(obj, *names: str):
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _get(obj: Any, *names: str):
    return _field(obj, *names)


def _dict(value: Any) -> dict:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in _list(value) if str(item or "").strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _warning(code: str, message: str = "") -> InspectorWarning:
    return InspectorWarning(code=code, message=message or code)


def _stale_warning(reason: str) -> InspectorWarning:
    key = reason.casefold()
    if "summary intelligence missing" in key:
        return _warning(INSPECTOR_SUMMARY_INTELLIGENCE_MISSING, reason)
    if "experience intelligence missing" in key:
        return _warning(INSPECTOR_EXPERIENCE_INTELLIGENCE_MISSING, reason)
    if "skills intelligence missing" in key:
        return _warning(INSPECTOR_SKILLS_INTELLIGENCE_MISSING, reason)
    if "version" in key or "configuration" in key:
        return _warning(INSPECTOR_VERSION_METADATA_MISSING, reason)
    return _warning(reason, reason)


def _stable_warnings(warnings: list[InspectorWarning]) -> list[InspectorWarning]:
    keyed = {(item.code, item.message): item for item in warnings}
    return [keyed[key] for key in sorted(keyed)]


def _safe_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[redacted-email]", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)", "[redacted-phone]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[redacted-api-key]", text)
    text = re.sub(r"\b\d{1,6}\s+[A-Za-z0-9 .'-]+(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Drive|Dr|Court|Ct|Boulevard|Blvd)\b", "[redacted-address]", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def _safe_evidence_text(evidence_id: str, source_id: str, value: Any) -> str:
    if _metadata_markers(evidence_id, source_id):
        return "[metadata-redacted]"
    return _safe_text(value)


def _metadata_warnings(evidence_id: str, source_id: str) -> list[InspectorWarning]:
    if _metadata_markers(evidence_id, source_id):
        return [_warning(INSPECTOR_METADATA_LEAKAGE, f"Metadata evidence was redacted: {evidence_id or source_id}")]
    return []


def _metadata_markers(*values: str) -> bool:
    markers = ("-company-", "-client-", "-location-")
    text = " ".join(values).casefold()
    return any(marker in text for marker in markers)


def _experience_id_from_source(source_id: str) -> str:
    if source_id.startswith("experience-"):
        return source_id.removeprefix("experience-")
    return ""


def _to_iso(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
