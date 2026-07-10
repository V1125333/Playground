from app.schemas.resume import JobKeywordAnalysisItem, GenerateResumeRequest
from app.services.llm import (
    build_jd_intelligence_from_rules,
    build_job_analysis_response,
    dedupe_analysis_items,
    normalize_keyword,
)


def keyword(
    value: str,
    *,
    source_type: str = "inferred",
    confidence: str = "medium",
    priority: str = "medium",
    priority_score: int = 50,
    direct_from_jd: bool = False,
    source_sentence: str | None = None,
    category: str = "General",
) -> JobKeywordAnalysisItem:
    return JobKeywordAnalysisItem(
        id=value.lower().replace(" ", "-"),
        value=value,
        normalizedValue=value,
        term=value,
        category=category,
        sourceType=source_type,
        confidence=confidence,
        priority=priority,
        priorityScore=priority_score,
        directFromJD=direct_from_jd,
        evidenceText=source_sentence,
        sourceSentence=source_sentence,
        occurrenceCount=1,
    )


def values(items: list[JobKeywordAnalysisItem]) -> list[str]:
    return [item.value for item in items]


def test_code_review_variants_merge() -> None:
    merged = dedupe_analysis_items([keyword("Code Review"), keyword("Code Reviews")])

    assert values(merged) == ["Code Review"]
    assert merged[0].occurrence_count == 2


def test_cicd_variants_merge() -> None:
    merged = dedupe_analysis_items(
        [
            keyword("continuous integration and continuous delivery"),
            keyword("CI/CD"),
            keyword("ci cd"),
        ]
    )

    assert values(merged) == ["CI/CD"]


def test_object_oriented_variants_merge() -> None:
    merged = dedupe_analysis_items(
        [
            keyword("object oriented programming"),
            keyword("Object-Oriented Development"),
            keyword("OOP"),
        ]
    )

    assert values(merged) == ["Object-Oriented Development"]


def test_stakeholder_variants_merge() -> None:
    merged = dedupe_analysis_items(
        [
            keyword("Stakeholder Engagement"),
            keyword("Stakeholder Collaboration"),
            keyword("Business Stakeholder Collaboration"),
        ]
    )

    assert values(merged) == ["Stakeholder Collaboration"]


def test_analytical_problem_solving_is_not_over_merged() -> None:
    merged = dedupe_analysis_items(
        [
            keyword("Problem Solving"),
            keyword("Problem-Solving Skills"),
            keyword("Analytical Problem Solving"),
        ]
    )

    assert values(merged) == ["Problem Solving", "Analytical Problem Solving"]


def test_cloud_platforms_and_azure_remain_separate() -> None:
    merged = dedupe_analysis_items([keyword("Cloud Platforms"), keyword("Azure")])

    assert set(values(merged)) == {"Cloud Platforms", "Azure"}


def test_testing_best_practices_and_unit_testing_remain_separate() -> None:
    merged = dedupe_analysis_items([keyword("Testing Best Practices"), keyword("Unit Testing")])

    assert set(values(merged)) == {"Testing Best Practices", "Unit Testing"}


def test_technical_leadership_and_knowledge_sharing_remain_separate() -> None:
    merged = dedupe_analysis_items([keyword("Technical Leadership"), keyword("Knowledge Sharing")])

    assert set(values(merged)) == {"Technical Leadership", "Knowledge Sharing"}


def test_source_type_precedence_preserves_explicit() -> None:
    merged = dedupe_analysis_items(
        [
            keyword("Code Review", source_type="suggested", priority="low", priority_score=20),
            keyword("Code Reviews", source_type="explicit", direct_from_jd=True, priority="high", priority_score=90),
        ]
    )

    assert values(merged) == ["Code Review"]
    assert merged[0].source_type == "explicit"
    assert merged[0].direct_from_jd is True


def test_confidence_precedence_preserves_high() -> None:
    merged = dedupe_analysis_items(
        [
            keyword("Stakeholder Collaboration", confidence="low"),
            keyword("Stakeholder Engagement", confidence="high"),
        ]
    )

    assert values(merged) == ["Stakeholder Collaboration"]
    assert merged[0].confidence == "high"


def test_evidence_merging_keeps_unique_source_sentences() -> None:
    first = "Support code reviews for service changes."
    second = "Participate in peer code reviews before deployment."
    merged = dedupe_analysis_items(
        [
            keyword("Code Review", source_sentence=first),
            keyword("Code Reviews", source_sentence=second),
        ]
    )

    assert values(merged) == ["Code Review"]
    assert merged[0].occurrence_count == 2
    assert first in (merged[0].source_sentence or "")
    assert second in (merged[0].source_sentence or "")


def test_identical_source_sentence_is_not_double_counted() -> None:
    sentence = "Support code reviews for service changes."
    merged = dedupe_analysis_items(
        [
            keyword("Code Review", source_sentence=sentence),
            keyword("Code Reviews", source_sentence=sentence),
        ]
    )

    assert values(merged) == ["Code Review"]
    assert merged[0].occurrence_count == 1


def test_normalize_keyword_safe_aliases() -> None:
    assert normalize_keyword("dotnet") == ".NET"
    assert normalize_keyword("c sharp") == "C#"
    assert normalize_keyword("problem-solving skills") == "Problem Solving"


def test_original_trading_jd_does_not_emit_semantic_duplicates() -> None:
    job_description = """
    Responsibilities:
    Design, develop, and enhance front-office applications that support trading, valuation, and research activities.
    Build scalable, reliable, and high-performing software solutions using modern development frameworks.
    Create clean, maintainable code while adhering to testing, version control, and CI/CD best practices.
    Document system designs, support code reviews, and contribute to ongoing process and quality improvements.
    Analyze existing workflows and develop technology solutions that improve operational efficiency.
    Partner with business users, technology teams, and stakeholders to gather requirements and deliver effective applications.
    Provide technical leadership and guidance to developers while promoting collaboration and knowledge sharing.
    Stay current with emerging technologies and apply new approaches that strengthen application performance and business value.

    Qualifications:
    Bachelor's degree in Computer Science or a related field with 7+ years of professional software development experience.
    Strong experience with object-oriented development using C#/.NET and scripting or data-focused development using Python.
    Proven ability to build scalable enterprise applications, preferably within financial services, trading, or investment environments.
    Experience working with modern web technologies, cloud platforms, databases, and application frameworks.
    Strong analytical, troubleshooting, and problem-solving skills with a focus on practical solutions.
    Effective communication skills and the ability to collaborate with both technical and business stakeholders.
    """
    payload = GenerateResumeRequest(
        job_description=job_description,
        target_role="Senior Software Engineer",
        target_company="Target Company",
        level="Senior",
    )
    response = build_job_analysis_response(payload, build_jd_intelligence_from_rules(payload))
    terms = values(response.explicit_keywords)

    assert len(terms) == len(set(terms))
    assert not {"Code Review", "Code Reviews"}.issubset(set(terms))
    assert not {"Stakeholders", "Stakeholder Collaboration"}.issubset(set(terms))
    assert not {"Deployment", "Deployments"}.issubset(set(terms))
    assert not {"CI/CD", "Continuous Integration and Delivery"}.issubset(set(terms))
    assert not {"Problem Solving", "Problem-Solving Skills"}.issubset(set(terms))
