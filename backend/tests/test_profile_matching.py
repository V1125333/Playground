import pytest

from app.schemas.resume import (
    CandidateProfile,
    JobAnalysisResponse,
    JobKeywordAnalysisItem,
    ResumeContact,
    ResumeEducation,
    ResumeExperience,
    SkillCategory,
)
from app.services.profile_matching import (
    PROFILE_MATCH_CACHE_VERSION,
    build_profile_evidence_index,
    calculate_non_overlapping_experience_months,
    match_job_to_profile,
)


def keyword(
    value: str,
    *,
    category: str = "General",
    priority: str = "high",
    score: int = 90,
    source_type: str = "explicit",
) -> JobKeywordAnalysisItem:
    return JobKeywordAnalysisItem(
        id=f"keyword-{value.lower().replace(' ', '-')}",
        value=value,
        normalizedValue=value,
        category=category,
        sourceType=source_type,
        confidence="high" if source_type == "explicit" else "low",
        priority=priority,
        priorityScore=score,
        directFromJD=source_type == "explicit",
        evidenceText=f"JD mentions {value}" if source_type == "explicit" else None,
        sourceSentence=f"JD mentions {value}" if source_type == "explicit" else None,
        occurrenceCount=1,
    )


def analysis(*items: JobKeywordAnalysisItem) -> JobAnalysisResponse:
    return JobAnalysisResponse(
        roleInformation={"title": "Software Engineer", "seniority": "Senior"},
        keywords=list(items),
        analysisHash="test-analysis",
    )


def profile(
    *,
    skills: list[str] | None = None,
    experience: list[ResumeExperience] | None = None,
    education: list[ResumeEducation] | None = None,
    title: str = "Senior Developer",
) -> CandidateProfile:
    return CandidateProfile(
        name="Venu Madhav Pendurthi",
        title=title,
        contact=ResumeContact(email="venu@example.com"),
        skills=[SkillCategory(category="Technical Skills", items=skills or [])],
        experience=experience or [],
        education=education or [],
    )


def only_match(result, value: str):
    matches = [
        *result.match_summary.matched_requirements,
        *result.match_summary.partially_matched_requirements,
        *result.match_summary.unmatched_requirements,
    ]
    return next(item for item in matches if item.requirement_value == value)


def test_exact_skill_match() -> None:
    result = match_job_to_profile(analysis(keyword("C#", category="Languages")), profile(skills=["C#"]))

    match = only_match(result, "C#")
    assert match.classification == "exact"
    assert match.evidence


def test_safe_normalized_skill_match() -> None:
    result = match_job_to_profile(
        analysis(keyword("Object-Oriented Development", category="Architecture")),
        profile(skills=["OOP"]),
    )

    assert only_match(result, "Object-Oriented Development").classification == "exact"


def test_broad_requirement_matches_specific_evidence_directionally() -> None:
    result = match_job_to_profile(
        analysis(keyword("Cloud Platforms", category="Cloud", priority="medium", score=60)),
        profile(skills=["Azure"]),
    )

    assert only_match(result, "Cloud Platforms").classification == "normalized"


def test_specific_requirement_does_not_match_broad_evidence_as_exact() -> None:
    result = match_job_to_profile(
        analysis(keyword("Azure", category="Cloud")),
        profile(skills=["Cloud Platforms"]),
    )

    assert only_match(result, "Azure").classification == "adjacent"


def test_different_cloud_providers_are_adjacent_not_exact() -> None:
    result = match_job_to_profile(
        analysis(keyword("Azure", category="Cloud")),
        profile(skills=["AWS"]),
    )

    assert only_match(result, "Azure").classification == "adjacent"


def test_trading_does_not_match_healthcare_domain() -> None:
    result = match_job_to_profile(
        analysis(keyword("Trading", category="Domain")),
        profile(
            experience=[
                ResumeExperience(
                    company="Healthcare Co",
                    role="Developer",
                    rawNotes="Built healthcare provider portal workflows.",
                )
            ]
        ),
    )

    assert only_match(result, "Trading").classification == "unmatched"


