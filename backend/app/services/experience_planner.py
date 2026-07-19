from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from app.schemas.resume import (
    CandidateProfile,
    ExperienceCapabilitySelection,
    ExperienceEvidenceSelection,
    ExperienceIntelligencePlan,
    ExperienceRolePlan,
    ExperienceTechnologySelection,
    ProfileEvidenceItem,
    ProfileEvidenceType,
    ProfileMatchSummary,
    ResumeGenerationSettings,
    ResumeExperience,
    TypedJobRequirement,
)


EXPERIENCE_PLANNER_VERSION = "experience-planner-v1"

METADATA_EVIDENCE_MARKERS = ("-company-", "-client-", "-location-", "-raw-notes-", "-legacy-notes-")
GENERIC_CAPABILITIES = {"requirements analysis", "agile", "scrum", "documentation", "communication", "collaboration"}
INVALID_PROJECT_EXPERIENCE_LINK = "INVALID_PROJECT_EXPERIENCE_LINK"
PROJECT_LINK_TARGET_NOT_FOUND = "PROJECT_LINK_TARGET_NOT_FOUND"
PROJECT_EVIDENCE_WRONG_ROLE = "PROJECT_EVIDENCE_WRONG_ROLE"
DUPLICATE_PROJECT_EXPERIENCE_LINK = "DUPLICATE_PROJECT_EXPERIENCE_LINK"
UNMAPPED_PROJECT_EXCLUDED = "UNMAPPED_PROJECT_EXCLUDED"


def build_experience_intelligence(
    profile: CandidateProfile,
    job_description: str,
    typed_requirements: Any,
    profile_match: ProfileMatchSummary,
    evidence_index: list[ProfileEvidenceItem],
    generation_settings: ResumeGenerationSettings,
) -> ExperienceIntelligencePlan:
    role_family = classify_role_family(job_description, getattr(profile_match, "strengths", []))
    requirement_by_id = requirement_lookup(typed_requirements)
    matched_requirement_by_evidence = evidence_to_requirements(profile_match)
    evidence_by_record = role_specific_evidence(evidence_index)
    jd_terms = requirement_terms(profile_match)
    warnings: list[str] = project_mapping_warnings(evidence_index, profile)
    role_plans: list[ExperienceRolePlan] = []
    selected_theme_counts: Counter[str] = Counter()

    for index, role in enumerate(profile.experience):
        source_record_id = role_source_record_id(role)
        role_items = evidence_by_record.get(source_record_id, [])
        recent = index == 0 or role.is_current_role
        desired_count = generation_settings.bullets_per_recent_role if recent else generation_settings.bullets_per_older_role
        scored = rank_role_evidence(
            role,
            role_items,
            job_description,
            matched_requirement_by_evidence,
            requirement_by_id,
            role_family,
            recency_score=recency_for(index, role),
            selected_theme_counts=selected_theme_counts,
        )
        selected = [item for item in scored if item["score"] > 0][: max(desired_count * 2, desired_count)]
        bullet_count = min(desired_count, len(selected))
        for item in selected[:bullet_count]:
            selected_theme_counts.update(themes_for_text(item["evidence"].original_text, role_family))

        role_warnings = validate_role_plan_inputs(role, role_items, selected, matched_requirement_by_evidence)
        if bullet_count < desired_count:
            role_warnings.append("insufficient role evidence for requested bullet count")
        warnings.extend(f"{role.experience_id or role.role}: {warning}" for warning in role_warnings)
        selected_requirement_ids = sorted({rid for item in selected for rid in matched_requirement_by_evidence.get(item["evidence"].evidence_id, [])})
        selected_technologies = select_role_technologies(role, role_items, job_description)
        selected_capabilities = select_role_capabilities(
            selected,
            matched_requirement_by_evidence,
            requirement_by_id,
            role_family,
        )
        bullet_themes = select_bullet_themes(selected, role_family)
        if generic_capabilities_dominate(bullet_themes):
            role_warnings.append("generic capabilities dominate selected themes")

        role_plans.append(
            ExperienceRolePlan(
                experienceId=role.experience_id,
                roleTitle=role.role,
                company=role.company,
                roleFamily=role_family,
                bulletCount=bullet_count,
                selectedEvidence=[selection_from_scored(item) for item in selected],
                selectedTechnologies=selected_technologies,
                selectedCapabilities=selected_capabilities,
                supportedRequirementIds=selected_requirement_ids,
                bulletThemes=bullet_themes,
                excludedJdTerms=[term for term in jd_terms if term and term_id(term, requirement_by_id) not in selected_requirement_ids][:12],
                warnings=dedupe(role_warnings),
            )
        )

    warnings.extend(validate_plan(role_plans, evidence_index, profile_match))
    return ExperienceIntelligencePlan(
        plannerVersion=EXPERIENCE_PLANNER_VERSION,
        roleFamily=role_family,
        roles=role_plans,
        warnings=dedupe(warnings),
        validationStatus="valid" if not warnings else "warning",
    )


