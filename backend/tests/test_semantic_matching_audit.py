from app.schemas.resume import (
    CandidateProfile,
    JobAnalysisResponse,
    JobKeywordAnalysisItem,
    ResumeContact,
    ResumeExperience,
    SkillCategory,
)
from app.services.profile_matching import match_job_to_profile


def keyword(
    value: str,
    *,
    source_type: str = "explicit",
    category: str = "General",
    priority: str | None = None,
    priority_score: int | None = None,
) -> JobKeywordAnalysisItem:
    resolved_priority = priority or ("high" if source_type == "explicit" else "low")
    resolved_score = priority_score if priority_score is not None else (90 if source_type == "explicit" else 20)
    return JobKeywordAnalysisItem(
        id=f"keyword-{value.lower().replace(' ', '-')}",
        value=value,
        normalizedValue=value,
        category=category,
        sourceType=source_type,
        confidence="high" if source_type == "explicit" else "low",
        priority=resolved_priority,
        priorityScore=resolved_score,
        directFromJD=source_type == "explicit",
        evidenceText=f"JD mentions {value}" if source_type == "explicit" else None,
        sourceSentence=f"JD mentions {value}" if source_type == "explicit" else None,
        occurrenceCount=1,
    )


def analysis(*items: JobKeywordAnalysisItem) -> JobAnalysisResponse:
    return JobAnalysisResponse(
        roleInformation={"title": "Software Engineer", "seniority": "Senior"},
        keywords=list(items),
        analysisHash="semantic-audit",
    )


def profile(*, skills: list[str] | None = None, raw_notes: str = "", title: str = "Senior Developer") -> CandidateProfile:
    experience = [ResumeExperience(company="Company", role="Developer", rawNotes=raw_notes)] if raw_notes else []
    return CandidateProfile(
        name="Test Candidate",
        title=title,
        contact=ResumeContact(email="test@example.com"),
        skills=[SkillCategory(category="Technical Skills", items=skills or [])],
        experience=experience,
    )


def get_match(result, value: str):
    matches = [
        *result.match_summary.matched_requirements,
        *result.match_summary.partially_matched_requirements,
        *result.match_summary.unmatched_requirements,
    ]
    return next(item for item in matches if item.requirement_value == value)


def get_match_or_none(result, value: str):
    matches = [
        *result.match_summary.matched_requirements,
        *result.match_summary.partially_matched_requirements,
        *result.match_summary.unmatched_requirements,
    ]
    return next((item for item in matches if item.requirement_value == value), None)


def test_audit_exact_match_is_safe_and_uses_direct_evidence() -> None:
    result = match_job_to_profile(analysis(keyword("C#", category="Languages")), profile(skills=["C#"]))

    match = get_match(result, "C#")
    assert match.classification == "exact"
    assert match.is_safe_to_use is True
    assert match.requires_user_confirmation is False
    assert match.evidence[0].original_text == "C#"


def test_audit_normalized_equivalent_should_be_distinct_from_exact() -> None:
    result = match_job_to_profile(analysis(keyword("C#", category="Languages")), profile(skills=["C sharp"]))

    match = get_match(result, "C#")
    assert match.classification == "normalized"
    assert match.is_safe_to_use is True


def test_audit_semantic_adjacent_match_is_not_resume_safe() -> None:
    result = match_job_to_profile(analysis(keyword("Azure", category="Cloud")), profile(skills=["AWS"]))

    match = get_match(result, "Azure")
    assert match.classification == "adjacent"
    assert match.is_safe_to_use is False
    assert match.requires_user_confirmation is True
    assert match.adjacent_evidence


def test_audit_specific_requirement_with_only_broad_evidence_is_unsupported() -> None:
    result = match_job_to_profile(analysis(keyword("Azure", category="Cloud")), profile(skills=["Cloud Platforms"]))

    match = get_match(result, "Azure")
    assert match.classification == "adjacent"
    assert match.is_safe_to_use is False
    assert match.requires_user_confirmation is True


def test_audit_broad_requirement_can_be_supported_by_specific_evidence() -> None:
    result = match_job_to_profile(analysis(keyword("Cloud Platforms", category="Cloud")), profile(skills=["Azure"]))

    match = get_match(result, "Cloud Platforms")
    assert match.classification == "normalized"
    assert match.is_safe_to_use is True
    assert match.evidence[0].original_text == "Azure"


def test_audit_related_but_insufficient_evidence_stays_adjacent() -> None:
    result = match_job_to_profile(
        analysis(keyword("Technical Leadership", category="Leadership")),
        profile(title="Senior Developer"),
    )

    match = get_match(result, "Technical Leadership")
    assert match.classification == "adjacent"
    assert match.is_safe_to_use is False
    assert "Senior Developer" in match.adjacent_evidence[0].original_text


