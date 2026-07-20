import pytest

from app.core.config import settings
from app.schemas.resume import SectionEnhancementApplyRequest, SectionEnhancementRequest, StructuredResumeRecord
from app.services.ai_usage import AICompletionResult
from app.services.resume_section_enhancement import (
    SectionEnhancementError,
    apply_section_enhancement_to_resume,
    generate_section_enhancement,
)


def resume_record() -> StructuredResumeRecord:
    return StructuredResumeRecord(
        resumeId="11111111-1111-1111-1111-111111111111",
        userId="22222222-2222-2222-2222-222222222222",
        profileId="33333333-3333-3333-3333-333333333333",
        profileVersion=1,
        profileContentHash="profile-hash",
        resumeName="Venu Resume",
        targetJobTitle="Senior .NET Developer",
        targetCompany="Digittech",
        jobDescription="C# .NET SQL Server REST APIs",
        jobAnalysisJson={},
        profileMatchJson={},
        resumeJson={
            "resumeId": "11111111-1111-1111-1111-111111111111",
            "userId": "22222222-2222-2222-2222-222222222222",
            "resumeHeader": {"fullName": "Venu Madhav Pendurthi", "currentTitle": "Senior .NET Developer"},
            "resumeName": "Venu Resume",
            "targetJobTitle": "Senior .NET Developer",
            "targetCompany": "Digittech",
            "jobDescription": "C# .NET SQL Server REST APIs",
            "profileId": "33333333-3333-3333-3333-333333333333",
            "profileVersion": 1,
            "profileContentHash": "profile-hash",
            "matchingAlgorithmVersion": "match-v1",
            "generationAlgorithmVersion": "generation-v1",
            "templateId": "classic-ats",
            "versionNumber": 1,
            "status": "draft",
            "matchScore": 76,
            "missingRequirements": [],
            "warnings": [],
            "contact": {"email": "", "phone": "", "location": ""},
            "sections": [
                {
                    "sectionId": "section-summary",
                    "type": "summary",
                    "title": "SUMMARY",
                    "order": 1,
                    "visible": True,
                    "content": "Senior .NET Developer with C# and SQL Server delivery experience.",
                    "provenance": {
                        "supportingEvidenceIds": ["ev-summary"],
                        "supportedRequirementIds": ["req-dotnet"],
                        "generationMethod": "summary_intelligence",
                        "validationStatus": "validated",
                        "warnings": [],
                    },
                },
                {
                    "sectionId": "section-experience",
                    "type": "experience",
                    "title": "PROFESSIONAL EXPERIENCE",
                    "order": 2,
                    "visible": True,
                    "content": [
                        {
                            "company": "Infosys",
                            "role": "Senior .NET Developer",
                            "location": "Hartford, CT",
                            "sourceRecordId": "experience-exp-infosys",
                            "bullets": [
                                {
                                    "bulletId": "bullet-1",
                                    "order": 1,
                                    "generatedText": "Built C# API features with SQL Server for enterprise workflows.",
                                    "currentText": "Built C# API features with SQL Server for enterprise workflows.",
                                    "userEdited": False,
                                    "supportingEvidenceIds": ["ev-bullet"],
                                    "supportedRequirementIds": ["req-csharp"],
                                }
                            ],
                        }
                    ],
                    "provenance": {
                        "supportingEvidenceIds": ["ev-bullet"],
                        "supportedRequirementIds": ["req-csharp"],
                        "generationMethod": "experience_intelligence",
                        "validationStatus": "validated",
                        "warnings": [],
                    },
                },
            ],
            "createdAt": "2026-07-19T00:00:00+00:00",
            "updatedAt": "2026-07-19T00:00:00+00:00",
        },
        templateId="classic-ats",
        matchScore=76,
        generationAlgorithmVersion="generation-v1",
        status="draft",
        versionNumber=1,
        parentResumeId="",
        createdAt="2026-07-19T00:00:00+00:00",
        updatedAt="2026-07-19T00:00:00+00:00",
    )


class DummyAI:
    def __init__(self, content: str) -> None:
        self.content = content

    async def chat_completion(self, **kwargs):
        return AICompletionResult(
            content=self.content,
            model="gpt-5.5-mini",
            input_tokens=10,
            output_tokens=10,
            total_tokens=20,
            estimated_cost=0,
            latency_ms=1,
            cache_hit=False,
        )


