from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.resume import ProfileEvidenceItem, ProfileEvidenceType


@dataclass(frozen=True)
class ResponsibilityMatch:
    concepts: tuple[str, ...]
    reason: str


DIRECT_RESPONSIBILITY_EVIDENCE = {
    ProfileEvidenceType.work_experience,
    ProfileEvidenceType.achievement,
    ProfileEvidenceType.project,
}


def controlled_responsibility_match(requirement_text: str, evidence: ProfileEvidenceItem) -> ResponsibilityMatch | None:
    if evidence.evidence_type not in DIRECT_RESPONSIBILITY_EVIDENCE:
        return None

    requirement = normalize_responsibility_text(requirement_text)
    evidence_text = normalize_responsibility_text(
        " ".join(
            value
            for value in [
                evidence.source_label,
                evidence.original_text,
                evidence.company_name or "",
                evidence.role_title or "",
                evidence.project_name or "",
            ]
            if value
        )
    )
    requirement_concepts = extract_requirement_concepts(requirement)
    evidence_concepts = extract_evidence_concepts(evidence_text)
    if not requirement_concepts or not evidence_concepts:
        return None
    if prohibited_escalation(requirement_concepts, evidence_concepts, requirement, evidence_text):
        return None

    matched = sorted(concept for concept in requirement_concepts if concept in evidence_concepts)
    if not matched:
        return None
    if not requirement_is_satisfied(requirement_concepts, evidence_concepts, matched):
        return None

    explanation_concepts = sorted(set(matched) | supporting_explanation_concepts(requirement_concepts, evidence_concepts))
    return ResponsibilityMatch(tuple(matched), explain_responsibility_match(explanation_concepts, evidence.original_text))


def semantic_reason_for_match(requirement_text: str, evidence_items: list[ProfileEvidenceItem]) -> str | None:
    for evidence in evidence_items:
        match = controlled_responsibility_match(requirement_text, evidence)
        if match:
            return match.reason
    return None


def extract_requirement_concepts(text: str) -> set[str]:
    concepts: set[str] = set()

    if has_any(text, "troubleshoot production", "production incident", "production issue"):
        concepts.add("production_incident_resolution")
    if has_any(text, "resolve application defect", "application defect", "bug fix", "defect resolution"):
        concepts.add("application_defect_resolution")
    if has_any(text, "root cause", "root-cause"):
        concepts.add("root_cause_analysis")

    if has_any(text, "rest based backend service", "rest backend service", "rest api", "restful api", "api development"):
        concepts.add("rest_api_development")
    if has_any(text, "backend service", "back end service"):
        concepts.add("backend_service_development")

    if has_any(text, "optimize database quer", "query optimization", "query tuning"):
        concepts.add("database_query_optimization")
    if has_any(text, "stored procedure"):
        concepts.add("stored_procedure_development")
    if has_any(text, "application performance", "performance optimization"):
        concepts.add("application_performance_optimization")

    if collaborator_count(text) >= 2 or has_any(text, "cross functional", "cross-functional"):
        concepts.add("cross_functional_collaboration")

    if has_any(text, "document system", "technical documentation", "technical change", "support procedure"):
        concepts.add("technical_documentation")

    if has_any(text, "maintain and enhance", "maintain existing", "enhance existing", "application maintenance"):
        concepts.add("application_maintenance")
    if has_any(text, "enhance existing", "application enhancement", "maintain and enhance"):
        concepts.add("application_enhancement")

    if has_any(text, "healthcare claim", "claims and provider", "claims status"):
        concepts.add("healthcare_claims_support")
    if has_any(text, "provider application", "provider app", "provider workflow"):
        concepts.add("healthcare_provider_support")

    if has_any(text, "architect enterprise", "architecture ownership", "system wide technical strategy", "system-wide technical strategy"):
        concepts.add("architecture_ownership")
    if has_any(text, "technical strategy", "define strategy"):
        concepts.add("technical_strategy")
    if has_any(text, "lead engineering team", "lead teams", "engineering leadership"):
        concepts.add("engineering_leadership")
    if has_any(text, "mentor developer", "mentor engineers", "mentoring"):
        concepts.add("mentoring")
    if has_any(text, "own the complete", "complete software delivery lifecycle", "own complete lifecycle"):
        concepts.add("complete_lifecycle_ownership")
    if contains_metric(text):
        concepts.add("quantified_metric")
    if has_any(text, "epic bridges", "epic bridge"):
        concepts.add("epic_bridges")
    if has_any(text, "microservices architecture", "microservice architecture"):
        concepts.add("microservices_architecture")
    if has_any(text, "database architecture", "data architecture"):
        concepts.add("database_architecture")
    if has_any(text, "documentation leadership", "technical writing leadership"):
        concepts.add("documentation_leadership")
    if has_any(text, "engineering management", "manage engineers", "people management"):
        concepts.add("engineering_management")
    if has_integrated_react_api_claim(text):
        concepts.add("integrated_react_api")

    return concepts


