from types import SimpleNamespace

from app.schemas.resume import (
    CandidateProfile,
    GenerateResumeRequest,
    JobAnalysisResponse,
    JobKeywordAnalysisItem,
    ResumeContact,
    ResumeExperience,
    SkillCategory,
)
from app.services.profile_service import compute_profile_content_hash, ensure_profile_record_ids
from app.services.resume_generation_pipeline import (
    assemble_structured_resume,
    build_generation_context,
    build_generation_response,
    evidence_aware_ats_coverage,
    select_relevant_profile_evidence,
    structured_to_resume_content,
)
from app.services.resume_validator import validate_structured_resume


PROFILE_ID = "11111111-1111-1111-1111-111111111111"


def keyword(value: str, *, category: str = "Responsibility", source_type: str = "explicit") -> JobKeywordAnalysisItem:
    return JobKeywordAnalysisItem(
        id=f"keyword-{abs(hash((value, source_type)))}",
        value=value,
        normalizedValue=value,
        category=category,
        sourceType=source_type,
        confidence="high" if source_type == "explicit" else "low",
        priority="high" if source_type == "explicit" else "low",
        priorityScore=90 if source_type == "explicit" else 20,
        directFromJD=source_type == "explicit",
        evidenceText=value if source_type == "explicit" else "",
        sourceSentence=value if source_type == "explicit" else "",
        occurrenceCount=1,
    )


def analysis(*items: JobKeywordAnalysisItem) -> JobAnalysisResponse:
    return JobAnalysisResponse(
        roleInformation={"title": "Software Engineer", "seniority": "Senior"},
        keywords=list(items),
        suggestedKeywords=[item for item in items if item.source_type == "suggested"],
        analysisHash=f"phase-4a-{abs(hash(tuple(item.value for item in items)))}",
    )


def candidate_with_evidence(
    *evidence: str,
    skills: list[str] | None = None,
    company: str = "Company",
    role: str = "Developer",
) -> CandidateProfile:
    return ensure_profile_record_ids(
        CandidateProfile(
            name="Test Candidate",
            title="Senior .NET Developer",
            contact=ResumeContact(email="test@example.com", phone="+12015550100", location="Hartford, CT"),
            skills=[SkillCategory(category="Technical Skills", items=skills or [])],
            experience=[
                ResumeExperience(
                    company=company,
                    role=role,
                    startDate="2022-01",
                    endDate="Present",
                    rawNotes=item,
                )
                for item in evidence
            ],
        )
    )


def profile_record(profile: CandidateProfile):
    return SimpleNamespace(
        profile_id=PROFILE_ID,
        profile_version=1,
        content_hash=compute_profile_content_hash(profile),
        updated_at="2026-07-17T00:00:00+00:00",
        profile_data=profile,
    )


def run_pipeline(
    requirement: str,
    profile: CandidateProfile,
    *,
    source_type: str = "explicit",
    job_description: str | None = None,
):
    item = keyword(requirement, source_type=source_type)
    job_analysis = analysis(item)
    payload = GenerateResumeRequest(
        profileId=PROFILE_ID,
        job_description=job_description or requirement,
        target_role="Software Engineer",
        target_company="Target",
        jobAnalysis=job_analysis,
    )
    context = build_generation_context(profile_record(profile), payload, job_analysis)
    selected = select_relevant_profile_evidence(context)
    structured = assemble_structured_resume(profile, payload, context, selected)
    validation = validate_structured_resume(structured, context.evidence_index, context.profile_match)
    resume = structured_to_resume_content(profile, structured)
    response = build_generation_response(profile, payload, context, structured, validation)
    return SimpleNamespace(
        item=item,
        payload=payload,
        job_analysis=job_analysis,
        context=context,
        selected=selected,
        structured=structured,
        validation=validation,
        resume=resume,
        response=response,
    )


def only_requirement(result, value: str):
    matches = [
        *result.context.profile_match.matched_requirements,
        *result.context.profile_match.partially_matched_requirements,
        *result.context.profile_match.unmatched_requirements,
    ]
    return next(match for match in matches if match.requirement_value == value)


def experience_section(result):
    return next(section for section in result.structured.sections if section.type == "experience")


