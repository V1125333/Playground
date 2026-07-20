from __future__ import annotations

import pytest
from docx import Document
from io import BytesIO
from pypdf import PdfReader

from app.schemas.resume import (
    CandidateProfile,
    GenerateResumeRequest,
    JobAnalysisResponse,
    JobKeywordAnalysisItem,
    NormalizedRequirements,
    ResumeContact,
    ResumeEducation,
    ResumeExperience,
    ResumeProject,
    StructuredResumeRecord,
    SkillCategory,
    TypedJobRequirement,
)
from app.services.ai_usage import AICompletionResult
from app.services.export import ExportFormat, export_resume_record
from app.services.profile_matching import calculate_non_overlapping_experience_months
from app.services.profile_service import ensure_profile_record_ids
from app.services.resume_generation_pipeline import (
    assemble_structured_resume,
    build_generation_context,
    select_relevant_profile_evidence,
)
from app.services.summary_planner import (
    SummaryGenerationResult,
    SummaryValidationCode,
    build_summary_planner,
    build_validated_summary,
    count_sentences,
    validate_summary_result,
)


def keyword(value: str, *, category: str = "Technology", priority: str = "high", score: int = 90) -> JobKeywordAnalysisItem:
    return JobKeywordAnalysisItem(
        id=f"kw-{value.lower().replace(' ', '-')}",
        value=value,
        normalizedValue=value,
        category=category,
        sourceType="explicit",
        confidence="high",
        priority=priority,
        priorityScore=score,
        directFromJD=True,
        evidenceText=f"JD mentions {value}",
        sourceSentence=f"JD mentions {value}",
        occurrenceCount=1,
    )


def analysis(*items: JobKeywordAnalysisItem) -> JobAnalysisResponse:
    typed_requirements = [
        TypedJobRequirement(
            requirementId=item.id,
            canonicalTerm=item.value,
            originalTerms=[item.value],
            category=item.category,
            requirementLevel="required",
            priority="high" if item.priority == "high" else "medium",
            explicit=True,
            confidence=0.9,
            evidenceText=item.evidence_text,
            sourceSentence=item.source_sentence,
        )
        for item in items
    ]
    return JobAnalysisResponse(
        roleInformation={"title": "Software Engineer", "seniority": "Senior"},
        keywords=list(items),
        normalizedRequirements=NormalizedRequirements(
            technicalRequirements=[item for item in typed_requirements if item.category in {"Technology", "Cloud", "Database", "API", "Architecture", "Frontend"}],
            responsibilityRequirements=[item for item in typed_requirements if item.category not in {"Technology", "Cloud", "Database", "API", "Architecture", "Frontend"}],
        ),
        analysisHash="summary-test",
    )


def profile() -> CandidateProfile:
    return ensure_profile_record_ids(
        CandidateProfile(
            name="Venu Madhav Pendurthi",
            title="Senior Full Stack .NET Developer",
            contact=ResumeContact(email="venu@example.com", phone="+12014436937", location="Hartford, CT"),
            skills=[
                SkillCategory(category="Programming Languages", categoryId="programming-languages", categoryName="Programming Languages", order=0, items=["C#", "JavaScript"]),
                SkillCategory(category="Backend Development", categoryId="backend-development", categoryName="Backend Development", order=1, items=[".NET Framework", "ASP.NET MVC", "REST APIs"]),
                SkillCategory(category="Databases", categoryId="databases", categoryName="Databases", order=2, items=["SQL Server", "T-SQL"]),
            ],
            experience=[
                ResumeExperience(
                    company="Infosys",
                    role="Senior .NET Developer",
                    location="Hartford, CT",
                    startDate="2025-01",
                    endDate="Present",
                    responsibilities=[
                        "Maintained C# and .NET Framework applications for healthcare provider workflows.",
                        "Reviewed code changes with QA and infrastructure teams.",
                        "Documented system functionality, technical changes, and deployment notes.",
                    ],
                    achievements=[
                        "Optimized SQL Server stored procedures to improve application response time by 20%.",
                        "Resolved production defects through debugging and root-cause analysis.",
                    ],
                    technologies=["C#", ".NET Framework", "SQL Server"],
                )
            ],
            education=[ResumeEducation(degree="Bachelor's degree in Computer Science", institution="JNTU")],
        )
    )