def extract_evidence_concepts(text: str) -> set[str]:
    concepts: set[str] = set()

    if has_any(text, "production fix", "support ticket", "application failure", "production issue", "application defect"):
        concepts.add("production_incident_resolution")
        concepts.add("application_defect_resolution")
    if has_any(text, "root cause", "root-cause", "correlat") and has_any(text, "log", "failure", "defect", "issue"):
        concepts.add("root_cause_analysis")

    if has_any(text, "web api", "rest api", "restful api") and has_any(text, "built", "developed", "designed", "implemented"):
        concepts.add("rest_api_development")
        concepts.add("backend_service_development")
    if has_any(text, "backend service") and has_any(text, "built", "developed", "designed", "implemented"):
        concepts.add("backend_service_development")

    if has_any(text, "tuned sql", "query tuning", "tuned query", "optimized query", "optimized sql", "query execution"):
        concepts.add("database_query_optimization")
        concepts.add("application_performance_optimization")
    if has_any(text, "stored procedure"):
        concepts.add("stored_procedure_development")

    if collaborator_count(text) >= 2 and has_any(text, "worked with", "collaborated", "coordinated", "partnered"):
        concepts.add("cross_functional_collaboration")

    if has_any(text, "technical documentation", "troubleshooting note", "api reference", "implementation guide", "release note"):
        concepts.add("technical_documentation")

    if has_any(text, "supported and enhanced", "maintained and enhanced", "maintained", "supported existing"):
        concepts.add("application_maintenance")
    if has_any(text, "enhanced existing", "supported and enhanced", "improved existing"):
        concepts.add("application_enhancement")

    if has_any(text, "claims status", "claims-status", "healthcare claim"):
        concepts.add("healthcare_claims_support")
    if has_any(text, "provider matching", "provider application", "provider facing", "provider-facing"):
        concepts.add("healthcare_provider_support")

    if has_integrated_react_api_claim(text):
        concepts.add("integrated_react_api")
    if contains_metric(text):
        concepts.add("quantified_metric")

    return concepts


def requirement_is_satisfied(requirement_concepts: set[str], evidence_concepts: set[str], matched: list[str]) -> bool:
    unsupported = requirement_concepts - evidence_concepts
    if "quantified_metric" in unsupported:
        return False
    if "integrated_react_api" in requirement_concepts and "integrated_react_api" not in evidence_concepts:
        return False

    protected = {
        "architecture_ownership",
        "technical_strategy",
        "engineering_leadership",
        "mentoring",
        "complete_lifecycle_ownership",
        "epic_bridges",
        "microservices_architecture",
        "database_architecture",
        "documentation_leadership",
        "engineering_management",
    }
    if requirement_concepts & protected:
        return False

    positive = requirement_concepts - protected - {"quantified_metric", "integrated_react_api"}
    if not positive:
        return False
    return bool(set(matched) & positive)


def prohibited_escalation(requirement_concepts: set[str], evidence_concepts: set[str], requirement: str, evidence: str) -> bool:
    if "quantified_metric" in requirement_concepts and "quantified_metric" not in evidence_concepts:
        return True
    protected = {
        "architecture_ownership",
        "technical_strategy",
        "engineering_leadership",
        "mentoring",
        "complete_lifecycle_ownership",
        "epic_bridges",
        "microservices_architecture",
        "database_architecture",
        "documentation_leadership",
        "engineering_management",
    }
    if requirement_concepts & protected:
        return True
    if "integrated_react_api" in requirement_concepts and "integrated_react_api" not in evidence_concepts:
        return True
    if "microservices" in requirement and "api" in evidence:
        return True
    return False


def explain_responsibility_match(concepts: list[str], evidence_text: str) -> str:
    labels = {
        "production_incident_resolution": "production issue resolution",
        "application_defect_resolution": "application defect resolution",
        "root_cause_analysis": "root-cause analysis",
        "rest_api_development": "REST API development",
        "backend_service_development": "backend service development",
        "database_query_optimization": "SQL query tuning",
        "stored_procedure_development": "stored procedure work",
        "application_performance_optimization": "application performance optimization",
        "cross_functional_collaboration": "cross-functional collaboration",
        "technical_documentation": "technical documentation",
        "application_maintenance": "application maintenance",
        "application_enhancement": "application enhancement",
        "healthcare_claims_support": "healthcare claims support",
        "healthcare_provider_support": "healthcare provider application support",
    }
    readable = ", ".join(labels.get(concept, concept.replace("_", " ")) for concept in concepts[:3])
    return f"The profile evidence describes {readable}, which safely supports the JD responsibility without adding unsupported seniority, product, metric, or ownership claims."


def supporting_explanation_concepts(requirement_concepts: set[str], evidence_concepts: set[str]) -> set[str]:
    supporting: set[str] = set()
    if {"production_incident_resolution", "application_defect_resolution"} & requirement_concepts:
        if "root_cause_analysis" in evidence_concepts:
            supporting.add("root_cause_analysis")
    return supporting


def collaborator_count(text: str) -> int:
    groups = (
        ("product owner", "product owners", "product manager", "product managers"),
        ("qa", "quality assurance"),
        ("infrastructure", "infra"),
        ("engineering team", "engineering teams", "developers", "developer"),
        ("business analyst", "business analysts", "business user", "business users"),
        ("deployment team", "deployment teams", "devops"),
        ("stakeholder", "stakeholders"),
        ("architect", "architects"),
    )
    return sum(1 for group in groups if has_any(text, *group))


def has_integrated_react_api_claim(text: str) -> bool:
    return (
        has_any(text, "react")
        and has_any(text, "api", "apis", "asp net core")
        and has_any(text, "integrated with", "connected to", "wired to", "consumed", "calling")
    )


def contains_metric(text: str) -> bool:
    return bool(
        re.search(
            r"\b\d+(?:\.\d+)?\s*(?:%|percent\b|hours?\b|days?\b|weeks?\b|months?\b|users?\b|defects?\b|tickets?\b|incidents?\b)",
            text,
        )
    )


def has_any(text: str, *phrases: str) -> bool:
    return any(phrase in text for phrase in phrases)


def normalize_responsibility_text(value: str) -> str:
    text = str(value or "").lower().replace("&", " and ")
    text = text.replace(".net", " dotnet ")
    text = re.sub(r"(?<=\w)[./](?=\w)", " ", text)
    text = re.sub(r"[^a-z0-9+#% ]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
