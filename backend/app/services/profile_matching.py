from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date

from app.schemas.resume import (
    CandidateProfile,
    JobAnalysisResponse,
    JobKeywordAnalysisItem,
    KeywordSourceType,
    MatchClassification,
    ProfileEvidenceItem,
    ProfileEvidenceType,
    ProfileMatchResponse,
    ProfileMatchSummary,
    RequirementMatch,
)
from app.services.responsibility_taxonomy import (
    controlled_responsibility_match,
    semantic_reason_for_match,
)


PROFILE_MATCH_CACHE_VERSION = "profile-match-v2-responsibility-taxonomy"

_PROFILE_MATCH_CACHE: dict[str, ProfileMatchSummary] = {}


@dataclass(frozen=True)
class RequirementCandidate:
    id: str
    value: str
    normalized: str
    category: str
    priority: str
    priority_score: int
    source_type: KeywordSourceType


@dataclass(frozen=True)
class DateRange:
    start_month: int
    end_month: int


CANONICAL_ALIASES: dict[str, tuple[str, ...]] = {
    "C#": ("c#", "c sharp"),
    ".NET": (".net", "dotnet", "dot net", "c#/.net", "c# / .net"),
    "ASP.NET Core": ("asp.net core", "asp net core"),
    "MVC": ("mvc", "asp.net mvc", "asp net mvc"),
    "Object-Oriented Development": (
        "object-oriented development",
        "object oriented development",
        "object-oriented design",
        "object oriented design",
        "object-oriented programming",
        "object oriented programming",
        "oop",
    ),
    "CI/CD": (
        "ci/cd",
        "ci cd",
        "continuous integration",
        "continuous delivery",
        "continuous deployment",
        "continuous integration and delivery",
        "continuous integration and continuous delivery",
    ),
    "Code Review": ("code review", "code reviews", "peer code review", "peer code reviews"),
    "Stakeholder Collaboration": (
        "stakeholder collaboration",
        "stakeholder engagement",
        "business stakeholders",
        "collaborate with stakeholders",
    ),
    "Version Control": ("version control", "source control", "git"),
    "Technical Leadership": (
        "technical leadership",
        "engineering leadership",
        "technical guidance",
        "mentored engineers",
        "mentoring engineers",
        "led developers",
        "served as technical lead",
    ),
    "Testing Best Practices": ("testing best practices", "software testing", "application testing"),
    "Unit Testing": ("unit testing", "unit tests"),
    "NUnit": ("nunit",),
    "Jest": ("jest",),
    "Integration Testing": ("integration testing", "integration tests"),
    "Regression Testing": ("regression testing", "regression tests"),
    "Cloud Platforms": ("cloud platforms", "cloud platform", "cloud services", "cloud environment"),
    "Databases": ("databases", "database development", "database systems"),
    "SQL / Database Development": ("sql", "t-sql", "database development", "sql development"),
    "Modern Web Technologies": ("modern web technologies", "web technologies", "front-end", "frontend"),
    "Application Frameworks": ("application frameworks", "application framework", "modern development frameworks"),
    "REST API Development": ("rest api", "rest apis", "restful api", "restful apis", "api development", "apis"),
    "API Development": ("api development", "apis", "rest api", "rest apis", "service integrations"),
    "SQL Server": ("sql server", "ms sql server", "mssql", "microsoft sql server"),
    "MSTest": ("mstest", "ms test"),
    "Entity Framework": ("entity framework", "entity framework core", "ef core"),
    "T-SQL": ("t-sql", "tsql", "transact sql"),
    "PostgreSQL": ("postgresql", "postgres"),
    "Google Cloud": ("google cloud", "gcp"),
    "AWS": ("aws", "amazon web services"),
    "Azure": ("azure", "microsoft azure"),
    "Azure Kubernetes Service": ("azure kubernetes service", "aks"),
    "Financial Services": ("financial services", "fintech", "banking", "payments", "aml", "anti money laundering"),
    "Trading": ("trading", "trading systems", "trading applications"),
    "Healthcare": ("healthcare", "provider portal", "claims", "authorizations"),
    "Bachelor's Degree": ("bachelor's degree", "bachelors degree", "bachelor degree", "bs degree", "b.s."),
}


BROAD_TO_SPECIFIC: dict[str, tuple[str, ...]] = {
    "Cloud Platforms": ("Azure", "AWS", "Google Cloud"),
    "Databases": ("SQL Server", "PostgreSQL", "MySQL", "Oracle", "MongoDB", "SQL / Database Development"),
    "Modern Web Technologies": ("React", "Angular", "JavaScript", "TypeScript", "HTML", "CSS", "Next.js", "Node.js"),
    "Application Frameworks": ("ASP.NET Core", "MVC", "Entity Framework", "React", "Angular", "Node.js", ".NET"),
    "Testing Best Practices": ("Unit Testing", "Integration Testing", "Regression Testing", "NUnit", "MSTest", "Jest"),
    "API Development": ("REST API Development", "REST APIs", "Swagger", "Postman"),
    "REST API Development": ("REST APIs", "Swagger", "Postman"),
}