def first_bullet(result) -> dict:
    return experience_section(result).content[0]["bullets"][0]


def all_bullets(result) -> list[str]:
    return [bullet for role in result.resume.experience for bullet in role.bullets]


def joined_bullets(result) -> str:
    return " ".join(all_bullets(result)).lower()


def assert_valid_section_provenance(result) -> None:
    evidence_ids = {item.evidence_id for item in result.context.evidence_index}
    requirement_ids = {
        match.requirement_id
        for match in [
            *result.context.profile_match.matched_requirements,
            *result.context.profile_match.partially_matched_requirements,
            *result.context.profile_match.unmatched_requirements,
        ]
    }
    for section in result.structured.sections:
        assert set(section.provenance.supporting_evidence_ids) <= evidence_ids
        assert set(section.provenance.supported_requirement_ids) <= requirement_ids


def test_production_support_semantic_match_reaches_generation() -> None:
    result = run_pipeline(
        "Troubleshoot production incidents and resolve application defects.",
        candidate_with_evidence(
            "Analyzed support tickets, application failures, database errors, and logs to identify root causes and implement production fixes."
        ),
    )
    match = only_requirement(result, "Troubleshoot production incidents and resolve application defects.")
    section = experience_section(result)

    assert match.classification == "normalized"
    assert match.evidence
    assert match.evidence[0].evidence_id in section.provenance.supporting_evidence_ids
    assert match.requirement_id in section.provenance.supported_requirement_ids
    assert "production fixes" in joined_bullets(result)
    assert "30%" not in joined_bullets(result)
    assert result.validation.is_valid is True
    assert_valid_section_provenance(result)


def test_api_development_semantic_match_stays_evidence_grounded() -> None:
    result = run_pipeline(
        "Design and develop REST-based backend services.",
        candidate_with_evidence("Built ASP.NET Core Web APIs using C# and Entity Framework Core."),
    )
    text = joined_bullets(result)

    assert only_requirement(result, "Design and develop REST-based backend services.").classification == "normalized"
    assert "asp.net core web apis" in text
    assert "c#" in text
    assert "entity framework core" in text
    assert "microservices" not in text
    assert "kubernetes" not in text
    assert "azure api management" not in text
    assert "event-driven" not in text
    assert result.validation.is_valid is True


def test_database_optimization_generation_does_not_add_metric_or_architecture() -> None:
    result = run_pipeline(
        "Optimize database queries and stored procedures.",
        candidate_with_evidence("Developed T-SQL stored procedures and tuned SQL Server queries."),
    )
    text = joined_bullets(result)

    assert "stored procedures" in text
    assert "sql server queries" in text
    assert "%" not in text
    assert "database architecture" not in text
    assert result.validation.is_valid is True


def test_collaboration_generation_does_not_escalate_to_leadership() -> None:
    result = run_pipeline(
        "Collaborate with product owners, QA, infrastructure, and engineering teams.",
        candidate_with_evidence("Worked with QA, business analysts, product owners, and deployment teams."),
    )
    text = joined_bullets(result)

    assert "product owners" in text
    assert "qa" in text
    assert not any(term in text for term in ("led ", "managed", "mentored", "directed", "owned", "supervised"))
    assert result.validation.is_valid is True


def test_application_maintenance_generation_does_not_claim_architecture() -> None:
    result = run_pipeline(
        "Maintain and enhance enterprise applications.",
        candidate_with_evidence("Supported and enhanced existing provider-facing applications."),
    )
    text = joined_bullets(result)

    assert "supported and enhanced" in text
    assert "architecture ownership" not in text
    assert "greenfield" not in text
    assert "system design" not in text
    assert result.validation.is_valid is True


def test_healthcare_domain_generation_does_not_infer_products_or_standards() -> None:
    result = run_pipeline(
        "Support healthcare claims and provider applications.",
        candidate_with_evidence("Resolved provider matching, authorization, and claims-status issues for a healthcare client."),
    )
    text = joined_bullets(result)

    assert "claims-status" in text or "claims status" in text
    assert "provider" in text
    assert "authorization" in text
    assert not any(term in text for term in ("epic bridges", "hl7", "fhir", "claims architecture"))
    assert result.validation.is_valid is True


