from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
from uuid import UUID

import pytest
from docx import Document
from pypdf import PdfReader

from app.api.routes import resumes as resumes_route
from app.schemas.resume import (
    CandidateProfile,
    GenerateResumeRequest,
    JobAnalysisResponse,
    JobKeywordAnalysisItem,
    ProfileMatchSummary,
    ResumeContact,
    ResumeExperience,
    SkillCategory,
    StructuredGeneratedResume,
    StructuredResumeRecord,
)
from app.services.export import ExportFormat, export_resume_record
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
from app.services.structured_bullets import normalize_structured_resume_bullets


USER_ID = "11111111-1111-1111-1111-111111111111"
PROFILE_ID = "22222222-2222-2222-2222-222222222222"
PERSISTED_RESUME_ID = "33333333-3333-3333-3333-333333333333"


def keyword(value: str, *, source_type: str = "explicit") -> JobKeywordAnalysisItem:
    return JobKeywordAnalysisItem(
        id=f"req-{value.lower().replace(' ', '-').replace('#', 'sharp').replace('/', '-')}",
        value=value,
        normalizedValue=value,
        category="Technical",
        sourceType=source_type,
        confidence="high" if source_type == "explicit" else "low",
        priority="high" if source_type == "explicit" else "low",
        priorityScore=90 if source_type == "explicit" else 15,
        directFromJD=source_type == "explicit",
        evidenceText=value if source_type == "explicit" else "",
        sourceSentence=value if source_type == "explicit" else "",
        occurrenceCount=1,
    )


def job_analysis(*items: JobKeywordAnalysisItem) -> JobAnalysisResponse:
    return JobAnalysisResponse(
        roleInformation={"title": "Software Engineer", "seniority": "Senior"},
        keywords=list(items),
        suggestedKeywords=[item for item in items if item.source_type == "suggested"],
        analysisHash="phase-5a-contract-analysis",
    )


def profile(*notes: str, skills: list[str] | None = None) -> CandidateProfile:
    return ensure_profile_record_ids(
        CandidateProfile(
            name="Venu Madhav Pendurthi",
            title="Senior .NET Developer",
            contact=ResumeContact(email="venu@example.com", phone="+12014436937", location="Hartford, CT"),
            skills=[SkillCategory(category="Technical Skills", items=skills or [])],
            experience=[
                ResumeExperience(
                    company="Infosys",
                    role="Senior .NET Developer",
                    location="Hartford, CT",
                    startDate="2025-01",
                    endDate="Present",
                    rawNotes=note,
                )
                for note in notes
            ],
        )
    )


def profile_record(candidate: CandidateProfile):
    return SimpleNamespace(
        profile_id=PROFILE_ID,
        profile_version=7,
        content_hash=compute_profile_content_hash(candidate),
        updated_at="2026-07-17T00:00:00+00:00",
        profile_data=candidate,
    )


def run_pipeline(*, requirement: str = "C#", candidate: CandidateProfile | None = None, source_type: str = "explicit"):
    candidate = candidate or profile("Built C# and ASP.NET Core REST API enhancements with SQL Server for enterprise delivery.")
    analysis = job_analysis(keyword(requirement, source_type=source_type))
    payload = GenerateResumeRequest(
        profileId=PROFILE_ID,
        job_description=requirement,
        target_role="Software Engineer IV",
        target_company="Velera",
        jobAnalysis=analysis,
    )
    record = profile_record(candidate)
    context = build_generation_context(record, payload, analysis)
    selected = select_relevant_profile_evidence(context)
    structured = assemble_structured_resume(candidate, payload, context, selected)
    validation = validate_structured_resume(structured, context.evidence_index, context.profile_match)
    response = build_generation_response(candidate, payload, context, structured, validation)
    return SimpleNamespace(candidate=candidate, analysis=analysis, payload=payload, context=context, structured=structured, validation=validation, response=response)


def experience_bullets(resume: StructuredGeneratedResume) -> list[dict]:
    section = next(section for section in resume.sections if section.type == "experience")
    return section.content[0]["bullets"]


def first_bullet(resume: StructuredGeneratedResume) -> dict:
    return experience_bullets(resume)[0]