SAME_CATEGORY_ADJACENT: tuple[tuple[str, ...], ...] = (
    ("Azure", "AWS", "Google Cloud", "Azure Kubernetes Service", "Cloud Platforms"),
    ("SQL Server", "PostgreSQL", "MySQL", "Oracle", "MongoDB", "Databases"),
    ("NUnit", "MSTest", "Jest", "Unit Testing", "Testing Best Practices"),
)


LEADERSHIP_EVIDENCE_PATTERNS = (
    r"\bled\b.+\b(developer|developers|engineer|engineers|team|delivery|review|reviews)\b",
    r"\bprovided technical guidance\b",
    r"\bmentored\b",
    r"\bowned architecture\b",
    r"\barchitecture decisions\b",
    r"\bserved as (?:a )?technical lead\b",
    r"\bcoordinated technical delivery\b",
    r"\bled code reviews\b",
)


def match_job_to_profile(
    job_analysis: JobAnalysisResponse,
    profile: CandidateProfile | None,
    profile_id: str = "local-profile",
    profile_updated_at: str = "",
    profile_version: int = 0,
    profile_content_hash: str = "",
) -> ProfileMatchResponse:
    validate_profile_for_matching(profile)
    assert profile is not None

    cache_key = profile_match_cache_key(
        job_analysis,
        profile,
        profile_id,
        profile_updated_at,
        profile_version,
        profile_content_hash,
    )
    cached = _PROFILE_MATCH_CACHE.get(cache_key)
    if cached:
        return ProfileMatchResponse(
            matchSummary=cached,
            cacheVersion=PROFILE_MATCH_CACHE_VERSION,
            cacheHit=True,
            profileId=profile_id,
            profileVersion=profile_version,
            profileUpdatedAt=profile_updated_at,
            profileContentHash=profile_content_hash,
            matchingAlgorithmVersion=PROFILE_MATCH_CACHE_VERSION,
        )

    evidence_index = build_profile_evidence_index(profile, profile_id)
    requirements = requirements_from_job_analysis(job_analysis)
    matches = [match_requirement_to_profile(requirement, evidence_index, profile) for requirement in requirements]
    summary = calculate_profile_match_summary(matches)
    _PROFILE_MATCH_CACHE[cache_key] = summary
    return ProfileMatchResponse(
        matchSummary=summary,
        cacheVersion=PROFILE_MATCH_CACHE_VERSION,
        cacheHit=False,
        profileId=profile_id,
        profileVersion=profile_version,
        profileUpdatedAt=profile_updated_at,
        profileContentHash=profile_content_hash,
        matchingAlgorithmVersion=PROFILE_MATCH_CACHE_VERSION,
    )


def validate_profile_for_matching(profile: CandidateProfile | None) -> None:
    if not profile:
        raise ValueError("Complete your profile before matching it against a job description.")
    fields = [
        profile.name,
        profile.title,
        profile.summary,
        " ".join(skill for group in profile.skills for skill in group.items),
        " ".join(
            " ".join([
                item.company,
                item.client_name or "",
                item.role,
                item.raw_notes,
                item.legacy_notes,
                *item.responsibilities,
                *item.achievements,
                *item.technologies,
                *[f"{metric.label} {metric.value}" for metric in item.metrics],
                *item.bullets,
            ])
            for item in profile.experience
        ),
        " ".join(" ".join([item.name, *item.technologies, *item.bullets]) for item in profile.projects),
        " ".join(" ".join([item.degree, item.institution]) for item in profile.education),
        " ".join(" ".join([item.name, item.issuer]) for item in profile.certifications),
    ]
    if not any(value.strip() for value in fields):
        raise ValueError("Complete your profile before matching it against a job description.")