def test_audit_unmatched_requirement_has_no_evidence() -> None:
    result = match_job_to_profile(
        analysis(keyword("Trading", category="Domain")),
        profile(raw_notes="Built healthcare provider portal workflows."),
    )

    match = get_match(result, "Trading")
    assert match.classification == "unmatched"
    assert match.is_safe_to_use is False
    assert not match.evidence
    assert not match.adjacent_evidence


def test_audit_suggested_skill_must_not_be_treated_as_candidate_evidence() -> None:
    result = match_job_to_profile(
        analysis(keyword("Kubernetes", source_type="suggested", category="DevOps")),
        profile(skills=["Kubernetes"]),
    )

    assert get_match_or_none(result, "Kubernetes") is None
    assert result.match_summary.exact_match_count == 0
    assert result.match_summary.normalized_match_count == 0
    assert result.match_summary.adjacent_match_count == 0
    assert result.match_summary.unmatched_count == 0


def test_audit_suggested_absent_skill_is_excluded_from_matching() -> None:
    result = match_job_to_profile(
        analysis(keyword("Kubernetes", source_type="suggested", category="DevOps")),
        profile(skills=["C#"]),
    )

    assert get_match_or_none(result, "Kubernetes") is None
    assert result.match_summary.gaps == []
    assert result.match_summary.warnings == []


def test_audit_suggested_keyword_does_not_alter_supported_counts() -> None:
    without_suggested = match_job_to_profile(
        analysis(keyword("C#", category="Languages")),
        profile(skills=["C#", "Kubernetes"]),
        profile_id="audit-suggested-without",
    )
    with_suggested = match_job_to_profile(
        analysis(keyword("C#", category="Languages"), keyword("Kubernetes", source_type="suggested", category="DevOps")),
        profile(skills=["C#", "Kubernetes"]),
        profile_id="audit-suggested-with",
    )

    assert with_suggested.match_summary.exact_match_count == without_suggested.match_summary.exact_match_count
    assert with_suggested.match_summary.normalized_match_count == without_suggested.match_summary.normalized_match_count
    assert with_suggested.match_summary.adjacent_match_count == without_suggested.match_summary.adjacent_match_count
    assert with_suggested.match_summary.overall_match_score == without_suggested.match_summary.overall_match_score
    assert get_match_or_none(with_suggested, "Kubernetes") is None


def test_audit_required_version_of_suggested_keyword_matches_normally() -> None:
    result = match_job_to_profile(
        analysis(keyword("Kubernetes", category="DevOps")),
        profile(skills=["Kubernetes"]),
    )

    match = get_match(result, "Kubernetes")
    assert match.classification == "exact"
    assert match.is_safe_to_use is True


def test_audit_preferred_explicit_keyword_follows_existing_matching_rules() -> None:
    result = match_job_to_profile(
        analysis(keyword("Kubernetes", category="DevOps", source_type="explicit", priority="low", priority_score=30)),
        profile(skills=["Kubernetes"]),
    )

    match = get_match(result, "Kubernetes")
    assert match.classification == "exact"
    assert match.is_safe_to_use is True
    assert match.requirement_priority == "low"


def test_audit_case_only_difference_remains_exact() -> None:
    result = match_job_to_profile(analysis(keyword("React", category="Frontend")), profile(skills=["react"]))

    assert get_match(result, "React").classification == "exact"


def test_audit_whitespace_only_difference_remains_exact() -> None:
    result = match_job_to_profile(analysis(keyword("REST API", category="API")), profile(skills=["REST   API"]))

    assert get_match(result, "REST API").classification == "exact"


def test_audit_controlled_technology_aliases_are_normalized() -> None:
    cases = [
        ("MS SQL Server", "Microsoft SQL Server"),
        ("TSQL", "T-SQL"),
        ("MS Test", "MSTest"),
        ("EF Core", "Entity Framework Core"),
        ("RESTful API", "REST API"),
    ]
    for requirement, evidence in cases:
        result = match_job_to_profile(analysis(keyword(requirement, category="Technical")), profile(skills=[evidence]))
        assert get_match(result, requirement).classification == "normalized"


def test_audit_related_but_different_technologies_do_not_normalize() -> None:
    result = match_job_to_profile(analysis(keyword("Java", category="Languages")), profile(skills=["JavaScript"]))

    assert get_match(result, "Java").classification == "unmatched"


def test_audit_azure_and_azure_kubernetes_service_remain_distinct() -> None:
    result = match_job_to_profile(analysis(keyword("Azure", category="Cloud")), profile(skills=["Azure Kubernetes Service"]))

    match = get_match(result, "Azure")
    assert match.classification == "adjacent"
    assert match.is_safe_to_use is False


def test_audit_unit_test_frameworks_are_adjacent_not_normalized() -> None:
    result = match_job_to_profile(analysis(keyword("NUnit", category="Testing")), profile(skills=["Jest"]))

    assert get_match(result, "NUnit").classification in {"adjacent", "unmatched"}