def record_for(resume: StructuredGeneratedResume, context=None) -> StructuredResumeRecord:
    return StructuredResumeRecord(
        resumeId=resume.resume_id or PERSISTED_RESUME_ID,
        userId=USER_ID,
        profileId=PROFILE_ID,
        profileVersion=resume.profile_version,
        profileContentHash=resume.profile_content_hash,
        resumeName=resume.resume_name,
        targetJobTitle=resume.target_job_title,
        targetCompany=resume.target_company,
        jobDescription=resume.job_description,
        jobAnalysisJson={},
        profileMatchJson=(context.profile_match if context else ProfileMatchSummary()).model_dump(mode="json", by_alias=True),
        resumeJson=resume,
        templateId=resume.template_id,
        matchScore=resume.match_score,
        generationAlgorithmVersion=resume.generation_algorithm_version,
        status=resume.status,
        versionNumber=resume.version_number,
        parentResumeId="",
        createdAt=resume.created_at,
        updatedAt=resume.updated_at,
    )


def pdf_text(content: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)


def docx_text(content: bytes) -> str:
    document = Document(BytesIO(content))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


@pytest.mark.asyncio
async def test_generate_route_response_contract_uses_persisted_structured_resume(monkeypatch) -> None:
    candidate = profile("Built C# and ASP.NET Core REST API enhancements with SQL Server for enterprise delivery.")
    profile_rec = profile_record(candidate)
    captured = {}

    async def fake_get_profile(_session, _user_id, _profile_id):
        return profile_rec

    async def fake_create_generated_resume(_session, user_id, structured, job_analysis_json, profile_match_json):
        persisted = structured.model_copy(update={"resume_id": PERSISTED_RESUME_ID, "user_id": str(user_id)})
        captured["structured"] = persisted
        captured["job_analysis_json"] = job_analysis_json
        captured["profile_match_json"] = profile_match_json
        return record_for(persisted, SimpleNamespace(profile_match=ProfileMatchSummary.model_validate(profile_match_json)))

    monkeypatch.setattr(resumes_route.profile_service, "get_profile", fake_get_profile)
    monkeypatch.setattr(resumes_route, "create_generated_resume", fake_create_generated_resume)

    response = await resumes_route.create_resume(
        GenerateResumeRequest(
            profileId=PROFILE_ID,
            job_description="C#",
            target_role="Software Engineer IV",
            target_company="Velera",
            jobAnalysis=job_analysis(keyword("C#")),
        ),
        session=object(),
        user_id=UUID(USER_ID),
    )

    payload = response.model_dump(mode="json", by_alias=True)
    assert payload["persistedResumeId"] == PERSISTED_RESUME_ID
    assert payload["structuredResume"] == captured["structured"].model_dump(mode="json", by_alias=True)
    assert payload["structuredResume"]["resumeId"] == PERSISTED_RESUME_ID
    assert payload["validationResult"]["isValid"] is True
    assert set(payload["breakdown"]["coverage"]) == {
        "supportedAndCovered",
        "supportedButNotRepresented",
        "adjacentUnsupported",
        "unmatched",
        "suggestedExcluded",
    }
    assert "resume" in payload  # Current compatibility duplicate: flattened legacy content remains in the response.


def test_generated_bullets_satisfy_structured_output_contract() -> None:
    result = run_pipeline()
    bullets = experience_bullets(result.structured)
    requirement_ids = {match.requirement_id for match in result.context.profile_match.matched_requirements}
    evidence_ids = {item.evidence_id for item in result.context.evidence_index}

    assert bullets
    assert len({bullet["bulletId"] for bullet in bullets}) == len(bullets)
    assert [bullet["order"] for bullet in bullets] == list(range(1, len(bullets) + 1))
    for bullet in bullets:
        assert isinstance(bullet, dict)
        assert bullet["generatedText"]
        assert bullet["currentText"] == bullet["generatedText"]
        assert bullet["userEdited"] is False
        assert bullet["validationStatus"] == "validated"
        assert bullet["supportingEvidenceIds"]
        assert set(bullet["supportingEvidenceIds"]) <= evidence_ids
        assert set(bullet["supportedRequirementIds"]) <= requirement_ids
        assert bullet["warnings"] == []