def build_profile_evidence_index(profile: CandidateProfile, profile_id: str = "local-profile") -> list[ProfileEvidenceItem]:
    evidence: list[ProfileEvidenceItem] = []
    if profile.title.strip():
        evidence.append(
            evidence_item(
                "profile-title",
                ProfileEvidenceType.summary,
                "Profile title",
                profile.title,
                strength=50,
                reason="Candidate's stored professional title.",
            )
        )
    if profile.summary.strip():
        evidence.append(
            evidence_item(
                "profile-summary",
                ProfileEvidenceType.summary,
                "Profile summary",
                profile.summary,
                strength=50,
                reason="Candidate's stored professional summary.",
            )
        )

    for category_index, group in enumerate(profile.skills):
        for skill_index, skill in enumerate(group.items):
            if skill.strip():
                evidence.append(
                    evidence_item(
                        stable_evidence_id("profile", profile_id, "skill", skill, duplicate_index(evidence, f"profile-{profile_id}-skill-{slug(skill)}")),
                        ProfileEvidenceType.skill,
                        f"Technical Skills - {group.category}",
                        skill,
                        strength=85,
                        reason="Direct technical skill stored in the candidate profile.",
                    )
                )

    for index, experience in enumerate(profile.experience):
        experience_id = experience.experience_id or stable_parent_id(
            "experience",
            "|".join([experience.company, experience.role, experience.start_date]),
        )
        record_id = f"experience-{experience_id}"
        source_label = f"{experience.role or 'Role'} at {experience.company or 'Company'}".strip()
        for field_name, value in (
            ("company", experience.company),
            ("client", experience.client_name or ""),
            ("role", experience.role),
            ("location", experience.location),
            ("raw-notes", experience.raw_notes),
            ("legacy-notes", experience.legacy_notes),
        ):
            if value.strip():
                evidence.append(
                    evidence_item(
                        f"{record_id}-{field_name}-{content_digest(value)}",
                        ProfileEvidenceType.work_experience,
                        source_label,
                        value,
                        source_record_id=record_id,
                        company_name=experience.company or None,
                        role_title=experience.role or None,
                        strength=95 if field_name == "raw-notes" else 45 if field_name == "legacy-notes" else 70,
                        reason="Stored work-experience field." if field_name != "legacy-notes" else "Legacy free-text preserved for review; not treated as validated metric evidence.",
                    )
                )
        for kind, values, evidence_type, strength, reason in (
            ("responsibility", experience.responsibilities, ProfileEvidenceType.work_experience, 90, "Structured responsibility stored in the candidate profile."),
            ("technology", experience.technologies, ProfileEvidenceType.skill, 90, "Technology stored on a specific work experience."),
            ("achievement", experience.achievements, ProfileEvidenceType.achievement, 95, "Structured achievement stored in the candidate profile."),
        ):
            for value in values:
                if value.strip():
                    evidence.append(
                        evidence_item(
                            f"{record_id}-{kind}-{content_digest(value)}",
                            evidence_type,
                            source_label,
                            value,
                            source_record_id=record_id,
                            company_name=experience.company or None,
                            role_title=experience.role or None,
                            strength=strength,
                            reason=reason,
                        )
                    )
        for metric in experience.metrics:
            original = " ".join(value for value in [metric.label, metric.value] if value)
            if original.strip():
                evidence.append(
                    evidence_item(
                        f"{record_id}-metric-{content_digest(original)}",
                        ProfileEvidenceType.achievement,
                        source_label,
                        original,
                        source_record_id=record_id,
                        company_name=experience.company or None,
                        role_title=experience.role or None,
                        strength=100,
                        reason="Structured metric stored in the candidate profile.",
                    )
                )
        for bullet_index, bullet in enumerate(experience.bullets):
            if bullet.strip():
                evidence.append(
                    evidence_item(
                        f"{record_id}-statement-{content_digest(bullet)}",
                        ProfileEvidenceType.work_experience,
                        source_label,
                        bullet,
                        source_record_id=record_id,
                        company_name=experience.company or None,
                        role_title=experience.role or None,
                        strength=95,
                        reason="Stored work-experience bullet.",
                    )
                )
        for metric_index, metric in enumerate(experience.metric_flags):
            if metric.strip():
                evidence.append(
                    evidence_item(
                        f"{record_id}-achievement-{content_digest(metric)}",
                        ProfileEvidenceType.achievement,
                        source_label,
                        metric,
                        source_record_id=record_id,
                        company_name=experience.company or None,
                        role_title=experience.role or None,
                        strength=100,
                        reason="Stored achievement or impact metric.",
                    )
                )

    for index, project in enumerate(profile.projects):
        project_id = project.project_id or stable_parent_id("project", "|".join([project.name, project.org]))
        record_id = f"project-{project_id}"
        source_label = f"Project - {project.name}"
        for bullet in project.bullets:
            if bullet.strip():
                evidence.append(
                    evidence_item(
                        f"{record_id}-bullet-{content_digest(bullet)}",
                        ProfileEvidenceType.project,
                        source_label,
                        bullet,
                        source_record_id=record_id,
                        project_name=project.name or None,
                        project_id=project_id,
                        linked_experience_ids=project.linked_experience_ids,
                        strength=80,
                        reason="Stored project bullet evidence.",
                    )
                )
        for technology in project.technologies:
            if technology.strip():
                evidence.append(
                    evidence_item(
                        f"{record_id}-technology-{content_digest(technology)}",
                        ProfileEvidenceType.project,
                        source_label,
                        technology,
                        source_record_id=record_id,
                        project_name=project.name or None,
                        project_id=project_id,
                        linked_experience_ids=project.linked_experience_ids,
                        strength=85,
                        reason="Stored project technology evidence.",
                    )
                )

    for index, education in enumerate(profile.education):
        education_id = education.education_id or stable_parent_id(
            "education",
            "|".join([education.degree, education.institution, education.grad_year]),
        )
        original = " ".join(
            value for value in [education.degree, education.institution, education.location, education.grad_year, education.gpa] if value
        )
        if original.strip():
            evidence.append(
                evidence_item(
                    f"education-{education_id}",
                    ProfileEvidenceType.education,
                    f"Education - {education.institution or education.degree}",
                    original,
                    source_record_id=f"education-{education_id}",
                    strength=90,
                    reason="Stored education record.",
                )
            )

    for index, certification in enumerate(profile.certifications):
        certification_id = certification.certification_id or stable_parent_id(
            "certification",
            "|".join([certification.name, certification.issuer, certification.issued_date]),
        )
        original = " ".join(
            value for value in [certification.name, certification.issuer, certification.issued_date, certification.expiry_date] if value
        )
        if original.strip():
            evidence.append(
                evidence_item(
                    f"certification-{certification_id}",
                    ProfileEvidenceType.certification,
                    f"Certification - {certification.name}",
                    original,
                    source_record_id=f"certification-{certification_id}",
                    strength=95,
                    reason="Stored certification record.",
                )
            )

    return evidence