def role_source_record_id(role: ResumeExperience) -> str:
    return f"experience-{role.experience_id}" if role.experience_id else ""


def role_specific_evidence(evidence_index: list[ProfileEvidenceItem]) -> dict[str, list[ProfileEvidenceItem]]:
    grouped: dict[str, list[ProfileEvidenceItem]] = defaultdict(list)
    for evidence in evidence_index:
        record_id = evidence.source_record_id or ""
        if not record_id.startswith("experience-"):
            if evidence.evidence_type == ProfileEvidenceType.project:
                for experience_id in evidence.linked_experience_ids:
                    grouped[f"experience-{experience_id}"].append(evidence)
            continue
        grouped[record_id].append(evidence)
    return grouped


def project_mapping_warnings(evidence_index: list[ProfileEvidenceItem], profile: CandidateProfile) -> list[str]:
    warnings: list[str] = []
    valid_experience_ids = {item.experience_id for item in profile.experience if item.experience_id}
    for evidence in evidence_index:
        if evidence.evidence_type != ProfileEvidenceType.project:
            continue
        if not evidence.linked_experience_ids:
            warnings.append(f"{UNMAPPED_PROJECT_EXCLUDED}: {evidence.project_id or evidence.source_record_id}")
            continue
        if len(evidence.linked_experience_ids) != len(set(evidence.linked_experience_ids)):
            warnings.append(f"{DUPLICATE_PROJECT_EXPERIENCE_LINK}: {evidence.project_id or evidence.source_record_id}")
        missing = [experience_id for experience_id in evidence.linked_experience_ids if experience_id not in valid_experience_ids]
        if missing:
            warnings.append(f"{PROJECT_LINK_TARGET_NOT_FOUND}: {evidence.project_id or evidence.source_record_id} -> {', '.join(missing)}")
    return warnings


def evidence_to_requirements(profile_match: ProfileMatchSummary) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = defaultdict(list)
    for match in profile_match.matched_requirements:
        if not match.is_safe_to_use:
            continue
        for evidence in match.evidence:
            mapping[evidence.evidence_id].append(match.requirement_id)
    return {key: dedupe(values) for key, values in mapping.items()}


def requirement_lookup(typed_requirements: Any) -> dict[str, TypedJobRequirement]:
    groups = []
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
        groups.extend(getattr(typed_requirements, attr, []) or [])
    return {item.requirement_id: item for item in groups}


def requirement_terms(profile_match: ProfileMatchSummary) -> list[str]:
    return dedupe(
        [
            match.requirement_value
            for match in [
                *profile_match.matched_requirements,
                *profile_match.partially_matched_requirements,
                *profile_match.unmatched_requirements,
            ]
            if match.requirement_value.strip()
        ]
    )