def payload(job_analysis: JobAnalysisResponse) -> GenerateResumeRequest:
    return GenerateResumeRequest(
        profileId="11111111-1111-1111-1111-111111111111",
        job_description="Need C#, .NET Framework, SQL Server, production support, documentation, and code reviews.",
        target_role="Java Architect",
        target_company="Digitech",
        jobAnalysis=job_analysis,
        resumePreferences={
            "templateId": "classic-ats",
            "headerVisibility": {
                "fullName": True,
                "currentTitle": True,
                "email": True,
                "phone": True,
                "location": True,
                "linkedinUrl": False,
                "githubUrl": False,
                "portfolioUrl": False,
            },
            "sectionVisibility": {
                "summary": True,
                "skills": True,
                "experience": True,
                "projects": True,
                "education": True,
                "certifications": True,
            },
        },
    )


class ProfileRecord:
    profile_id = "11111111-1111-1111-1111-111111111111"
    profile_version = 1
    content_hash = "hash"
    updated_at = "2026-07-01T00:00:00+00:00"

    def __init__(self, profile_data: CandidateProfile):
        self.profile_data = profile_data


def planner_for(job_analysis: JobAnalysisResponse):
    candidate = profile()
    request = payload(job_analysis)
    context = build_generation_context(ProfileRecord(candidate), request, job_analysis)
    planner = build_summary_planner(
        candidate,
        request,
        context.profile_match,
        context.evidence_index,
        round(calculate_non_overlapping_experience_months(candidate) / 12, 1),
    )
    return candidate, request, context, planner


async def adaptive_summary_for(job_analysis: JobAnalysisResponse, *, target_role: str, job_description: str):
    candidate = profile()
    candidate.skills[1].items.append("ASP.NET Core")
    candidate.skills.extend(
        [
            SkillCategory(
                category="Data Engineering",
                categoryId="data-engineering",
                categoryName="Data Engineering",
                order=4,
                items=["Azure Data Factory", "Databricks", "Apache Spark"],
            ),
            SkillCategory(
                category="AI Engineering",
                categoryId="ai-engineering",
                categoryName="AI Engineering",
                order=5,
                items=["Python", "FastAPI", "RAG", "LangChain"],
            ),
        ]
    )
    candidate.experience[0].responsibilities.extend(
        [
            "Built Azure Data Factory and Databricks data pipelines using Python, SQL, and Spark for reporting workflows.",
            "Created FastAPI services for RAG prototypes with LangChain retrieval flows and API validation.",
            "Maintained production .NET applications by resolving defects, improving reliability, and coordinating releases.",
            "Designed REST API changes and reviewed service-layer implementation with QA and engineering teams.",
        ]
    )
    candidate.projects.append(
        ResumeProject(
            name="AI Knowledge Assistant",
            bullets=["Built a RAG proof of concept using Python, FastAPI, LangChain, and REST APIs."],
            technologies=["Python", "FastAPI", "RAG", "LangChain"],
        )
    )
    request = payload(job_analysis)
    request.target_role = target_role
    request.job_description = job_description
    context = build_generation_context(ProfileRecord(candidate), request, request.job_analysis)
    planner = build_summary_planner(
        candidate,
        request,
        context.profile_match,
        context.evidence_index,
        9.6,
    )
    result = await build_validated_summary(planner, use_ai=False)
    return planner, result.generation.summary


@pytest.mark.asyncio
async def test_planner_fallback_removes_previous_grounded_in_summary_language() -> None:
    _, _, _, planner = planner_for(analysis(keyword("C#"), keyword(".NET Framework"), keyword("5 Years of Experience", category="Experience")))

    result = await build_validated_summary(planner, use_ai=False)

    assert "grounded in" not in result.generation.summary.lower()
    assert "evidence-backed resume claims" not in result.generation.summary.lower()
    assert "5 Years of Experience" not in result.generation.summary
    assert result.validation.is_valid is True


@pytest.mark.asyncio
async def test_summary_does_not_leak_raw_education_keyword() -> None:
    _, _, _, planner = planner_for(analysis(keyword("Bachelor's Degree", category="Education"), keyword("C#")))

    result = await build_validated_summary(planner, use_ai=False)

    assert "Bachelor" not in result.generation.summary
    assert "education" not in result.generation.summary.lower()