def evidence_item(
    evidence_id: str,
    evidence_type: ProfileEvidenceType,
    source_label: str,
    original_text: str,
    *,
    source_record_id: str | None = None,
    matched_text: str | None = None,
    company_name: str | None = None,
    role_title: str | None = None,
    project_name: str | None = None,
    project_id: str | None = None,
    linked_experience_ids: list[str] | None = None,
    strength: int,
    reason: str,
) -> ProfileEvidenceItem:
    return ProfileEvidenceItem(
        evidenceId=evidence_id,
        evidenceType=evidence_type,
        sourceRecordId=source_record_id,
        sourceLabel=source_label,
        originalText=original_text.strip(),
        matchedText=matched_text,
        companyName=company_name,
        roleTitle=role_title,
        projectName=project_name,
        projectId=project_id,
        linkedExperienceIds=linked_experience_ids or [],
        strengthScore=max(0, min(100, strength)),
        reason=reason,
    )


def stable_parent_id(prefix: str, value: str) -> str:
    return f"{prefix}-{content_digest(value or prefix)}"


def stable_evidence_id(prefix: str, profile_id: str, kind: str, value: str, duplicate: int = 0) -> str:
    base = f"{prefix}-{profile_id}-{kind}-{slug(value)}"
    return f"{base}-{duplicate}" if duplicate else base


def duplicate_index(items: list[ProfileEvidenceItem], evidence_id: str) -> int:
    return sum(1 for item in items if item.evidence_id == evidence_id or item.evidence_id.startswith(f"{evidence_id}-"))


def content_digest(value: str) -> str:
    return hashlib.sha256(normalize_key(value).encode("utf-8")).hexdigest()[:16]


def requirements_from_job_analysis(job_analysis: JobAnalysisResponse) -> list[RequirementCandidate]:
    typed = requirements_from_typed_job_analysis(job_analysis)
    if typed:
        return typed
    items = job_analysis.keywords or [
        *job_analysis.explicit_keywords,
        *job_analysis.inferred_keywords,
        *job_analysis.suggested_keywords,
    ]
    by_id: dict[str, RequirementCandidate] = {}
    for item in items:
        if item.source_type == KeywordSourceType.suggested:
            continue
        value = item.value or item.term
        if not value.strip():
            continue
        requirement = requirement_from_keyword(item)
        existing = by_id.get(requirement.id)
        if not existing or requirement.priority_score > existing.priority_score:
            by_id[requirement.id] = requirement
    return list(by_id.values())


def requirements_from_typed_job_analysis(job_analysis: JobAnalysisResponse) -> list[RequirementCandidate]:
    groups = job_analysis.normalized_requirements
    typed_items = [
        *groups.technical_requirements,
        *groups.responsibility_requirements,
        *groups.experience_requirements,
        *groups.education_requirements,
        *groups.certification_requirements,
        *groups.leadership_requirements,
        *groups.soft_skill_requirements,
        *groups.domain_requirements,
    ]
    by_id: dict[str, RequirementCandidate] = {}
    for item in typed_items:
        if not item.explicit or item.requirement_level == "inferred":
            continue
        candidate = RequirementCandidate(
            id=item.requirement_id,
            value=item.canonical_term,
            normalized=canonicalize(item.canonical_term),
            category=item.category,
            priority=typed_priority_to_match_priority(item.priority),
            priority_score=typed_priority_to_score(item.priority),
            source_type=KeywordSourceType.explicit,
        )
        existing = by_id.get(candidate.id)
        if not existing or candidate.priority_score > existing.priority_score:
            by_id[candidate.id] = candidate
    return list(by_id.values())


