from app.schemas.resume import (
    CandidateProfile,
    JobAnalysisResponse,
    JobKeywordAnalysisItem,
    ResumeContact,
    ResumeExperience,
    SkillCategory,
)
from app.services.profile_matching import match_job_to_profile


def keyword(value: str, *, priority: str = "high", score: int = 90) -> JobKeywordAnalysisItem:
    return JobKeywordAnalysisItem(
        id=f"keyword-{abs(hash(value))}",
        value=value,
        normalizedValue=value,
        category="Responsibility",
        sourceType="explicit",
        confidence="high",
        priority=priority,
        priorityScore=score,
        directFromJD=True,
        evidenceText=value,
        sourceSentence=value,
        occurrenceCount=1,
    )


def analysis(requirement: str, *, priority: str = "high", score: int = 90) -> JobAnalysisResponse:
    return JobAnalysisResponse(
        roleInformation={"title": "Software Engineer", "seniority": "Senior"},
        keywords=[keyword(requirement, priority=priority, score=score)],
        analysisHash=f"responsibility-audit-{abs(hash(requirement))}",
    )


def profile_with_evidence(*evidence: str, skills: list[str] | None = None) -> CandidateProfile:
    experiences = [
        ResumeExperience(
            experienceId=f"exp-{index}",
            company="Company",
            role="Developer",
            rawNotes=item,
        )
        for index, item in enumerate(evidence)
    ]
    return CandidateProfile(
        name="Test Candidate",
        title="Senior .NET Developer",
        contact=ResumeContact(email="test@example.com"),
        skills=[SkillCategory(category="Technical Skills", items=skills or [])],
        experience=experiences,
    )


def requirement_result(requirement: str, candidate: CandidateProfile):
    result = match_job_to_profile(analysis(requirement), candidate)
    matches = [
        *result.match_summary.matched_requirements,
        *result.match_summary.partially_matched_requirements,
        *result.match_summary.unmatched_requirements,
    ]
    return next(item for item in matches if item.requirement_value == requirement)


def audit_payload(requirement: str, candidate: CandidateProfile) -> dict:
    match = requirement_result(requirement, candidate)
    evidence = match.evidence or match.adjacent_evidence
    return {
        "extracted_requirement": requirement,
        "normalized_requirement": match.requirement_value,
        "profile_evidence_selected": [item.original_text for item in evidence],
        "classification": str(match.classification.value),
        "matched": bool(match.evidence),
        "confidence": match.match_score,
        "supportingEvidenceIds": [item.evidence_id for item in match.evidence],
        "resumeSafe": match.is_safe_to_use,
        "explanation": match.reason,
    }


def assert_matched_semantic(requirement: str, candidate: CandidateProfile) -> None:
    payload = audit_payload(requirement, candidate)
    assert payload["matched"] is True, payload
    assert payload["classification"] in {"exact", "normalized"}, payload
    assert payload["supportingEvidenceIds"], payload
    assert payload["resumeSafe"] is True, payload


def assert_not_resume_safe(requirement: str, candidate: CandidateProfile) -> None:
    payload = audit_payload(requirement, candidate)
    assert payload["classification"] in {"adjacent", "unmatched"}, payload
    assert payload["resumeSafe"] is False, payload


def test_production_support_sentence_semantics() -> None:
    payload = audit_payload(
        "Troubleshoot production incidents and resolve application defects.",
        profile_with_evidence(
            "Analyzed support tickets, application failures, database errors, and logs to identify root causes and implement production fixes."
        ),
    )
    assert payload["matched"] is True, payload
    assert payload["classification"] == "normalized", payload
    assert payload["supportingEvidenceIds"], payload
    assert payload["resumeSafe"] is True, payload
    assert "production issue resolution" in payload["explanation"], payload
    assert "root-cause analysis" in payload["explanation"], payload


def test_api_development_sentence_semantics() -> None:
    assert_matched_semantic(
        "Design and develop REST-based backend services.",
        profile_with_evidence("Built ASP.NET Core Web APIs using C# and Entity Framework Core."),
    )


def test_database_optimization_sentence_semantics() -> None:
    assert_matched_semantic(
        "Optimize database queries, stored procedures, and application performance.",
        profile_with_evidence("Developed T-SQL stored procedures and tuned SQL Server queries to improve application performance."),
    )


def test_cross_functional_collaboration_sentence_semantics() -> None:
    assert_matched_semantic(
        "Collaborate with product owners, QA, infrastructure, and engineering teams.",
        profile_with_evidence("Worked with QA, business analysts, product owners, and deployment teams to resolve defects and deliver releases."),
    )


def test_documentation_sentence_semantics() -> None:
    assert_matched_semantic(
        "Document system functionality, technical changes, and support procedures.",
        profile_with_evidence("Created technical documentation, troubleshooting notes, API references, and implementation guides."),
    )


def test_application_maintenance_sentence_semantics() -> None:
    assert_matched_semantic(
        "Maintain and enhance existing enterprise applications.",
        profile_with_evidence("Supported and enhanced existing provider-facing applications built with C#, .NET, React, and SQL Server."),
    )


def test_architecture_overclaim_protection() -> None:
    assert_not_resume_safe(
        "Architect enterprise platforms and define system-wide technical strategy.",
        profile_with_evidence("Maintained and enhanced existing enterprise applications."),
    )