def test_structured_resume_roundtrip_preserves_bullet_ids_and_empty_arrays() -> None:
    result = run_pipeline()
    before = result.structured.model_dump(mode="json", by_alias=True)
    restored = StructuredGeneratedResume.model_validate(before)
    after = restored.model_dump(mode="json", by_alias=True)

    assert after == before
    assert first_bullet(restored)["bulletId"] == first_bullet(result.structured)["bulletId"]
    assert "warnings" in first_bullet(restored)
    assert first_bullet(restored)["warnings"] == []


def test_persistence_record_schema_reload_does_not_regenerate_structured_bullets() -> None:
    result = run_pipeline()
    persisted = result.structured.model_copy(update={"resume_id": PERSISTED_RESUME_ID, "user_id": USER_ID})
    record = record_for(persisted, result.context)
    reloaded = StructuredResumeRecord.model_validate(record.model_dump(mode="json", by_alias=True)).resume_json

    assert reloaded.model_dump(mode="json", by_alias=True) == persisted.model_dump(mode="json", by_alias=True)
    assert first_bullet(reloaded)["bulletId"] == first_bullet(persisted)["bulletId"]


def test_editing_current_text_preserves_generated_text_and_marks_user_edited() -> None:
    result = run_pipeline()
    bullet = first_bullet(result.structured)
    generated = bullet["generatedText"]

    bullet["currentText"] = generated.replace("enterprise delivery", "enterprise release delivery")
    validation = validate_structured_resume(result.structured, result.context.evidence_index, result.context.profile_match)

    assert validation.is_valid is True
    assert bullet["generatedText"] == generated
    assert bullet["currentText"] != generated
    assert bullet["userEdited"] is True
    assert bullet["validationStatus"] == "validated"


def test_unsupported_edit_persists_warning_and_is_excluded_from_supported_coverage() -> None:
    result = run_pipeline(candidate=profile("Developed C# services and SQL Server workflows for enterprise delivery."))
    bullet = first_bullet(result.structured)
    generated = bullet["generatedText"]
    bullet["currentText"] = "Improved database performance by 40%."

    validation = validate_structured_resume(result.structured, result.context.evidence_index, result.context.profile_match)
    coverage = evidence_aware_ats_coverage(result.structured, result.context)

    assert validation.is_valid is False
    assert bullet["generatedText"] == generated
    assert bullet["currentText"] == "Improved database performance by 40%."
    assert bullet["validationStatus"] == "rejected"
    assert bullet["warnings"]
    assert coverage["supportedButNotRepresented"]
    assert not coverage["supportedAndCovered"]


def test_reverting_current_text_to_generated_text_clears_user_edited_on_model_validation() -> None:
    result = run_pipeline()
    bullet = first_bullet(result.structured)
    bullet["currentText"] = f"{bullet['generatedText']} temporary edit"
    validate_structured_resume(result.structured, result.context.evidence_index, result.context.profile_match)
    assert bullet["userEdited"] is True

    bullet["currentText"] = bullet["generatedText"]
    validate_structured_resume(result.structured, result.context.evidence_index, result.context.profile_match)
    restored = StructuredGeneratedResume.model_validate(result.structured.model_dump(mode="json", by_alias=True))

    assert first_bullet(restored)["userEdited"] is False
    assert first_bullet(restored)["validationStatus"] == "validated"
    assert first_bullet(restored)["warnings"] == []


def test_version_copy_policy_keeps_bullet_ids_and_version_specific_current_text() -> None:
    result = run_pipeline()
    old_version = result.structured
    new_version = deepcopy(old_version)
    first_bullet(new_version)["currentText"] = "Edited C# API delivery for version two."
    new_version = new_version.model_copy(update={"version_number": 2, "status": "draft"})

    assert first_bullet(old_version)["currentText"] == first_bullet(old_version)["generatedText"]
    assert first_bullet(new_version)["currentText"] == "Edited C# API delivery for version two."
    assert first_bullet(new_version)["generatedText"] == first_bullet(old_version)["generatedText"]
    assert first_bullet(new_version)["bulletId"] == first_bullet(old_version)["bulletId"]
    assert first_bullet(new_version)["supportingEvidenceIds"] == first_bullet(old_version)["supportingEvidenceIds"]