def term_id(term: str, requirement_by_id: dict[str, TypedJobRequirement]) -> str:
    normalized = normalize(term)
    for requirement_id, requirement in requirement_by_id.items():
        if normalize(requirement.canonical_term) == normalized:
            return requirement_id
    return ""


def rank_role_evidence(
    role: ResumeExperience,
    role_items: list[ProfileEvidenceItem],
    job_description: str,
    matched_requirement_by_evidence: dict[str, list[str]],
    requirement_by_id: dict[str, TypedJobRequirement],
    role_family: str,
    *,
    recency_score: float,
    selected_theme_counts: Counter[str],
) -> list[dict[str, Any]]:
    scored = []
    for evidence in role_items:
        kind = planner_evidence_type(evidence)
        if not kind:
            continue
        relevance = jd_relevance_score(evidence, job_description, matched_requirement_by_evidence, requirement_by_id)
        evidence_match_themes = themes_for_text(evidence.original_text, "")
        jd_match_themes = themes_for_text(job_description, "")
        if set(evidence_match_themes) & set(jd_match_themes):
            relevance = max(relevance, 45.0)
        if relevance < 20.0 and not matched_requirement_by_evidence.get(evidence.evidence_id):
            continue
        strength = float(evidence.strength_score)
        role_specificity = 100.0 if evidence.source_record_id == role_source_record_id(role) else 0.0
        achievement_value = 100.0 if kind in {"achievement", "metric"} else 80.0 if kind == "existing_bullet" else 65.0
        themes = themes_for_text(evidence.original_text, role_family)
        duplication_penalty = min(30.0, sum(selected_theme_counts[theme] * 8.0 for theme in themes))
        score = (relevance * 0.4) + (strength * 0.3) + (role_specificity * 0.15) + (recency_score * 0.1) + (achievement_value * 0.05) - duplication_penalty
        if has_metadata_leak(evidence):
            score -= 100
        scored.append(
            {
                "evidence": evidence,
                "kind": kind,
                "score": max(0.0, round(score, 2)),
                "relevance": round(relevance, 2),
                "recency": round(recency_score, 2),
                "strength": round(strength, 2),
                "reason": selection_reason(kind, relevance, evidence, matched_requirement_by_evidence),
            }
        )
    return sorted(scored, key=lambda item: (item["score"], item["strength"]), reverse=True)


def planner_evidence_type(evidence: ProfileEvidenceItem) -> str:
    evidence_id = evidence.evidence_id
    if has_metadata_leak(evidence):
        return ""
    if "-responsibility-" in evidence_id:
        return "responsibility"
    if "-metric-" in evidence_id or "-achievement-" in evidence_id:
        return "metric" if "-metric-" in evidence_id else "achievement"
    if "-technology-" in evidence_id and evidence.evidence_type == ProfileEvidenceType.skill:
        return "technology"
    if evidence.evidence_type == ProfileEvidenceType.project:
        if "-technology-" in evidence_id:
            return "project_technology"
        if "-bullet-" in evidence_id:
            return "project"
    if "-statement-" in evidence_id:
        return "existing_bullet"
    return ""


def has_metadata_leak(evidence: ProfileEvidenceItem) -> bool:
    evidence_id = evidence.evidence_id
    return any(marker in evidence_id for marker in METADATA_EVIDENCE_MARKERS)


def jd_relevance_score(
    evidence: ProfileEvidenceItem,
    job_description: str,
    matched_requirement_by_evidence: dict[str, list[str]],
    requirement_by_id: dict[str, TypedJobRequirement],
) -> float:
    requirement_ids = matched_requirement_by_evidence.get(evidence.evidence_id, [])
    if requirement_ids:
        priority_scores = []
        for requirement_id in requirement_ids:
            requirement = requirement_by_id.get(requirement_id)
            priority_scores.append(priority_score(requirement.priority if requirement else "medium"))
        return max(priority_scores or [80.0])
    overlap = token_overlap(evidence.original_text, job_description)
    return min(70.0, overlap * 100)