def typed_priority_to_match_priority(priority: str) -> str:
    return "high" if str(priority).lower() in {"critical", "high"} else "medium" if str(priority).lower() == "medium" else "low"


def typed_priority_to_score(priority: str) -> int:
    return {"critical": 95, "high": 85, "medium": 60, "low": 35}.get(str(priority).lower(), 60)


def requirement_from_keyword(item: JobKeywordAnalysisItem) -> RequirementCandidate:
    raw_value = (item.value or item.term).strip()
    value = raw_value or canonicalize(raw_value)
    return RequirementCandidate(
        id=item.id or f"keyword-{slug(value)}",
        value=value,
        normalized=canonicalize(value),
        category=item.category or "General",
        priority=str(item.priority.value if hasattr(item.priority, "value") else item.priority),
        priority_score=item.priority_score,
        source_type=item.source_type,
    )


def match_requirement_to_profile(
    requirement: RequirementCandidate,
    evidence_index: list[ProfileEvidenceItem],
    profile: CandidateProfile,
) -> RequirementMatch:
    years_match = match_years_requirement(requirement, profile)
    if years_match:
        return years_match

    education_match = match_education_requirement(requirement, evidence_index)
    if education_match:
        return education_match

    exact = evidence_matching_requirement(requirement, evidence_index, MatchClassification.exact)
    if exact:
        return build_requirement_match(requirement, MatchClassification.exact, exact, [])

    normalized = evidence_matching_requirement(requirement, evidence_index, MatchClassification.normalized)
    if normalized:
        return build_requirement_match(requirement, MatchClassification.normalized, normalized, [])

    adjacent = evidence_matching_requirement(requirement, evidence_index, MatchClassification.adjacent)
    if adjacent:
        return build_requirement_match(requirement, MatchClassification.adjacent, [], adjacent)

    return build_requirement_match(requirement, MatchClassification.unmatched, [], [])


def evidence_matching_requirement(
    requirement: RequirementCandidate,
    evidence_index: list[ProfileEvidenceItem],
    classification: MatchClassification,
) -> list[ProfileEvidenceItem]:
    matches: list[ProfileEvidenceItem] = []
    for evidence in evidence_index:
        result = classify_evidence_against_requirement(requirement, evidence)
        if result == classification:
            matches.append(evidence_with_match(evidence, requirement.value, classification))
    return strongest_unique_evidence(matches)


def classify_evidence_against_requirement(requirement: RequirementCandidate, evidence: ProfileEvidenceItem) -> MatchClassification:
    canonical_requirement = requirement.normalized or canonicalize(requirement.value)
    text = evidence_text(evidence)

    if canonical_requirement == "Technical Leadership":
        if leadership_evidence_is_direct(text):
            return MatchClassification.normalized
        if evidence.evidence_type == ProfileEvidenceType.summary and "senior" in normalize_key(text):
            return MatchClassification.adjacent
        return MatchClassification.unmatched

    if canonical_requirement == "Trading":
        return MatchClassification.exact if contains_canonical(text, "Trading") else MatchClassification.unmatched

    if canonical_requirement == "Financial Services":
        return MatchClassification.normalized if contains_canonical(text, "Financial Services") else MatchClassification.unmatched

    if canonical_requirement == "Databases":
        original_only = normalize_key(evidence.original_text)
        if phrase_in_text("databases", original_only) or phrase_in_text("database development", original_only):
            return MatchClassification.normalized
        return MatchClassification.unmatched

    if contains_exact_requirement_text(text, requirement.value):
        return MatchClassification.exact

    if contains_controlled_alias(text, canonical_requirement):
        return MatchClassification.normalized

    if controlled_responsibility_match(requirement.value, evidence):
        return MatchClassification.normalized

    if canonical_requirement in BROAD_TO_SPECIFIC and any(contains_canonical(text, specific) for specific in BROAD_TO_SPECIFIC[canonical_requirement]):
        return MatchClassification.normalized

    if any(canonical_requirement == specific and contains_canonical(text, broad) for broad, specifics in BROAD_TO_SPECIFIC.items() for specific in specifics):
        return MatchClassification.adjacent

    if adjacent_same_category(canonical_requirement, text):
        return MatchClassification.adjacent

    return MatchClassification.unmatched


