from app.schemas.resume import GenerateResumeRequest
from app.services.llm import (
    build_jd_intelligence_from_rules,
    build_job_analysis_response,
    calculate_keyword_priority,
)


def keywords_for(job_description: str, target_role: str = "Software Engineer"):
    payload = GenerateResumeRequest(
        job_description=job_description,
        target_role=target_role,
        target_company="Target Company",
        level="Senior",
    )
    return build_job_analysis_response(payload, build_jd_intelligence_from_rules(payload)).keywords


def keyword_map(job_description: str, target_role: str = "Software Engineer"):
    return {item.value: item for item in keywords_for(job_description, target_role)}


def test_core_required_technology_scores_high() -> None:
    items = keyword_map("Strong experience with C# and .NET is required.")

    assert items["C#"].priority == "high"
    assert items[".NET"].priority == "high"
    assert items["C#"].priority_score >= 70
    assert items[".NET"].priority_score >= 70


def test_preferred_language_is_not_high_by_category_alone() -> None:
    python = keyword_map("Python experience is preferred.")["Python"]

    assert python.priority in {"medium", "low"}
    assert python.priority_score < 70


def test_generic_explicit_competency_is_medium() -> None:
    communication = keyword_map("Strong communication skills are required.")["Communication Skills"]

    assert communication.source_type == "explicit"
    assert communication.priority == "medium"


def test_supporting_engineering_practice_is_not_high() -> None:
    code_review = keyword_map("Participate in code reviews.")["Code Review"]

    assert code_review.source_type == "explicit"
    assert code_review.priority in {"medium", "low"}
    assert code_review.priority_score < 70


def test_repeated_role_defining_domain_scores_high() -> None:
    trading = keyword_map(
        "Build trading systems. Support trading applications. Experience in trading environments is required."
    )["Trading"]

    assert trading.priority == "high"
    assert trading.occurrence_count >= 2


def test_broad_category_scores_medium() -> None:
    cloud = keyword_map("Experience with cloud platforms.")["Cloud Platforms"]

    assert cloud.source_type == "explicit"
    assert cloud.priority == "medium"


def test_specific_required_platform_scores_high() -> None:
    azure = keyword_map("Strong Azure experience is required.")["Azure"]

    assert azure.priority == "high"


def test_suggested_terms_cannot_exceed_low_priority_cap() -> None:
    result = calculate_keyword_priority(
        term="Azure",
        category="Cloud",
        source_type="suggested",
        direct_from_jd=False,
        source_sentence="Experience with cloud platforms.",
        job_description="Experience with cloud platforms.",
        target_role="Software Engineer",
    )

    assert result.score <= 30
    assert result.priority == "low"


def test_inferred_leadership_is_normally_medium_not_high() -> None:
    leadership = keyword_map("Guide junior developers and promote knowledge sharing.")[
        "Technical Leadership"
    ]

    assert leadership.priority == "medium"
    assert leadership.priority_score < 70


def test_years_of_experience_scores_high() -> None:
    experience = keyword_map("7+ years of professional software development experience.")[
        "7+ Years of Experience"
    ]

    assert experience.priority == "high"


def test_required_scores_above_preferred() -> None:
    items = keyword_map("C# is required. Python is preferred.")

    assert items["C#"].priority == "high"
    assert items["Python"].priority in {"medium", "low"}
    assert items["C#"].priority_score > items["Python"].priority_score


def test_qualifications_score_above_responsibility_documentation() -> None:
    items = keyword_map(
        """
        Responsibilities:
        Document system designs.

        Qualifications:
        Strong experience with C#/.NET.
        """
    )

    documentation_score = max(
        (item.priority_score for item in items.values() if item.value in {"Documentation", "System Designs"}),
        default=0,
    )
    assert items["C#"].priority_score > documentation_score
    assert items[".NET"].priority_score > documentation_score


def test_original_jd_priority_distribution_is_selective_and_deterministic() -> None:
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
    first = keywords_for(job_description, "Senior Software Engineer")
    second = keywords_for(job_description, "Senior Software Engineer")
    first_by_value = {item.value: item for item in first}

    visible_count = len(first)
    high_count = sum(1 for item in first if item.priority == "high")
    assert high_count / visible_count <= 0.4
    assert all(item.priority != "high" for item in first if item.source_type == "suggested")
    assert all(0 <= item.priority_score <= 100 for item in first)
    assert [(item.value, item.priority_score) for item in first] == [
        (item.value, item.priority_score) for item in second
    ]

    for core in ("C#", ".NET", "Python", "Trading", "Financial Services"):
        assert first_by_value[core].priority_score > first_by_value["Communication Skills"].priority_score
        assert first_by_value[core].priority_score > first_by_value["Code Review"].priority_score