def test_adjacent_react_requirement_is_excluded_from_resume_safe_generation() -> None:
    result = run_pipeline("React", candidate_with_evidence(skills=["Angular"]))

    match = only_requirement(result, "React")
    skills = [skill for group in result.resume.skills for skill in group.items]

    assert match.classification in {"adjacent", "unmatched"}
    assert match.is_safe_to_use is False
    assert "React" not in skills
    assert all(match.requirement_id not in section.provenance.supported_requirement_ids for section in result.structured.sections)


def test_suggested_keyword_does_not_create_requirement_or_bullet() -> None:
    result = run_pipeline("Kubernetes", candidate_with_evidence(skills=["Kubernetes"]), source_type="suggested")

    assert result.context.profile_match.matched_requirements == []
    assert result.context.profile_match.partially_matched_requirements == []
    assert result.context.profile_match.unmatched_requirements == []
    assert "kubernetes" not in joined_bullets(result)
    assert result.context.profile_match.overall_match_score == 0


def test_unsupported_metric_requirement_is_not_counted_or_generated() -> None:
    result = run_pipeline(
        "Improve performance by 30%",
        candidate_with_evidence("Optimized SQL queries."),
    )
    match = only_requirement(result, "Improve performance by 30%")

    assert match.classification == "unmatched"
    assert match.is_safe_to_use is False
    assert "30%" not in joined_bullets(result)
    assert result.context.profile_match.overall_match_score == 0


def test_compound_react_api_relationship_is_not_inferred_from_separate_evidence() -> None:
    result = run_pipeline(
        "Build React interfaces integrated with ASP.NET Core APIs.",
        candidate_with_evidence("Developed React user interfaces.", "Built ASP.NET Core Web APIs."),
    )
    match = only_requirement(result, "Build React interfaces integrated with ASP.NET Core APIs.")
    text = joined_bullets(result)

    assert match.classification == "unmatched"
    assert match.is_safe_to_use is False
    assert "integrated with asp.net core" not in text


def test_structured_resume_provenance_survives_json_roundtrip_and_version_copy() -> None:
    result = run_pipeline(
        "Design and develop REST-based backend services.",
        candidate_with_evidence("Built ASP.NET Core Web APIs using C# and Entity Framework Core."),
    )
    restored = result.structured.__class__.model_validate(result.structured.model_dump(mode="json", by_alias=True))
    version = restored.model_copy(update={"version_number": 2})

    assert restored.sections[0].provenance == result.structured.sections[0].provenance
    assert version.sections[0].provenance == result.structured.sections[0].provenance


def test_generated_bullets_have_required_bullet_level_provenance_shape() -> None:
    result = run_pipeline(
        "Troubleshoot production incidents and resolve application defects.",
        candidate_with_evidence("Analyzed support tickets, application failures, database errors, and logs to identify root causes and implement production fixes."),
    )
    bullet = experience_section(result).content[0]["bullets"][0]

    assert isinstance(bullet, dict)
    assert {
        "bulletId",
        "order",
        "generatedText",
        "currentText",
        "userEdited",
        "supportedRequirementIds",
        "supportingEvidenceIds",
        "validationStatus",
        "warnings",
    } <= set(bullet)
    assert bullet["supportingEvidenceIds"]
    assert bullet["currentText"] == bullet["generatedText"]
    assert bullet["userEdited"] is False
    assert bullet["validationStatus"] == "validated"


def test_generated_bullet_order_is_stable() -> None:
    result = run_pipeline(
        "Troubleshoot production incidents and resolve application defects.",
        candidate_with_evidence(
            "Analyzed support tickets, application failures, database errors, and logs to identify root causes and implement production fixes.",
            "Resolved application defects across release validation workflows.",
        ),
    )
    bullets = experience_section(result).content[0]["bullets"]

    assert [bullet["order"] for bullet in bullets] == list(range(1, len(bullets) + 1))
    assert [bullet["bulletId"] for bullet in bullets] == [bullet["bulletId"] for bullet in experience_section(result).content[0]["bullets"]]