def test_financial_services_matches_explicit_aml_payment_context() -> None:
    result = match_job_to_profile(
        analysis(keyword("Financial Services", category="Domain")),
        profile(
            experience=[
                ResumeExperience(
                    company="Banking Co",
                    role="Developer",
                    rawNotes="Delivered financial services AML and payment platform features.",
                )
            ]
        ),
    )

    assert only_match(result, "Financial Services").classification in {"exact", "normalized"}


def test_trading_specificity_does_not_match_aml_payment_context() -> None:
    result = match_job_to_profile(
        analysis(keyword("Trading", category="Domain")),
        profile(
            experience=[
                ResumeExperience(
                    company="Banking Co",
                    role="Developer",
                    rawNotes="Delivered financial services AML and payment platform features.",
                )
            ]
        ),
    )

    assert only_match(result, "Trading").classification == "unmatched"


def test_leadership_requires_direct_evidence() -> None:
    result = match_job_to_profile(
        analysis(keyword("Technical Leadership", category="Leadership")),
        profile(
            experience=[
                ResumeExperience(
                    company="Infosys",
                    role="Senior Developer",
                    rawNotes="Provided technical guidance to five developers and led code reviews.",
                )
            ]
        ),
    )

    assert only_match(result, "Technical Leadership").classification == "normalized"


def test_senior_title_alone_is_only_adjacent_for_leadership() -> None:
    result = match_job_to_profile(
        analysis(keyword("Technical Leadership", category="Leadership")),
        profile(title="Senior Developer", experience=[ResumeExperience(company="Infosys", role="Senior Developer")]),
    )

    assert only_match(result, "Technical Leadership").classification == "adjacent"


def test_years_of_experience_match_uses_non_overlapping_dates() -> None:
    result = match_job_to_profile(
        analysis(keyword("7+ Years of Experience", category="Experience")),
        profile(
            experience=[
                ResumeExperience(company="A", role="Developer", startDate="2016-01", endDate="2020-12"),
                ResumeExperience(company="B", role="Developer", startDate="2021-01", endDate="2024-12"),
            ]
        ),
    )

    assert only_match(result, "7+ Years of Experience").classification == "exact"


def test_overlapping_dates_count_once() -> None:
    months = calculate_non_overlapping_experience_months(
        profile(
            experience=[
                ResumeExperience(company="A", role="Developer", startDate="2020-01", endDate="2021-12"),
                ResumeExperience(company="B", role="Developer", startDate="2021-01", endDate="2022-12"),
            ]
        )
    )

    assert months == 36


def test_masters_in_computer_science_satisfies_bachelors_related_field() -> None:
    result = match_job_to_profile(
        analysis(keyword("Bachelor's Degree in Computer Science or related field", category="Education")),
        profile(education=[ResumeEducation(degree="Master of Science in Computer Science", institution="University")]),
    )

    assert only_match(result, "Bachelor's Degree in Computer Science or related field").classification == "normalized"


def test_wrong_education_field_does_not_match() -> None:
    result = match_job_to_profile(
        analysis(keyword("Bachelor's Degree in Finance", category="Education")),
        profile(education=[ResumeEducation(degree="Master of Science in Computer Science", institution="University")]),
    )

    assert only_match(result, "Bachelor's Degree in Finance").classification == "adjacent"


def test_suggested_keyword_does_not_reduce_overall_score() -> None:
    result_without_suggested = match_job_to_profile(
        analysis(keyword("C#", category="Languages")),
        profile(skills=["C#"]),
        profile_id="suggested-a",
    )
    result_with_suggested = match_job_to_profile(
        analysis(keyword("C#", category="Languages"), keyword("Kubernetes", category="DevOps", source_type="suggested", priority="low", score=20)),
        profile(skills=["C#"]),
        profile_id="suggested-b",
    )

    assert result_with_suggested.match_summary.overall_match_score == result_without_suggested.match_summary.overall_match_score
    assert only_match(result_with_suggested, "Kubernetes").classification == "unmatched"