@pytest.mark.asyncio
async def test_summary_does_not_use_company_client_or_location_as_capabilities() -> None:
    candidate = profile()
    candidate.experience[0].company = "Tata Consultancy Servives"
    candidate.experience[0].client_name = "Western Union"
    candidate.experience[0].location = "Hyderabad, Telangana, India"
    candidate.experience[0].responsibilities = []
    candidate.experience[0].achievements = []
    request = payload(
        analysis(
            keyword("Tata Consultancy Servives", category="Domain"),
            keyword("Western Union", category="Domain"),
            keyword("Hyderabad, Telangana, India", category="Location"),
            keyword("C#"),
        )
    )
    context = build_generation_context(ProfileRecord(candidate), request, request.job_analysis)
    planner = build_summary_planner(
        candidate,
        request,
        context.profile_match,
        context.evidence_index,
        round(calculate_non_overlapping_experience_months(candidate) / 12, 1),
    )

    result = await build_validated_summary(planner, use_ai=False)

    assert "Tata Consultancy" not in result.generation.summary
    assert "Servives" not in result.generation.summary
    assert "Western Union" not in result.generation.summary
    assert "Hyderabad" not in result.generation.summary


def test_validator_rejects_exact_failing_summary_shape() -> None:
    _, _, _, planner = planner_for(
        analysis(
            keyword("C#"),
            keyword("ASP.NET Core"),
            keyword("Microsoft Azure", category="Cloud"),
            keyword("Microsoft SQL Server", category="Database"),
        )
    )
    planner.excluded_company_terms.append("Tata Consultancy Servives")
    planner.excluded_client_terms.append("Western Union")
    planner.excluded_location_terms.append("Hyderabad, Telangana, India")
    planner.excluded_metadata_terms.extend(["Tata Consultancy Servives", "Western Union", "Hyderabad, Telangana, India"])
    generated = SummaryGenerationResult(
        summary=(
            "Senior Full Stack .NET developer with 9.6+ years of experience building and maintaining enterprise applications using C#, "
            "ASP.NET Core, ASP.NET MVC, Microsoft Azure (App Service, Azure SQL), and Microsoft SQL Server. "
            "Experienced in Tata Consultancy Servives, Western Union, and Hyderabad, Telangana, India across Agile delivery teams. "
            "Known for maintainable software delivery while turning business requirements into reliable software solutions."
        ),
        usedEvidenceIds=list(planner.evidence_ids)[:1],
        usedSignals=["C#"],
        excludedSignals=[],
        riskFlags=[],
    )

    validation = validate_summary_result(generated, planner)

    assert validation.is_valid is False
    assert SummaryValidationCode.invalid_experience_display in validation.validation_codes
    assert SummaryValidationCode.raw_company_name_in_capability in validation.validation_codes
    assert SummaryValidationCode.raw_client_name_in_capability in validation.validation_codes
    assert SummaryValidationCode.location_leakage in validation.validation_codes
    assert SummaryValidationCode.overloaded_technology_list in validation.validation_codes
    assert SummaryValidationCode.generic_repetitive_language in validation.validation_codes


def test_validator_allows_professional_title_fragment_from_identity_metadata() -> None:
    _, _, _, planner = planner_for(
        analysis(
            keyword("C#"),
            keyword(".NET Framework"),
            keyword("SQL Server", category="Database"),
        )
    )
    planner.excluded_metadata_terms.append(".NET Developer")
    generated = SummaryGenerationResult(
        summary=(
            "Senior Full Stack .NET Developer with 9+ years of experience building enterprise applications using C#, "
            ".NET Framework, and SQL Server. Focused on maintainable implementation, debugging, and cross-team delivery "
            "for enterprise software."
        ),
        usedEvidenceIds=list(planner.evidence_ids)[:2],
        usedSignals=["C#", ".NET Framework", "SQL Server"],
        excludedSignals=[],
        riskFlags=[],
    )

    validation = validate_summary_result(generated, planner)

    assert SummaryValidationCode.metadata_leakage not in validation.validation_codes