def test_safe_user_edit_remains_validated() -> None:
    result = run_pipeline(
        "Design and develop REST-based backend services.",
        candidate_with_evidence("Built ASP.NET Core Web APIs using C# and Entity Framework Core."),
    )
    bullet = first_bullet(result)
    bullet["currentText"] = "Built ASP.NET Core Web APIs using C#."
    validation = validate_structured_resume(result.structured, result.context.evidence_index, result.context.profile_match)

    assert validation.is_valid is True
    assert first_bullet(result)["userEdited"] is True
    assert first_bullet(result)["validationStatus"] == "validated"


def assert_edit_rejected(result, edited_text: str, expected_code: str) -> None:
    bullet = first_bullet(result)
    generated = bullet["generatedText"]
    bullet["currentText"] = edited_text
    validation = validate_structured_resume(result.structured, result.context.evidence_index, result.context.profile_match)

    assert validation.is_valid is False
    assert first_bullet(result)["currentText"] == edited_text
    assert first_bullet(result)["generatedText"] == generated
    assert first_bullet(result)["userEdited"] is True
    assert first_bullet(result)["validationStatus"] == "rejected"
    assert any(issue.code == expected_code for issue in validation.errors)


def test_metric_escalation_is_rejected() -> None:
    result = run_pipeline(
        "Optimize database queries and stored procedures.",
        candidate_with_evidence("Developed T-SQL stored procedures and tuned SQL Server queries."),
    )
    assert_edit_rejected(result, "Improved database performance by 40%.", "unsupported_metric")


def test_architecture_escalation_is_rejected() -> None:
    result = run_pipeline(
        "Maintain and enhance enterprise applications.",
        candidate_with_evidence("Supported and enhanced existing provider-facing applications."),
    )
    assert_edit_rejected(result, "Architected greenfield enterprise system design.", "unsupported_architecture_claim")


def test_product_or_certification_escalation_is_rejected() -> None:
    result = run_pipeline(
        "Support healthcare claims and provider applications.",
        candidate_with_evidence("Resolved provider matching, authorization, and claims-status issues for a healthcare client."),
    )
    assert_edit_rejected(result, "Implemented Epic Bridges integrations.", "unsupported_product_or_certification")


def test_compound_integration_edit_is_rejected() -> None:
    result = run_pipeline(
        "Design and develop REST-based backend services.",
        candidate_with_evidence("Built ASP.NET Core Web APIs using C# and Entity Framework Core."),
    )
    assert_edit_rejected(result, "Built React interfaces integrated with ASP.NET Core APIs.", "unsupported_technology_claim")


def test_unsupported_technology_insertion_is_rejected() -> None:
    result = run_pipeline(
        "Design and develop REST-based backend services.",
        candidate_with_evidence("Built ASP.NET Core Web APIs using C# and Entity Framework Core."),
    )
    assert_edit_rejected(result, "Built Kubernetes services for Azure API Management.", "unsupported_technology_claim")


def test_user_edited_bullet_with_unsupported_claim_is_rejected_per_bullet() -> None:
    result = run_pipeline(
        "Design and develop REST-based backend services.",
        candidate_with_evidence("Built ASP.NET Core Web APIs using C# and Entity Framework Core."),
    )
    edited = result.structured.model_copy(deep=True)
    exp_section = next(section for section in edited.sections if section.type == "experience")
    exp_section.content[0]["bullets"][0]["currentText"] = "Managed Kubernetes microservices architecture for Azure API Management."
    validation = validate_structured_resume(edited, result.context.evidence_index, result.context.profile_match)
    exp_section = next(section for section in edited.sections if section.type == "experience")

    assert validation.is_valid is False
    assert exp_section.content[0]["bullets"][0]["currentText"] == "Managed Kubernetes microservices architecture for Azure API Management."
    assert exp_section.content[0]["bullets"][0]["generatedText"] != exp_section.content[0]["bullets"][0]["currentText"]
    assert exp_section.content[0]["bullets"][0]["userEdited"] is True
    assert exp_section.content[0]["bullets"][0]["validationStatus"] == "rejected"
    assert any(issue.code in {"unsupported_leadership_claim", "unsupported_architecture_claim", "unsupported_technology_claim"} for issue in validation.errors)