def test_every_matched_requirement_contains_valid_evidence_id() -> None:
    candidate = profile(skills=["C#"])
    result = match_job_to_profile(analysis(keyword("C#", category="Languages")), candidate)
    valid_ids = {item.evidence_id for item in build_profile_evidence_index(candidate)}

    for match in result.match_summary.matched_requirements:
        assert match.evidence
        assert all(item.evidence_id in valid_ids for item in match.evidence)


def test_no_evidence_invention() -> None:
    candidate = profile(skills=["C#"])
    result = match_job_to_profile(analysis(keyword("Azure", category="Cloud")), candidate)
    valid_ids = {item.evidence_id for item in build_profile_evidence_index(candidate)}

    for match in [*result.match_summary.matched_requirements, *result.match_summary.partially_matched_requirements]:
        assert all(item.evidence_id in valid_ids for item in [*match.evidence, *match.adjacent_evidence])


def test_empty_profile_returns_validation_error() -> None:
    with pytest.raises(ValueError, match="Complete your profile"):
        match_job_to_profile(analysis(keyword("C#", category="Languages")), CandidateProfile(name=""))


def test_cache_version_is_exposed() -> None:
    result = match_job_to_profile(
        analysis(keyword("C#", category="Languages")),
        profile(skills=["C#"]),
        profile_id="cache-version",
    )

    assert result.cache_version == PROFILE_MATCH_CACHE_VERSION


def test_original_jd_profile_matching_safety() -> None:
    candidate = profile(
        skills=["C#", ".NET", "SQL Server", "React", "CI/CD", "Code Review"],
        experience=[
                ResumeExperience(
                    company="Infosys",
                    role="Senior .NET Developer",
                    startDate="2018-01",
                    endDate="Present",
                    rawNotes=(
                    "Built modern web technologies with .NET, SQL Server, application frameworks, "
                    "stakeholder collaboration, troubleshooting, and problem solving."
                ),
            )
        ],
        education=[ResumeEducation(degree="Bachelor of Technology in Computer Science", institution="JNTU")],
    )
    result = match_job_to_profile(
        analysis(
            keyword("C#", category="Languages"),
            keyword(".NET", category="Frameworks"),
            keyword("Databases", category="Databases", priority="medium", score=60),
            keyword("Modern Web Technologies", category="Web", priority="medium", score=60),
            keyword("Application Frameworks", category="Frameworks", priority="medium", score=60),
            keyword("CI/CD", category="DevOps", priority="medium", score=60),
            keyword("Code Review", category="Review", priority="medium", score=60),
            keyword("Stakeholder Collaboration", category="Collaboration", priority="medium", score=60),
            keyword("Troubleshooting", category="Support", priority="medium", score=60),
            keyword("Problem Solving", category="Support", priority="medium", score=60),
            keyword("Bachelor's Degree", category="Education"),
            keyword("7+ Years of Experience", category="Experience"),
            keyword("Python", category="Languages"),
            keyword("Financial Services", category="Domain"),
            keyword("Trading", category="Domain"),
            keyword("Technical Leadership", category="Leadership"),
        ),
        candidate,
    )

    matched = {item.requirement_value for item in result.match_summary.matched_requirements}
    unmatched = {item.requirement_value for item in result.match_summary.unmatched_requirements}
    adjacent = {item.requirement_value for item in result.match_summary.partially_matched_requirements}

    assert {"C#", ".NET", "Databases", "Modern Web Technologies", "Application Frameworks", "CI/CD", "Code Review", "Bachelor's Degree", "7+ Years of Experience"} <= matched
    assert {"Python", "Financial Services", "Trading"} <= unmatched
    assert "Technical Leadership" in adjacent