def test_ats_coverage_categories_are_evidence_aware_not_text_only() -> None:
    result = run_pipeline(requirement="React", candidate=profile("Built Angular components for enterprise workflows.", skills=["Angular"]))
    before_score = result.response.ats_score
    result.structured.sections[0].content = f"{result.structured.sections[0].content} React"
    coverage = evidence_aware_ats_coverage(result.structured, result.context)
    response = build_generation_response(result.candidate, result.payload, result.context, result.structured, result.validation)

    assert coverage["adjacentUnsupported"] or coverage["unmatched"]
    assert not coverage["supportedAndCovered"]
    assert response.ats_score == before_score


def test_suggested_keywords_are_excluded_from_supported_coverage() -> None:
    result = run_pipeline(requirement="Kubernetes", candidate=profile("Used Kubernetes for deployment workflows.", skills=["Kubernetes"]), source_type="suggested")

    assert result.response.breakdown.coverage["suggestedExcluded"]
    assert not result.response.breakdown.coverage["supportedAndCovered"]
    assert result.response.breakdown.keyword_match == 0


def test_rejected_bullet_lowers_evidence_aware_ats_score_and_revert_restores_it() -> None:
    result = run_pipeline(candidate=profile("Built C# and ASP.NET Core REST API enhancements with SQL Server for enterprise delivery."))
    initial_score = result.response.ats_score
    bullet = first_bullet(result.structured)
    generated = bullet["generatedText"]

    bullet["currentText"] = "Improved database performance by 40%."
    validation = validate_structured_resume(result.structured, result.context.evidence_index, result.context.profile_match)
    rejected_response = build_generation_response(result.candidate, result.payload, result.context, result.structured, validation)

    assert rejected_response.ats_score < initial_score
    assert rejected_response.breakdown.coverage["supportedButNotRepresented"]

    bullet["currentText"] = generated
    reverted_validation = validate_structured_resume(result.structured, result.context.evidence_index, result.context.profile_match)
    reverted_response = build_generation_response(result.candidate, result.payload, result.context, result.structured, reverted_validation)

    assert reverted_response.ats_score == initial_score
    assert first_bullet(result.structured)["userEdited"] is False
    assert first_bullet(result.structured)["validationStatus"] == "validated"


def test_legacy_string_bullets_normalize_without_false_validation_and_export() -> None:
    result = run_pipeline()
    exp_section = next(section for section in result.structured.sections if section.type == "experience")
    exp_section.content[0]["bullets"] = ["Legacy visible bullet."]

    normalized = normalize_structured_resume_bullets(result.structured)
    validation = validate_structured_resume(normalized, result.context.evidence_index, result.context.profile_match)
    bullet = first_bullet(normalized)
    exported = export_resume_record(record_for(normalized, result.context), export_format=ExportFormat.pdf)

    assert validation.is_valid is True
    assert bullet["currentText"] == "Legacy visible bullet."
    assert bullet["generatedText"] == ""
    assert bullet["supportingEvidenceIds"] == []
    assert bullet["validationStatus"] == "warning"
    assert "Legacy visible bullet" in pdf_text(exported.content)


def test_pdf_and_docx_exports_render_current_text_only_and_hide_internal_metadata() -> None:
    result = run_pipeline()
    bullet = first_bullet(result.structured)
    bullet["currentText"] = "Edited currentText bullet for export."
    record = record_for(result.structured, result.context)

    pdf = pdf_text(export_resume_record(record, export_format=ExportFormat.pdf).content)
    docx = docx_text(export_resume_record(record, export_format=ExportFormat.docx).content)

    for text in (pdf, docx):
        assert "Edited currentText bullet for export." in text
        assert bullet["generatedText"] not in text
        assert bullet["supportingEvidenceIds"][0] not in text
        assert bullet["supportedRequirementIds"][0] not in text
        assert "validation" not in text.lower()


def test_flattened_resume_content_is_derived_duplicate_not_the_editing_source() -> None:
    result = run_pipeline()
    flattened = structured_to_resume_content(result.candidate, result.structured)

    assert flattened.experience[0].bullets[0] == first_bullet(result.structured)["currentText"]
    assert isinstance(flattened.experience[0].bullets[0], str)
    assert isinstance(first_bullet(result.structured), dict)