def test_ats_breakdown_distinguishes_supported_adjacent_unmatched_and_suggested() -> None:
    result = run_pipeline("React", candidate_with_evidence(skills=["Angular"]))

    assert "supportedAndCovered" in result.response.breakdown.coverage
    assert "adjacentUnsupported" in result.response.breakdown.coverage
    assert "suggestedExcluded" in result.response.breakdown.coverage


def test_ats_supported_and_represented_enters_supported_and_covered() -> None:
    result = run_pipeline(
        "Design and develop REST-based backend services.",
        candidate_with_evidence("Built ASP.NET Core Web APIs using C# and Entity Framework Core."),
    )

    assert result.response.breakdown.coverage["supportedAndCovered"]


def test_ats_supported_but_unused_enters_supported_but_not_represented_after_rejected_edit() -> None:
    result = run_pipeline(
        "Design and develop REST-based backend services.",
        candidate_with_evidence("Built ASP.NET Core Web APIs using C# and Entity Framework Core."),
    )
    first_bullet(result)["currentText"] = "Managed Kubernetes microservices architecture."
    validate_structured_resume(result.structured, result.context.evidence_index, result.context.profile_match)
    coverage = evidence_aware_ats_coverage(result.structured, result.context)

    assert coverage["supportedButNotRepresented"]
    assert not coverage["supportedAndCovered"]


def test_ats_adjacent_requirement_enters_adjacent_unsupported() -> None:
    result = run_pipeline("Azure", candidate_with_evidence(skills=["AWS"]))

    assert result.response.breakdown.coverage["adjacentUnsupported"]
    assert not result.response.breakdown.coverage["supportedAndCovered"]


def test_ats_unmatched_requirement_enters_unmatched() -> None:
    result = run_pipeline("React", candidate_with_evidence(skills=["C#"]))

    assert result.response.breakdown.coverage["unmatched"]
    assert not result.response.breakdown.coverage["supportedAndCovered"]


def test_ats_suggested_requirement_enters_suggested_excluded() -> None:
    result = run_pipeline("Kubernetes", candidate_with_evidence(skills=["Kubernetes"]), source_type="suggested")

    assert result.response.breakdown.coverage["suggestedExcluded"]
    assert not result.response.breakdown.coverage["supportedAndCovered"]


def test_keyword_insertion_without_evidence_does_not_increase_supported_coverage() -> None:
    result = run_pipeline("React", candidate_with_evidence(skills=["Angular"]))
    before = len(result.response.breakdown.coverage["supportedAndCovered"])
    if result.structured.sections:
        result.structured.sections[0].content = f"{result.structured.sections[0].content} React"
    coverage = evidence_aware_ats_coverage(result.structured, result.context)

    assert len(coverage["supportedAndCovered"]) == before


def test_another_valid_bullet_keeps_requirement_covered_after_one_rejected_edit() -> None:
    result = run_pipeline(
        "Troubleshoot production incidents and resolve application defects.",
        candidate_with_evidence(
            "Analyzed support tickets, application failures, database errors, and logs to identify root causes and implement production fixes.",
            "Resolved application defects across release validation workflows.",
        ),
    )
    bullets = experience_section(result).content[0]["bullets"]
    bullets[0]["currentText"] = "Managed Kubernetes microservices architecture."
    validate_structured_resume(result.structured, result.context.evidence_index, result.context.profile_match)
    coverage = evidence_aware_ats_coverage(result.structured, result.context)

    assert coverage["supportedAndCovered"]


def test_legacy_string_bullet_normalizes_without_false_validation() -> None:
    result = run_pipeline(
        "Design and develop REST-based backend services.",
        candidate_with_evidence("Built ASP.NET Core Web APIs using C# and Entity Framework Core."),
    )
    exp_section = experience_section(result)
    exp_section.content[0]["bullets"] = ["Legacy plain text bullet."]
    validation = validate_structured_resume(result.structured, result.context.evidence_index, result.context.profile_match)
    bullet = experience_section(result).content[0]["bullets"][0]

    assert validation.is_valid is True
    assert bullet["currentText"] == "Legacy plain text bullet."
    assert bullet["validationStatus"] == "warning"
    assert bullet["supportingEvidenceIds"] == []
    assert bullet["userEdited"] is True
    assert bullet["warnings"]
