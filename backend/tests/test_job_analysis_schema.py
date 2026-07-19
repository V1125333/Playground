import pytest
from pydantic import ValidationError

from app.schemas.resume import JobAnalysisResponse, JobKeywordAnalysisItem
from app.schemas.resume import GenerateResumeRequest
from app.services.llm import build_jd_intelligence_from_rules, build_job_analysis_response


def test_valid_explicit_keyword() -> None:
    item = JobKeywordAnalysisItem(
        id="languages:c-sharp",
        value="C#",
        normalizedValue="c#",
        category="Languages",
        sourceType="explicit",
        confidence="high",
        priority="high",
        priorityScore=95,
        directFromJD=True,
        evidenceText="Experience with C#/.NET",
        occurrenceCount=1,
    )

    assert item.source_type == "explicit"
    assert item.direct_from_jd is True
    assert item.term == "C#"


def test_valid_inferred_keyword() -> None:
    item = JobKeywordAnalysisItem(
        id="leadership:developer-mentoring",
        value="Developer Mentoring",
        normalizedValue="developer mentoring",
        category="Leadership",
        sourceType="inferred",
        confidence="medium",
        priority="medium",
        priorityScore=60,
        directFromJD=False,
    )

    assert item.source_type == "inferred"
    assert item.direct_from_jd is False


def test_valid_suggested_keyword() -> None:
    item = JobKeywordAnalysisItem(
        id="cloud:azure",
        value="Azure",
        normalizedValue="azure",
        category="Cloud",
        sourceType="suggested",
        confidence="low",
        priority="low",
        priorityScore=25,
        directFromJD=False,
        reason="Cloud platform was mentioned, but Azure was not named.",
    )

    assert item.source_type == "suggested"


def test_priority_score_below_zero_fails() -> None:
    with pytest.raises(ValidationError):
        JobKeywordAnalysisItem(
            id="bad:score",
            value="Bad",
            normalizedValue="bad",
            category="General",
            sourceType="inferred",
            confidence="medium",
            priority="medium",
            priorityScore=-1,
            directFromJD=False,
        )


def test_priority_score_above_one_hundred_fails() -> None:
    with pytest.raises(ValidationError):
        JobKeywordAnalysisItem(
            id="bad:score",
            value="Bad",
            normalizedValue="bad",
            category="General",
            sourceType="inferred",
            confidence="medium",
            priority="medium",
            priorityScore=101,
            directFromJD=False,
        )


def test_occurrence_count_below_one_fails() -> None:
    with pytest.raises(ValidationError):
        JobKeywordAnalysisItem(
            id="bad:count",
            value="Bad",
            normalizedValue="bad",
            category="General",
            sourceType="inferred",
            confidence="medium",
            priority="medium",
            priorityScore=50,
            directFromJD=False,
            occurrenceCount=0,
        )


def test_suggested_direct_from_jd_true_fails() -> None:
    with pytest.raises(ValidationError):
        JobKeywordAnalysisItem(
            id="cloud:azure",
            value="Azure",
            normalizedValue="azure",
            category="Cloud",
            sourceType="suggested",
            confidence="low",
            priority="low",
            priorityScore=25,
            directFromJD=True,
        )


def test_existing_api_response_can_still_be_parsed() -> None:
    response = JobAnalysisResponse(
        roleInformation={"title": "Software Engineer", "seniority": "Senior"},
        technicalSkills={
            "languages": [
                {
                    "term": "C#",
                    "category": "Languages",
                    "priority": "critical",
                    "priorityScore": 9,
                    "recruiterWeight": 8,
                    "confidence": 0.95,
                    "explicit": True,
                }
            ]
        },
        explicitAtsKeywords=[
            {
                "term": ".NET",
                "category": "Frameworks",
                "priority": "important",
                "priorityScore": 8,
                "recruiterWeight": 8,
                "confidence": 0.85,
                "explicit": True,
            }
        ],
    )

    language = response.technical_skills["languages"][0]
    keyword = response.explicit_ats_keywords[0]

    assert language.value == "C#"
    assert language.priority_score == 90
    assert language.priority == "high"
    assert keyword.value == ".NET"
    assert keyword.priority_score == 80


def test_typed_requirements_keep_education_and_years_out_of_legacy_keywords() -> None:
    payload = GenerateResumeRequest(
        job_description=(
            "Bachelor's degree in Computer Science required. "
            "5 years of experience required. "
            "Strong hands-on experience with C#, .NET Framework, SQL Server, and databases."
        ),
        target_role="Software Engineer",
        target_company="Acme",
        level="Senior",
    )

    response = build_job_analysis_response(payload, build_jd_intelligence_from_rules(payload))
    legacy_terms = {item.value for item in response.keywords}

    assert [item.canonical_term for item in response.education_requirements] == ["Bachelor's Degree"]
    assert [item.canonical_term for item in response.experience_requirements] == ["5 Years of Experience"]
    assert "Bachelor's Degree" not in legacy_terms
    assert "5 Years of Experience" not in legacy_terms
    assert "education - bachelor" not in {item.normalized_value for item in response.keywords}