def priority_score(priority: Any) -> float:
    value = str(getattr(priority, "value", priority)).casefold()
    return {"critical": 100.0, "high": 90.0, "medium": 70.0, "low": 45.0}.get(value, 65.0)


def recency_for(index: int, role: ResumeExperience) -> float:
    if role.is_current_role or str(role.end_date).casefold() == "present":
        return 100.0
    return max(35.0, 85.0 - (index * 15.0))


def selection_reason(kind: str, relevance: float, evidence: ProfileEvidenceItem, matched_requirement_by_evidence: dict[str, list[str]]) -> str:
    if matched_requirement_by_evidence.get(evidence.evidence_id):
        return f"Selected {kind} because it directly supports matched job requirements."
    if relevance > 40:
        return f"Selected {kind} because its wording overlaps with the target job description."
    return f"Selected {kind} as role-specific verified evidence."


def selection_from_scored(item: dict[str, Any]) -> ExperienceEvidenceSelection:
    evidence = item["evidence"]
    return ExperienceEvidenceSelection(
        evidenceId=evidence.evidence_id,
        evidenceType=item["kind"],
        text=evidence.original_text,
        sourceRecordId=evidence.source_record_id or "",
        projectId=evidence.project_id or "",
        linkedExperienceIds=evidence.linked_experience_ids,
        relevanceScore=item["relevance"],
        recencyScore=item["recency"],
        strengthScore=item["strength"],
        selectionReason=item["reason"],
    )


def select_role_technologies(
    role: ResumeExperience,
    role_items: list[ProfileEvidenceItem],
    job_description: str,
) -> list[ExperienceTechnologySelection]:
    output: list[ExperienceTechnologySelection] = []
    for evidence in role_items:
        evidence_kind = planner_evidence_type(evidence)
        if evidence_kind not in {"technology", "project_technology"}:
            continue
        name = evidence.original_text.strip()
        if not name:
            continue
        in_jd = contains_phrase(job_description, name)
        support = "project" if evidence_kind == "project_technology" else "verified" if evidence.source_record_id == role_source_record_id(role) else "partial"
        if in_jd or technology_is_role_core(name, role):
            output.append(
                ExperienceTechnologySelection(
                    name=name,
                    evidenceIds=[evidence.evidence_id],
                    supportLevel=support,
                    selectionReason="Technology is explicitly attached to this work experience or an explicitly linked project.",
                )
            )
    return dedupe_technologies(output)


def technology_is_role_core(name: str, role: ResumeExperience) -> bool:
    return contains_phrase(role.role, name)


def select_role_capabilities(
    selected: list[dict[str, Any]],
    matched_requirement_by_evidence: dict[str, list[str]],
    requirement_by_id: dict[str, TypedJobRequirement],
    role_family: str,
) -> list[ExperienceCapabilitySelection]:
    by_capability: dict[str, ExperienceCapabilitySelection] = {}
    for item in selected:
        evidence = item["evidence"]
        requirement_ids = matched_requirement_by_evidence.get(evidence.evidence_id, [])
        names = [requirement_by_id[req_id].canonical_term for req_id in requirement_ids if req_id in requirement_by_id]
        if not names:
            names = themes_for_text(evidence.original_text, role_family)[:2]
        for name in names:
            if not name or normalize(name) in {"company", "client", "location"}:
                continue
            current = by_capability.get(name)
            if current:
                current.evidence_ids = dedupe([*current.evidence_ids, evidence.evidence_id])
                current.supported_requirement_ids = dedupe([*current.supported_requirement_ids, *requirement_ids])
            else:
                by_capability[name] = ExperienceCapabilitySelection(
                    name=name,
                    evidenceIds=[evidence.evidence_id],
                    supportedRequirementIds=requirement_ids,
                    selectionReason="Capability is supported by role-specific evidence selected for this job.",
                )
    return list(by_capability.values())[:8]