@pytest.mark.asyncio
async def test_enhancement_suggestion_is_read_only_and_apply_updates_selected_bullet(monkeypatch):
    record = resume_record()
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_section_enhancement_enabled", True)
    monkeypatch.setattr(
        "app.services.resume_section_enhancement.get_ai_service",
        lambda: DummyAI(
            '{"suggestions":[{"enhancedText":"Built maintainable C# API features with SQL Server for enterprise workflows.","explanation":"Tightened wording.","supportingEvidenceIds":["ev-bullet"],"supportedRequirementIds":["req-csharp"]}]}'
        ),
    )

    response = await generate_section_enhancement(
        record,
        SectionEnhancementRequest(
            resumeId=record.resume_id,
            sectionType="experience_bullet",
            sectionId="bullet-1",
            parentSectionId="section-experience",
            currentText="Built C# API features with SQL Server for enterprise workflows.",
            expectedRevision=record.updated_at,
        ),
        user_id=record.user_id,
    )

    assert response.suggestions[0].enhanced_text.startswith("Built maintainable C#")
    original_bullet = record.resume_json.sections[1].content[0]["bullets"][0]
    assert original_bullet["currentText"] == original_bullet["generatedText"]

    updated = apply_section_enhancement_to_resume(
        record,
        SectionEnhancementApplyRequest(
            resumeId=record.resume_id,
            sectionType="experience_bullet",
            sectionId="bullet-1",
            suggestionId=response.suggestions[0].suggestion_id,
            expectedRevision=record.updated_at,
        ),
    )

    bullet = updated.sections[1].content[0]["bullets"][0]
    assert bullet["generatedText"] == "Built C# API features with SQL Server for enterprise workflows."
    assert bullet["currentText"] == "Built maintainable C# API features with SQL Server for enterprise workflows."
    assert bullet["userEdited"] is True
    assert updated.enhancement_history[-1]["sectionId"] == "bullet-1"


@pytest.mark.asyncio
async def test_enhancement_rejects_unsupported_added_technology(monkeypatch):
    record = resume_record()
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_section_enhancement_enabled", True)
    monkeypatch.setattr(
        "app.services.resume_section_enhancement.get_ai_service",
        lambda: DummyAI(
            '{"suggestions":[{"enhancedText":"Built Java Spring Boot API features with SQL Server for enterprise workflows.","explanation":"Unsafe.","supportingEvidenceIds":["ev-bullet"],"supportedRequirementIds":["req-csharp"]}]}'
        ),
    )

    with pytest.raises(SectionEnhancementError) as exc:
        await generate_section_enhancement(
            record,
            SectionEnhancementRequest(
                resumeId=record.resume_id,
                sectionType="experience_bullet",
                sectionId="bullet-1",
                parentSectionId="section-experience",
                currentText="Built C# API features with SQL Server for enterprise workflows.",
                expectedRevision=record.updated_at,
            ),
            user_id=record.user_id,
        )

    assert exc.value.code == "SECTION_ENHANCEMENT_INVALID_OUTPUT"


@pytest.mark.asyncio
async def test_enhancement_returns_clear_provider_error(monkeypatch):
    class FailingAI:
        async def chat_completion(self, **kwargs):
            raise RuntimeError("Error code: 429 - insufficient_quota")

    record = resume_record()
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_section_enhancement_enabled", True)
    monkeypatch.setattr("app.services.resume_section_enhancement.get_ai_service", lambda: FailingAI())

    with pytest.raises(SectionEnhancementError) as exc:
        await generate_section_enhancement(
            record,
            SectionEnhancementRequest(
                resumeId=record.resume_id,
                sectionType="experience_bullet",
                sectionId="bullet-1",
                parentSectionId="section-experience",
                currentText="Built C# API features with SQL Server for enterprise workflows.",
                expectedRevision=record.updated_at,
            ),
            user_id=record.user_id,
        )

    assert exc.value.code == "SECTION_ENHANCEMENT_AI_UNAVAILABLE"
    assert "quota" in exc.value.message.casefold()
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_role_enhancement_preserves_bullet_boundaries(monkeypatch):
    record = resume_record()
    record.resume_json.sections[1].content[0]["bullets"].append(
        {
            "bulletId": "bullet-2",
            "order": 2,
            "generatedText": "Reviewed SQL changes with QA before release.",
            "currentText": "Reviewed SQL changes with QA before release.",
            "userEdited": False,
            "supportingEvidenceIds": ["ev-bullet"],
            "supportedRequirementIds": ["req-csharp"],
        }
    )
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_section_enhancement_enabled", True)
    monkeypatch.setattr(
        "app.services.resume_section_enhancement.get_ai_service",
        lambda: DummyAI(
            json_response(
                [
                    "- Built maintainable C# API features with SQL Server for enterprise workflows.\n"
                    "- Reviewed SQL changes with QA before release readiness."
                ]
            )
        ),
    )

    response = await generate_section_enhancement(
        record,
        SectionEnhancementRequest(
            resumeId=record.resume_id,
            sectionType="experience_role",
            sectionId="experience-exp-infosys",
            parentSectionId="section-experience",
            currentText="",
            expectedRevision=record.updated_at,
        ),
        user_id=record.user_id,
    )

    assert "\n" in response.suggestions[0].enhanced_text

    updated = apply_section_enhancement_to_resume(
        record,
        SectionEnhancementApplyRequest(
            resumeId=record.resume_id,
            sectionType="experience_role",
            sectionId="experience-exp-infosys",
            suggestionId=response.suggestions[0].suggestion_id,
            expectedRevision=record.updated_at,
        ),
    )

    bullets = updated.sections[1].content[0]["bullets"]
    assert len(bullets) == 2
    assert bullets[0]["currentText"].startswith("Built maintainable C#")
    assert bullets[1]["currentText"].startswith("Reviewed SQL")


def json_response(enhanced_texts: list[str]) -> str:
    return (
        '{"suggestions":['
        + ",".join(
            f'{{"enhancedText":{text!r},"explanation":"Polished wording.","supportingEvidenceIds":["ev-bullet"],"supportedRequirementIds":["req-csharp"]}}'.replace(
                "'",
                '"',
            )
            for text in enhanced_texts
        )
        + "]}"
    )