def test_typed_requirements_keep_databases_separate_from_sql_server() -> None:
    payload = GenerateResumeRequest(
        job_description="Design and optimize SQL Server databases, queries, views, and stored procedures.",
        target_role="Software Engineer",
        target_company="Acme",
        level="Senior",
    )

    response = build_job_analysis_response(payload, build_jd_intelligence_from_rules(payload))
    technical_terms = [item.canonical_term for item in response.technical_requirements]
    legacy_terms = [item.value for item in response.keywords]

    assert "MS SQL Server" in technical_terms or "SQL Server" in technical_terms
    assert "Databases" in technical_terms
    assert "Databases" in legacy_terms


def test_phase_one_normalizes_microsoft_sql_server_without_fragments() -> None:
    payload = GenerateResumeRequest(
        job_description="Strong hands-on experience with Microsoft SQL Server.",
        target_role="Software Engineer",
        target_company="Acme",
        level="Senior",
    )

    response = build_job_analysis_response(payload, build_jd_intelligence_from_rules(payload))
    technical_terms = [item.canonical_term for item in response.technical_requirements]
    legacy_terms = [item.value for item in response.keywords]

    assert technical_terms.count("MS SQL Server") == 1
    assert legacy_terms.count("MS SQL Server") == 1
    assert "Microsoft Sql" not in technical_terms
    assert "microsoft-sql" not in {item.normalized_value for item in response.keywords}


def test_phase_one_keeps_databases_distinct_without_such_as_sql_fragment() -> None:
    payload = GenerateResumeRequest(
        job_description="Experience with relational databases such as SQL Server.",
        target_role="Software Engineer",
        target_company="Acme",
        level="Senior",
    )

    response = build_job_analysis_response(payload, build_jd_intelligence_from_rules(payload))
    technical_terms = [item.canonical_term for item in response.technical_requirements]
    legacy_terms = [item.value for item in response.keywords]

    assert "MS SQL Server" in technical_terms
    assert "Databases" in technical_terms
    assert "Such As Sql" not in technical_terms
    assert "Such As Sql" not in legacy_terms


def test_phase_one_extracts_spelled_out_years_as_typed_experience_requirement() -> None:
    payload = GenerateResumeRequest(
        job_description="Bachelor's degree and five years of professional software engineering experience required.",
        target_role="Software Engineer",
        target_company="Acme",
        level="Senior",
    )

    response = build_job_analysis_response(payload, build_jd_intelligence_from_rules(payload))
    legacy_terms = {item.value for item in response.keywords}

    assert [item.canonical_term for item in response.education_requirements] == ["Bachelor's Degree"]
    assert [item.canonical_term for item in response.experience_requirements] == ["5 Years of Experience"]
    assert "Bachelor's Degree" not in legacy_terms
    assert "5 Years of Experience" not in legacy_terms


def test_phase_one_merges_restful_and_web_api_aliases() -> None:
    payload = GenerateResumeRequest(
        job_description="Build RESTful APIs and Web APIs for enterprise applications.",
        target_role="Software Engineer",
        target_company="Acme",
        level="Senior",
    )

    response = build_job_analysis_response(payload, build_jd_intelligence_from_rules(payload))
    technical_terms = [item.canonical_term for item in response.technical_requirements]
    legacy_terms = [item.value for item in response.keywords]

    assert technical_terms.count("REST API") == 1
    assert legacy_terms.count("REST API") == 1
    assert "Rest" not in technical_terms
    assert "Rest Apis" not in technical_terms
    assert "Restful Apis" not in technical_terms
    assert "Web Apis" not in technical_terms


def test_phase_one_merges_rest_apis_plural_alias() -> None:
    payload = GenerateResumeRequest(
        job_description="Lead full-stack development using REST APIs, C#, and SQL Server.",
        target_role="Software Engineer",
        target_company="Acme",
        level="Senior",
    )

    response = build_job_analysis_response(payload, build_jd_intelligence_from_rules(payload))
    technical_terms = [item.canonical_term for item in response.technical_requirements]
    legacy_terms = [item.value for item in response.keywords]

    assert technical_terms.count("REST API") == 1
    assert legacy_terms.count("REST API") == 1
    assert "Rest" not in technical_terms
    assert "Rest Apis" not in technical_terms


def test_phase_one_does_not_expand_azure_to_specific_services() -> None:
    payload = GenerateResumeRequest(
        job_description="Experience with Azure is preferred.",
        target_role="Software Engineer",
        target_company="Acme",
        level="Senior",
    )

    response = build_job_analysis_response(payload, build_jd_intelligence_from_rules(payload))
    technical_terms = {item.canonical_term for item in response.technical_requirements}

    assert "Azure" in technical_terms
    assert "Azure Is" not in technical_terms
    assert "Azure DevOps" not in technical_terms
    assert "Azure SQL" not in technical_terms
    assert "Azure Functions" not in technical_terms


def test_phase_one_testing_best_practices_does_not_infer_specific_test_tools() -> None:
    payload = GenerateResumeRequest(
        job_description="Adhering to testing best practices is required.",
        target_role="Software Engineer",
        target_company="Acme",
        level="Senior",
    )

    response = build_job_analysis_response(payload, build_jd_intelligence_from_rules(payload))
    technical_terms = {item.canonical_term for item in response.technical_requirements}

    assert "Testing Best Practices" in technical_terms
    assert "Adhering" not in technical_terms
    assert {"MSTest", "NUnit", "Jest", "Jasmine"}.isdisjoint(technical_terms)