def test_leadership_overclaim_protection() -> None:
    assert_not_resume_safe(
        "Lead engineering teams and mentor developers.",
        profile_with_evidence("Collaborated with developers, QA, and product owners."),
    )


def test_ownership_overclaim_protection() -> None:
    assert_not_resume_safe(
        "Own the complete software delivery lifecycle.",
        profile_with_evidence("Contributed to development, testing, and production support activities."),
    )


def test_metric_protection_keeps_numeric_target_unsupported() -> None:
    assert_not_resume_safe(
        "Improved application performance by at least 30%.",
        profile_with_evidence("Optimized SQL queries and stored procedures."),
    )


def test_domain_meaning_sentence_semantics() -> None:
    assert_matched_semantic(
        "Experience supporting healthcare claims and provider applications.",
        profile_with_evidence("Resolved provider matching, authorization, and claims-status issues for a healthcare client."),
    )


def test_specific_product_protection() -> None:
    assert_not_resume_safe(
        "Epic Bridges integration experience.",
        profile_with_evidence("Supported healthcare claims applications."),
    )


def test_compound_requirement_does_not_infer_integration_from_separate_evidence() -> None:
    assert_not_resume_safe(
        "Build React user interfaces integrated with ASP.NET Core APIs.",
        profile_with_evidence("Developed React user interfaces.", "Built ASP.NET Core Web APIs."),
    )


def test_api_development_does_not_imply_microservices_architecture() -> None:
    assert_not_resume_safe(
        "Design microservices architecture for distributed systems.",
        profile_with_evidence("Built ASP.NET Core Web APIs using C# and Entity Framework Core."),
    )


def test_sql_query_tuning_does_not_imply_database_architecture() -> None:
    assert_not_resume_safe(
        "Define database architecture for enterprise platforms.",
        profile_with_evidence("Developed T-SQL stored procedures and tuned SQL Server queries to improve application performance."),
    )


def test_documentation_does_not_imply_documentation_leadership() -> None:
    assert_not_resume_safe(
        "Lead technical writing and documentation strategy.",
        profile_with_evidence("Created technical documentation, troubleshooting notes, API references, and implementation guides."),
    )


def test_suggested_terms_remain_excluded_from_profile_matching() -> None:
    result = match_job_to_profile(
        JobAnalysisResponse(
            roleInformation={"title": "Engineer"},
            suggestedKeywords=[
                JobKeywordAnalysisItem(
                    id="suggested-docker",
                    value="Docker",
                    normalizedValue="Docker",
                    category="DevOps",
                    sourceType="suggested",
                    confidence="high",
                    priority="low",
                    priorityScore=30,
                    directFromJD=False,
                    evidenceText="",
                    sourceSentence="",
                    occurrenceCount=1,
                )
            ],
            analysisHash="suggested-keyword-audit",
        ),
        profile_with_evidence(skills=["Docker"]),
    )

    assert result.match_summary.matched_requirements == []
    assert result.match_summary.partially_matched_requirements == []
    assert result.match_summary.unmatched_requirements == []


def test_root_cause_analysis_sentence_semantics() -> None:
    assert_matched_semantic(
        "Perform root-cause analysis for recurring production issues.",
        profile_with_evidence("Analyzed support tickets, application failures, database errors, and logs to identify root causes and implement production fixes."),
    )


def test_rest_api_development_sentence_semantics() -> None:
    assert_matched_semantic(
        "Build REST API services for application integrations.",
        profile_with_evidence("Built ASP.NET Core Web APIs using C# and Entity Framework Core."),
    )


def test_backend_service_development_sentence_semantics() -> None:
    assert_matched_semantic(
        "Develop backend services for enterprise applications.",
        profile_with_evidence("Built ASP.NET Core Web APIs using C# and Entity Framework Core."),
    )


def test_sql_query_tuning_sentence_semantics() -> None:
    assert_matched_semantic(
        "Tune SQL queries to improve application performance.",
        profile_with_evidence("Developed T-SQL stored procedures and tuned SQL Server queries to improve application performance."),
    )


def test_stored_procedure_development_sentence_semantics() -> None:
    assert_matched_semantic(
        "Develop stored procedures for database workflows.",
        profile_with_evidence("Developed T-SQL stored procedures and tuned SQL Server queries to improve application performance."),
    )


def test_application_maintenance_and_enhancement_sentence_semantics() -> None:
    assert_matched_semantic(
        "Perform application maintenance and enhancement work.",
        profile_with_evidence("Supported and enhanced existing provider-facing applications built with C#, .NET, React, and SQL Server."),
    )


def test_negated_responsibility_does_not_create_required_match_when_not_extracted() -> None:
    result = match_job_to_profile(
        JobAnalysisResponse(
            roleInformation={"title": "Engineer"},
            keywords=[],
            analysisHash="negated-kubernetes-audit",
        ),
        profile_with_evidence(skills=["Kubernetes"]),
    )

    assert result.match_summary.matched_requirements == []
    assert result.match_summary.partially_matched_requirements == []
    assert result.match_summary.unmatched_requirements == []


def test_preferred_qualification_is_low_priority_when_extracted_as_preferred() -> None:
    result = match_job_to_profile(
        analysis("Docker", priority="low", score=30),
        profile_with_evidence(skills=["Docker"]),
    )
    match = result.match_summary.matched_requirements[0]

    assert match.requirement_value == "Docker"
    assert match.requirement_priority == "low"
    assert match.is_safe_to_use is True