def match_years_requirement(
    requirement: RequirementCandidate,
    profile: CandidateProfile,
) -> RequirementMatch | None:
    required_years = required_years_from_text(requirement.value)
    if required_years is None:
        return None

    months = calculate_non_overlapping_experience_months(profile)
    calculated_years = round(months / 12, 1)
    evidence = [
        evidence_item(
            "profile-calculated-experience",
            ProfileEvidenceType.work_experience,
            "Calculated work history",
            f"{calculated_years} years of non-overlapping stored work experience",
            strength=95 if calculated_years >= required_years else 45,
            reason="Calculated from stored work-experience dates without double-counting overlaps.",
        )
    ]
    if calculated_years >= required_years:
        return build_requirement_match(requirement, MatchClassification.exact, evidence, [])
    if calculated_years >= required_years * 0.65:
        return build_requirement_match(requirement, MatchClassification.adjacent, [], evidence)
    return build_requirement_match(requirement, MatchClassification.unmatched, [], [])


def match_education_requirement(
    requirement: RequirementCandidate,
    evidence_index: list[ProfileEvidenceItem],
) -> RequirementMatch | None:
    text = normalize_key(requirement.value)
    if "degree" not in text and "bachelor" not in text and "master" not in text:
        return None

    required_discipline = education_discipline(text)
    matched: list[ProfileEvidenceItem] = []
    adjacent: list[ProfileEvidenceItem] = []
    for evidence in evidence_index:
        if evidence.evidence_type != ProfileEvidenceType.education:
            continue
        evidence_key = normalize_key(evidence.original_text)
        if not has_minimum_degree_level(text, evidence_key):
            continue
        evidence_discipline = education_discipline(evidence_key)
        if not required_discipline or required_discipline == evidence_discipline or disciplines_are_related(required_discipline, evidence_discipline):
            matched.append(evidence_with_match(evidence, requirement.value, MatchClassification.normalized))
        else:
            adjacent.append(evidence_with_match(evidence, requirement.value, MatchClassification.adjacent))
    if matched:
        return build_requirement_match(requirement, MatchClassification.normalized, matched, [])
    if adjacent:
        return build_requirement_match(requirement, MatchClassification.adjacent, [], adjacent)
    return build_requirement_match(requirement, MatchClassification.unmatched, [], [])


def build_requirement_match(
    requirement: RequirementCandidate,
    classification: MatchClassification,
    evidence: list[ProfileEvidenceItem],
    adjacent_evidence: list[ProfileEvidenceItem],
) -> RequirementMatch:
    score = requirement_match_score(classification, evidence, adjacent_evidence)
    is_safe = classification in {MatchClassification.exact, MatchClassification.normalized}
    return RequirementMatch(
        requirementId=requirement.id,
        requirementValue=requirement.value,
        requirementCategory=requirement.category,
        requirementPriority=requirement.priority,
        requirementPriorityScore=requirement.priority_score,
        sourceType=requirement.source_type,
        classification=classification,
        matchScore=score,
        evidence=evidence[:5],
        adjacentEvidence=adjacent_evidence[:5],
        isSafeToUse=is_safe,
        requiresUserConfirmation=classification == MatchClassification.adjacent,
        reason=reason_for_match(requirement.value, classification, evidence, adjacent_evidence),
    )


def requirement_match_score(
    classification: MatchClassification,
    evidence: list[ProfileEvidenceItem],
    adjacent_evidence: list[ProfileEvidenceItem],
) -> int:
    if classification == MatchClassification.unmatched:
        return 0
    sources = evidence or adjacent_evidence
    strongest = max((item.strength_score for item in sources), default=0)
    independent_sources = len({item.source_record_id or item.evidence_id for item in sources})
    source_bonus = min(8, max(0, independent_sources - 1) * 3)
    work_bonus = 5 if any(item.evidence_type in {ProfileEvidenceType.work_experience, ProfileEvidenceType.achievement} for item in sources) else 0
    score = strongest + source_bonus + work_bonus
    if classification == MatchClassification.exact:
        return max(85, min(100, score))
    if classification == MatchClassification.normalized:
        return max(70, min(89, score))
    return max(20, min(49, score))