@pytest.mark.asyncio
async def test_summary_safely_maps_domains_and_canonical_technologies() -> None:
    candidate = profile()
    candidate.skills.append(
        SkillCategory(
            category="Cloud",
            categoryId="cloud",
            categoryName="Cloud",
            order=3,
            items=["Microsoft Azure (App Service, Azure SQL)", "Microsoft SQL Server"],
        )
    )
    candidate.experience[0].client_name = "Molina Healthcare"
    candidate.experience[0].responsibilities.append("Built REST API integrations and database-driven provider workflows.")
    request = payload(
        analysis(
            keyword("Microsoft Azure", category="Cloud"),
            keyword("Microsoft SQL Server", category="Database"),
            keyword("Molina Healthcare", category="Domain"),
            keyword("REST API Development", category="API"),
        )
    )
    context = build_generation_context(ProfileRecord(candidate), request, request.job_analysis)
    planner = build_summary_planner(candidate, request, context.profile_match, context.evidence_index, 9.6)

    result = await build_validated_summary(planner, use_ai=False)

    assert "9.6+" not in result.generation.summary
    assert "9+ years" in result.generation.summary
    assert "Molina Healthcare" not in result.generation.summary
    assert "healthcare" in result.generation.summary.lower()
    assert "Microsoft Azure (" not in result.generation.summary
    assert "Microsoft SQL Server" not in result.generation.summary
    assert "Azure" in result.generation.summary
    assert "SQL Server" in result.generation.summary
    assert result.validation.is_valid is True


@pytest.mark.asyncio
async def test_support_jd_summary_prioritizes_support_and_collaboration_not_cloud_noise() -> None:
    candidate = profile()
    candidate.skills.append(
        SkillCategory(
            category="Cloud",
            categoryId="cloud",
            categoryName="Cloud",
            order=3,
            items=["Azure", "T-SQL"],
        )
    )
    candidate.experience[0].responsibilities.extend(
        [
            "Collaborated with product owners, QA, infrastructure, app support, and business stakeholders.",
            "Supported assigned application changes while balancing quality and schedule expectations.",
        ]
    )
    request = payload(
        analysis(
            keyword("database architecture", category="Architecture"),
            keyword("user interface", category="Frontend"),
            keyword("stakeholder collaboration", category="Professional Skills"),
            keyword("issue resolution", category="Support"),
            keyword("quality and schedule accountability", category="Delivery"),
            keyword("technical documentation", category="Documentation"),
        )
    )
    context = build_generation_context(ProfileRecord(candidate), request, request.job_analysis)
    planner = build_summary_planner(candidate, request, context.profile_match, context.evidence_index, 9.6)

    result = await build_validated_summary(planner, use_ai=False)

    assert "Azure" not in result.generation.summary
    assert "T-SQL" not in result.generation.summary
    assert "9+ years" in result.generation.summary
    assert "C#" in result.generation.summary
    assert "SQL Server" in result.generation.summary
    assert any(term in result.generation.summary for term in ["production troubleshooting", "debugging"])
    assert "technical documentation" in result.generation.summary
    assert "collaboration" in result.generation.summary.lower() or "collaborates" in result.generation.summary.lower()
    assert result.validation.is_valid is True


def test_validator_rejects_unsupported_java_and_aws_claims() -> None:
    _, _, _, planner = planner_for(analysis(keyword("Java"), keyword("AWS", category="Cloud"), keyword("C#")))
    generated = SummaryGenerationResult(
        summary="Senior Full Stack .NET Developer with 9+ years of experience building Java and AWS systems.",
        usedEvidenceIds=list(planner.evidence_ids)[:1],
        usedSignals=["Java", "AWS"],
        excludedSignals=[],
        riskFlags=[],
    )

    validation = validate_summary_result(generated, planner)

    assert validation.is_valid is False
    assert any("unsupported technology" in error.lower() for error in validation.errors)


@pytest.mark.asyncio
async def test_summary_preserves_candidate_identity_not_jd_identity() -> None:
    _, _, _, planner = planner_for(analysis(keyword("Java"), keyword("Architecture", category="Architecture"), keyword("C#")))

    result = await build_validated_summary(planner, use_ai=False)

    assert "Senior Full Stack .NET Developer" in result.generation.summary
    assert "Java Architect" not in result.generation.summary


@pytest.mark.asyncio
async def test_verified_domain_can_be_included_when_supported_by_profile_evidence() -> None:
    _, _, _, planner = planner_for(analysis(keyword("Healthcare", category="Domain"), keyword("C#")))

    result = await build_validated_summary(planner, use_ai=False)

    assert "Healthcare" in result.generation.summary or "healthcare" in result.generation.summary