def select_bullet_themes(selected: list[dict[str, Any]], role_family: str) -> list[str]:
    themes: list[str] = []
    for item in selected:
        themes.extend(themes_for_text(item["evidence"].original_text, role_family))
    return dedupe(themes)[:8]


def themes_for_text(text: str, role_family: str) -> list[str]:
    value = normalize(text)
    rules = [
        ("API development", ("api", "rest", "web api", "service")),
        ("SQL/database development", ("sql", "database", "stored procedure", "query")),
        ("secure application development", ("security", "secure", "authentication", "authorization", "compliance")),
        ("testing and quality", ("test", "qa", "defect", "validation", "regression")),
        ("release and deployment", ("release", "deploy", "pipeline", "ci/cd", "jenkins")),
        ("application modernization", ("refactor", "modernization", "upgrade", "migration")),
        ("production reliability", ("production", "support", "incident", "troubleshoot", "root cause", "debug")),
        ("technical documentation", ("documentation", "documented", "technical notes", "handoff", "specification")),
        ("code review and standards", ("code review", "reviewed", "standards", "best practices")),
        ("stakeholder collaboration", ("stakeholder", "product owner", "business analyst", "qa", "architect")),
        ("data engineering", ("etl", "databricks", "spark", "pipeline", "data flow")),
        ("AI engineering", ("rag", "langchain", "fastapi", "llm", "generative ai")),
        ("cloud engineering", ("azure", "aws", "cloud", "docker", "kubernetes")),
        ("frontend development", ("react", "angular", "next.js", "html", "css", "ui")),
        ("backend .NET development", ("c#", ".net", "asp.net", "mvc", "entity framework")),
        ("Java backend development", ("java", "spring", "spring boot")),
    ]
    themes = [label for label, terms in rules if any(term in value for term in terms)]
    if not themes and role_family:
        themes.append(role_family)
    return themes


def classify_role_family(job_description: str, strengths: list[str] | None = None) -> str:
    text = normalize(" ".join([job_description, " ".join(strengths or [])]))
    if any(term in text for term in ("rag", "llm", "generative ai", "langchain", "ai engineer")):
        return "AI / Generative AI Engineering"
    if any(term in text for term in ("databricks", "spark", "etl", "data engineer", "data pipeline")):
        return "Data Engineering"
    if any(term in text for term in ("production support", "maintain production", "application support", "defect", "troubleshoot")):
        return "Production Support / Application Maintenance"
    if any(term in text for term in ("refactor", "modernization", "upgrade")):
        return "Application Modernization"
    if any(term in text for term in ("full stack", "front-end", "frontend", "back-end", "backend")) and any(term in text for term in (".net", "c#", "asp.net")):
        return "Full Stack .NET Development"
    if any(term in text for term in (".net", "c#", "asp.net")):
        return "Backend .NET Development"
    if any(term in text for term in ("java", "spring boot", "spring")):
        return "Java Backend Development"
    if any(term in text for term in ("azure", "aws", "devops", "cloud", "ci/cd", "docker", "kubernetes")):
        return "Cloud / DevOps"
    if any(term in text for term in ("sql server", "stored procedure", "database development", "t-sql")):
        return "Database Development"
    return "Enterprise Application Development"


def validate_role_plan_inputs(
    role: ResumeExperience,
    role_items: list[ProfileEvidenceItem],
    selected: list[dict[str, Any]],
    matched_requirement_by_evidence: dict[str, list[str]],
) -> list[str]:
    warnings = []
    selected_ids = [item["evidence"].evidence_id for item in selected]
    if len(selected_ids) != len(set(selected_ids)):
        warnings.append("duplicate evidence selected")
    if not role_items:
        warnings.append("no role-specific evidence found")
    for item in selected:
        evidence = item["evidence"]
        if has_metadata_leak(evidence):
            warnings.append("metadata leakage detected")
        if evidence.source_record_id != role_source_record_id(role):
            if evidence.evidence_type == ProfileEvidenceType.project and role.experience_id in evidence.linked_experience_ids:
                continue
            warnings.append("experience-level evidence mapped to the wrong role")
        if planner_evidence_type(evidence) in {"technology", "project_technology"} and not matched_requirement_by_evidence.get(evidence.evidence_id):
            warnings.append("technology selected without matched requirement support")
    return warnings