def calculate_profile_match_summary(matches: list[RequirementMatch]) -> ProfileMatchSummary:
    scored_matches = [match for match in matches if match.source_type != KeywordSourceType.suggested]
    overall = weighted_match_score(scored_matches)
    core = weighted_match_score([match for match in scored_matches if match.requirement_priority == "high"])
    supporting = weighted_match_score([match for match in scored_matches if match.requirement_priority in {"medium", "low"}])

    matched = [match for match in matches if match.classification in {MatchClassification.exact, MatchClassification.normalized}]
    partial = [match for match in matches if match.classification == MatchClassification.adjacent]
    unmatched = [match for match in matches if match.classification == MatchClassification.unmatched]
    warnings = [
        f"Do not claim {match.requirement_value}; only adjacent evidence was found."
        for match in partial
    ]
    warnings.extend(
        f"Do not claim {match.requirement_value}; no stored profile evidence was found."
        for match in unmatched
        if match.source_type != KeywordSourceType.suggested
    )

    return ProfileMatchSummary(
        overallMatchScore=overall,
        coreRequirementScore=core,
        supportingRequirementScore=supporting,
        exactMatchCount=sum(1 for match in matches if match.classification == MatchClassification.exact),
        normalizedMatchCount=sum(1 for match in matches if match.classification == MatchClassification.normalized),
        adjacentMatchCount=len(partial),
        unmatchedCount=len(unmatched),
        matchedRequirements=matched,
        partiallyMatchedRequirements=partial,
        unmatchedRequirements=unmatched,
        strengths=[f"{match.requirement_value} supported by {match.evidence[0].source_label}" for match in matched[:8] if match.evidence],
        gaps=[match.requirement_value for match in unmatched if match.source_type != KeywordSourceType.suggested][:10],
        transferableStrengths=[
            f"{match.requirement_value} has adjacent evidence from {match.adjacent_evidence[0].source_label}"
            for match in partial[:8]
            if match.adjacent_evidence
        ],
        warnings=warnings[:12],
    )


def weighted_match_score(matches: list[RequirementMatch]) -> int:
    if not matches:
        return 0
    total_weight = 0
    contribution = 0
    for match in matches:
        weight = priority_weight(match.requirement_priority)
        total_weight += weight
        contribution += match.match_score * weight
    return round(contribution / total_weight) if total_weight else 0


def priority_weight(priority: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(str(priority).lower(), 2)


def calculate_non_overlapping_experience_months(profile: CandidateProfile) -> int:
    ranges = [
        parsed
        for item in profile.experience
        if (parsed := parse_experience_range(item.start_date, item.end_date)) is not None
    ]
    if not ranges:
        return 0
    months: set[int] = set()
    for item in ranges:
        months.update(range(item.start_month, item.end_month + 1))
    return len(months)


def parse_experience_range(start: str, end: str) -> DateRange | None:
    start_month = parse_year_month(start)
    if start_month is None:
        return None
    end_month = parse_year_month(end) if end and normalize_key(end) != "present" else current_month_index()
    if end_month is None:
        end_month = current_month_index()
    if end_month < start_month:
        return None
    return DateRange(start_month=start_month, end_month=end_month)


def parse_year_month(value: str) -> int | None:
    match = re.search(r"\b((?:19|20)\d{2})(?:[-/](0?[1-9]|1[0-2]))?\b", value or "")
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2) or "1")
    return year * 12 + month


def current_month_index() -> int:
    today = date.today()
    return today.year * 12 + today.month


def required_years_from_text(value: str) -> int | None:
    match = re.search(r"\b(\d+)\+?\s+years?\b", normalize_key(value))
    return int(match.group(1)) if match else None


def has_minimum_degree_level(requirement_text: str, evidence_text: str) -> bool:
    required = degree_level(requirement_text)
    actual = degree_level(evidence_text)
    return actual >= required > 0


def degree_level(text: str) -> int:
    if any(term in text for term in ("phd", "doctorate")):
        return 4
    if any(term in text for term in ("master", "m.s", "ms ", "mba")):
        return 3
    if any(term in text for term in ("bachelor", "b.s", "bs ", "degree")):
        return 2
    return 0


def education_discipline(text: str) -> str:
    if any(term in text for term in ("computer science", "software engineering", "computer engineering", "information systems")):
        return "computer science"
    if "finance" in text:
        return "finance"
    if "business" in text:
        return "business"
    if "engineering" in text:
        return "engineering"
    return ""


def disciplines_are_related(required: str, actual: str) -> bool:
    related = {
        "computer science": {"computer science", "engineering"},
        "engineering": {"engineering", "computer science"},
    }
    return actual in related.get(required, {required})


def evidence_with_match(
    evidence: ProfileEvidenceItem,
    requirement_value: str,
    classification: MatchClassification,
) -> ProfileEvidenceItem:
    strength = evidence.strength_score
    if classification == MatchClassification.adjacent:
        strength = min(strength, 45)
    return evidence.model_copy(
        update={
            "matched_text": requirement_value,
            "strength_score": strength,
            "reason": f"{classification.value.title()} evidence for {requirement_value}.",
        }
    )


def strongest_unique_evidence(items: list[ProfileEvidenceItem]) -> list[ProfileEvidenceItem]:
    by_id: dict[str, ProfileEvidenceItem] = {}
    for item in items:
        existing = by_id.get(item.evidence_id)
        if not existing or item.strength_score > existing.strength_score:
            by_id[item.evidence_id] = item
    return sorted(by_id.values(), key=lambda item: (-item.strength_score, item.evidence_id))[:8]