@pytest.mark.asyncio
async def test_summary_sentence_and_word_constraints_are_enforced() -> None:
    _, _, _, planner = planner_for(analysis(keyword("C#"), keyword(".NET Framework"), keyword("SQL Server")))

    result = await build_validated_summary(planner, use_ai=False)

    assert 2 <= count_sentences(result.generation.summary) <= 3
    assert len(result.generation.summary.split()) <= 80


class MalformedAI:
    async def chat_completion(self, **kwargs):
        return AICompletionResult(content="{not valid json", model="test", input_tokens=1, output_tokens=1, total_tokens=2, estimated_cost=0, latency_ms=1)


class FailingAI:
    async def chat_completion(self, **kwargs):
        raise TimeoutError("timeout")


class InvalidEvidenceAI:
    async def chat_completion(self, **kwargs):
        return AICompletionResult(
            content='{"summary":"Senior Full Stack .NET Developer with 9+ years of experience building C# systems.","usedEvidenceIds":["missing-id"],"usedSignals":["C#"],"excludedSignals":[],"riskFlags":[]}',
            model="test",
            input_tokens=1,
            output_tokens=1,
            total_tokens=2,
            estimated_cost=0,
            latency_ms=1,
        )


@pytest.mark.asyncio
async def test_malformed_llm_json_falls_back_to_deterministic_summary() -> None:
    _, _, _, planner = planner_for(analysis(keyword("C#")))

    result = await build_validated_summary(planner, ai_service=MalformedAI(), use_ai=True, max_retries=0)

    assert result.generation.generation_method == "deterministic"
    assert result.validation.is_valid is True


@pytest.mark.asyncio
async def test_llm_timeout_falls_back_to_deterministic_summary() -> None:
    _, _, _, planner = planner_for(analysis(keyword("C#")))

    result = await build_validated_summary(planner, ai_service=FailingAI(), use_ai=True, max_retries=0)

    assert result.generation.generation_method == "deterministic"
    assert result.validation.is_valid is True


@pytest.mark.asyncio
async def test_invalid_llm_evidence_ids_retry_then_fallback() -> None:
    _, _, _, planner = planner_for(analysis(keyword("C#")))

    result = await build_validated_summary(planner, ai_service=InvalidEvidenceAI(), use_ai=True, max_retries=0)

    assert result.generation.generation_method == "deterministic"
    assert set(result.generation.used_evidence_ids) <= planner.evidence_ids


@pytest.mark.asyncio
async def test_structured_resume_preview_pdf_and_docx_use_same_validated_summary() -> None:
    candidate, request, context, planner = planner_for(analysis(keyword("C#"), keyword(".NET Framework"), keyword("SQL Server")))
    summary = (await build_validated_summary(planner, use_ai=False)).generation
    selected = select_relevant_profile_evidence(context)
    structured = assemble_structured_resume(candidate, request, context, selected, summary)
    summary_section = next(section for section in structured.sections if section.type == "summary")
    record = StructuredResumeRecord(
        resumeId=structured.resume_id or "resume-id",
        userId="11111111-1111-1111-1111-111111111111",
        profileId=structured.profile_id,
        profileVersion=structured.profile_version,
        profileContentHash=structured.profile_content_hash,
        resumeName=structured.resume_name,
        targetJobTitle=structured.target_job_title,
        targetCompany=structured.target_company,
        jobDescription=structured.job_description,
        jobAnalysisJson={},
        profileMatchJson=context.profile_match.model_dump(mode="json", by_alias=True),
        resumeJson=structured,
        templateId=structured.template_id,
        matchScore=structured.match_score,
        generationAlgorithmVersion=structured.generation_algorithm_version,
        status=structured.status,
        versionNumber=structured.version_number,
        parentResumeId="",
        createdAt=structured.created_at,
        updatedAt=structured.updated_at,
    )

    pdf_result = export_resume_record(record, export_format=ExportFormat.pdf).content
    docx_result = export_resume_record(record, export_format=ExportFormat.docx).content
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf_result)).pages)
    docx_text = "\n".join(paragraph.text for paragraph in Document(BytesIO(docx_result)).paragraphs)

    assert summary_section.content == summary.summary
    assert summary.summary.split(".")[0] in pdf_text
    assert summary.summary.split(".")[0] in docx_text