def validate_plan(role_plans: list[ExperienceRolePlan], evidence_index: list[ProfileEvidenceItem], profile_match: ProfileMatchSummary) -> list[str]:
    warnings = []
    valid_evidence_ids = {item.evidence_id for item in evidence_index}
    safe_requirement_ids = {match.requirement_id for match in profile_match.matched_requirements if match.is_safe_to_use}
    valid_role_ids = {role.experience_id for role in role_plans if role.experience_id}
    all_theme_sets = []
    for role in role_plans:
        all_theme_sets.append(tuple(role.bullet_themes))
        for item in role.selected_evidence:
            if item.evidence_id not in valid_evidence_ids:
                warnings.append("invalid evidence ID")
            if has_metadata_text(item.text):
                warnings.append("metadata leakage detected")
            if item.source_record_id.startswith("project-") and role.experience_id not in item.linked_experience_ids:
                warnings.append(f"{PROJECT_EVIDENCE_WRONG_ROLE}: {item.project_id or item.source_record_id}")
            for experience_id in item.linked_experience_ids:
                if experience_id not in valid_role_ids:
                    warnings.append(f"{PROJECT_LINK_TARGET_NOT_FOUND}: {item.project_id or item.source_record_id} -> {experience_id}")
        for capability in role.selected_capabilities:
            for requirement_id in capability.supported_requirement_ids:
                if requirement_id not in safe_requirement_ids:
                    warnings.append("unsupported requirement selected")
        for technology in role.selected_technologies:
            if not technology.evidence_ids:
                warnings.append("JD-only technology selection")
    if len(role_plans) > 1 and len(set(all_theme_sets)) == 1 and all_theme_sets[0]:
        warnings.append("identical themes across all roles")
    return dedupe(warnings)


def generic_capabilities_dominate(themes: list[str]) -> bool:
    if not themes:
        return False
    generic = sum(1 for theme in themes if normalize(theme) in GENERIC_CAPABILITIES or "documentation" in normalize(theme) or "collaboration" in normalize(theme))
    return generic / len(themes) > 0.6


def has_metadata_text(text: str) -> bool:
    return normalize(text) in {"company", "client", "location", "present"}


def token_overlap(left: str, right: str) -> float:
    left_tokens = meaningful_tokens(left)
    right_tokens = meaningful_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(1, len(left_tokens))


def meaningful_tokens(value: str) -> set[str]:
    stop = {
        "and",
        "or",
        "the",
        "with",
        "for",
        "to",
        "of",
        "in",
        "on",
        "a",
        "an",
        "using",
        "built",
        "developed",
        "worked",
        "delivered",
    }
    return {token for token in re.findall(r"[a-z0-9+#.]+", normalize(value)) if len(token) > 1 and token not in stop}


def contains_phrase(text: str, phrase: str) -> bool:
    return normalize(phrase) in normalize(text)


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output = []
    for item in items:
        key = normalize(item)
        if key and key not in seen:
            seen.add(key)
            output.append(item)
    return output


def dedupe_technologies(items: list[ExperienceTechnologySelection]) -> list[ExperienceTechnologySelection]:
    by_name: dict[str, ExperienceTechnologySelection] = {}
    for item in items:
        key = normalize(item.name)
        current = by_name.get(key)
        if current:
            current.evidence_ids = dedupe([*current.evidence_ids, *item.evidence_ids])
        else:
            by_name[key] = item
    return list(by_name.values())[:10]