def reason_for_match(
    requirement: str,
    classification: MatchClassification,
    evidence: list[ProfileEvidenceItem],
    adjacent_evidence: list[ProfileEvidenceItem],
) -> str:
    if classification == MatchClassification.exact:
        return f"{requirement} is directly present in stored profile evidence."
    if classification == MatchClassification.normalized:
        semantic_reason = semantic_reason_for_match(requirement, evidence)
        if semantic_reason:
            return semantic_reason
        return f"{requirement} is supported by a safe canonical or direction-aware equivalent."
    if classification == MatchClassification.adjacent:
        labels = ", ".join(item.source_label for item in adjacent_evidence[:2])
        return f"{requirement} is not directly supported; related transferable evidence exists in {labels}."
    return f"No reliable stored profile evidence supports {requirement}."


def contains_canonical(text: str, canonical: str) -> bool:
    normalized = normalize_key(text)
    canonical_value = canonicalize(canonical)
    aliases = (canonical_value, *CANONICAL_ALIASES.get(canonical_value, ()))
    return any(phrase_in_text(alias, normalized) for alias in aliases)


def contains_exact_requirement_text(text: str, requirement_value: str) -> bool:
    normalized_text = normalize_key(text)
    normalized_requirement = normalize_key(requirement_value)
    if not normalized_requirement:
        return False
    if normalized_requirement == "azure" and phrase_in_text("azure kubernetes service", normalized_text):
        return False
    return phrase_in_text(normalized_requirement, normalized_text)


def contains_controlled_alias(text: str, canonical: str) -> bool:
    normalized = normalize_key(text)
    canonical_value = canonicalize(canonical)
    if canonical_value == "Azure" and phrase_in_text("azure kubernetes service", normalized):
        return False
    aliases = CANONICAL_ALIASES.get(canonical_value, ())
    return any(phrase_in_text(alias, normalized) for alias in aliases)


def adjacent_same_category(requirement: str, text: str) -> bool:
    for group in SAME_CATEGORY_ADJACENT:
        already_supported = contains_exact_requirement_text(text, requirement) or contains_controlled_alias(text, requirement)
        if requirement in group and not already_supported:
            return any(contains_canonical(text, item) for item in group if item != requirement)
    return False


def leadership_evidence_is_direct(text: str) -> bool:
    normalized = normalize_key(text)
    return any(re.search(pattern, normalized) for pattern in LEADERSHIP_EVIDENCE_PATTERNS)


def evidence_text(evidence: ProfileEvidenceItem) -> str:
    return " ".join(
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


def canonicalize(value: str) -> str:
    key = normalize_key(value)
    years = required_years_from_text(value)
    if years is not None and "experience" in key:
        return f"{years}+ Years of Experience"
    for canonical, aliases in CANONICAL_ALIASES.items():
        if key == normalize_key(canonical) or key in {normalize_key(alias) for alias in aliases}:
            return canonical
    for broad, specifics in BROAD_TO_SPECIFIC.items():
        if key == normalize_key(broad):
            return broad
        for specific in specifics:
            if key == normalize_key(specific):
                return specific
    return " ".join(part.upper() if part in {"api", "sql", "aws"} else part.capitalize() for part in key.split())


def phrase_in_text(phrase: str, normalized_text: str) -> bool:
    normalized_phrase = normalize_key(phrase)
    if not normalized_phrase:
        return False
    return bool(re.search(rf"(?<![a-z0-9+#]){re.escape(normalized_phrase)}(?![a-z0-9+#])", normalized_text))


def normalize_key(value: str) -> str:
    text = str(value or "").lower().replace("&", " and ")
    text = re.sub(r"(?<=\w)[./](?=\w)", " ", text)
    text = re.sub(r"[^a-z0-9+# ]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize_key(value)).strip("-") or "item"


def profile_match_cache_key(
    job_analysis: JobAnalysisResponse,
    profile: CandidateProfile,
    profile_id: str,
    profile_updated_at: str,
    profile_version: int = 0,
    profile_content_hash: str = "",
) -> str:
    payload = {
        "profileId": profile_id,
        "profileUpdatedAt": profile_updated_at,
        "profileVersion": profile_version,
        "profileContentHash": profile_content_hash,
        "profile": profile.model_dump(mode="json", by_alias=True),
        "analysisHash": job_analysis.analysis_hash,
        "normalizedRequirements": job_analysis.normalized_requirements.model_dump(mode="json", by_alias=True),
        "keywords": [item.model_dump(mode="json", by_alias=True) for item in job_analysis.keywords],
        "version": PROFILE_MATCH_CACHE_VERSION,
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