@pytest.mark.asyncio
async def test_summary_adapts_across_role_families_without_changing_identity() -> None:
    scenarios = {
        "dotnet": await adaptive_summary_for(
            analysis(keyword("C#"), keyword("ASP.NET Core"), keyword("SQL Server"), keyword("REST API Development", category="API")),
            target_role="Senior .NET Developer",
            job_description="Senior .NET developer role building C#, ASP.NET Core, SQL Server, and REST API applications.",
        ),
        "support": await adaptive_summary_for(
            analysis(keyword("production support", category="Support"), keyword("defect resolution", category="Support"), keyword("SQL Server")),
            target_role="Application Support .NET Engineer",
            job_description="Maintain production .NET applications, resolve defects, troubleshoot issues, and improve reliability.",
        ),
        "data": await adaptive_summary_for(
            analysis(keyword("Python"), keyword("SQL"), keyword("Azure Data Factory"), keyword("Databricks"), keyword("Apache Spark"), keyword("ETL", category="Data")),
            target_role="Data Engineer",
            job_description="Data Engineer role building ETL data pipelines with Python, SQL, Azure Data Factory, Databricks, and Spark.",
        ),
        "ai": await adaptive_summary_for(
            analysis(keyword("Python"), keyword("FastAPI"), keyword("RAG"), keyword("LangChain"), keyword("REST APIs")),
            target_role="AI Engineer",
            job_description="AI Engineer role building RAG workflows, FastAPI services, LangChain retrieval, and REST APIs.",
        ),
        "java": await adaptive_summary_for(
            analysis(keyword("Java"), keyword("Spring Boot"), keyword("REST APIs"), keyword("SQL Server")),
            target_role="Java Developer",
            job_description="Java developer role using Spring Boot, REST APIs, SQL databases, code reviews, and backend services.",
        ),
    }

    summaries = {name: summary for name, (_, summary) in scenarios.items()}
    for summary in summaries.values():
        assert "Senior Full Stack .NET Developer" in summary

    assert "Java" not in summaries["java"]
    assert "Spring Boot" not in summaries["java"]
    assert all(term in summaries["data"] for term in ["Python", "Azure Data Factory", "Databricks", "Apache Spark"])
    assert all(term in summaries["ai"] for term in ["Python", "FastAPI", "RAG", "LangChain"])
    assert "production application maintenance and reliability" in summaries["support"]
    assert "defects" in summaries["support"].lower() or "troubleshooting" in summaries["support"].lower()
    assert all(term in summaries["dotnet"] for term in ["C#", "ASP.NET Core", "SQL Server"])
    assert len(set(summaries.values())) == len(summaries)
    assert scenarios["data"][0].target_emphasis.role_family == "Data Engineering"
    assert scenarios["ai"][0].target_emphasis.role_family == "AI / Generative AI Engineering"
    assert scenarios["support"][0].target_emphasis.role_family == "Production Support / Application Maintenance"
    assert scenarios["java"][0].target_emphasis.role_family == "Java Backend Development"
    assert scenarios["data"][0].debug_diagnostics.selected_signals


def test_summary_validation_flags_reused_generic_summary_shape() -> None:
    _, _, _, planner = planner_for(analysis(keyword("Python"), keyword("Azure Data Factory"), keyword("Databricks")))
    planner = planner.model_copy(
        update={
            "target_emphasis": planner.target_emphasis.model_copy(update={"role_family": "Data Engineering"}),
            "debug_diagnostics": planner.debug_diagnostics.model_copy(update={"variation_score": 0.1}),
        }
    )
    generated = SummaryGenerationResult(
        summary=(
            "Senior Full Stack .NET Developer with 9+ years of experience building and maintaining enterprise applications using SQL Server. "
            "Experienced in requirements analysis, debugging, and technical documentation across Agile delivery teams. "
            "Translates business requirements into reliable, maintainable software through clear implementation and team communication."
        ),
        usedEvidenceIds=list(planner.evidence_ids)[:1],
        usedSignals=["SQL Server"],
        excludedSignals=[],
        riskFlags=[],
    )

    validation = validate_summary_result(generated, planner)

    assert validation.is_valid is False
    assert SummaryValidationCode.reused_generic_summary in validation.validation_codes
    assert SummaryValidationCode.low_signal_variation in validation.validation_codes
