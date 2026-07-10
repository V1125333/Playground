from app.services.ats_scoring import extract_job_keywords, infer_role_context
from app.services.llm import build_jd_intelligence_from_rules, extract_metric_phrases
from app.schemas.resume import GenerateResumeRequest


def terms_for(job_description: str) -> list[str]:
    return [term for term, _weight in extract_job_keywords(job_description)]


def test_velera_style_jd_extracts_role_specific_keywords_without_fragments() -> None:
    job_description = """
    Software Engineer IV (Full Stack .Net)
    Work across the SDLC, code review, design review, technical specifications,
    technical documentation, secure application development, audit, and
    regulatory compliance. Perform as a subject matter expert, provide
    engineering leadership and mentorship, lead delivery, and collaborate with
    architects. Advanced experience in Azure. Expert-level full-stack engineer
    with databases, API, front-end, back-end, data structures, and algorithms.
    """

    inference = infer_role_context(job_description)
    extracted = terms_for(job_description)

    assert inference.seniority == "senior_lead"
    assert {".NET", "C#", "full-stack"}.issubset(set(inference.core_stack))
    assert {
        ".NET",
        "C#",
        "full-stack",
        "SDLC",
        "code review",
        "security",
        "regulatory compliance",
        "technical specifications",
        "mentorship",
        "subject matter expert",
    }.issubset(set(extracted))
    assert not {
        "Ten",
        "Ensure",
        "Skills",
        "Mastery",
        "Existing code",
        "All the audit",
        "Computer Engineering",
        "Software Development",
    }.intersection(extracted)


def test_python_data_engineer_jd_does_not_leak_dotnet_terms() -> None:
    job_description = """
    Senior Python Data Engineer
    Build and operate data pipelines for analytics delivery using Python,
    Apache Spark, Airflow, dbt, Snowflake, AWS Glue, and S3. Own data modeling,
    orchestration, lineage, and data quality checks. Partner with product
    managers and mentor engineers.
    """

    inference = infer_role_context(job_description)
    extracted = terms_for(job_description)

    assert inference.role_type == "senior python data engineer"
    assert {"Python", "Apache Spark", "Airflow", "dbt", "Snowflake", "AWS Glue"}.issubset(set(extracted))
    assert ".NET" not in extracted
    assert "C#" not in extracted
    assert "operate data" not in {term.lower() for term in extracted}
    assert "own data" not in {term.lower() for term in extracted}


def test_jd_intelligence_fallback_prioritizes_categories_and_excludes_noise() -> None:
    job_description = """
    Software Engineer IV (Full Stack .Net)
    Build secure scalable applications in an Azure cloud environment. Review
    technical specifications, participate in peer code reviews, support SDLC
    release management, audit and regulatory compliance, and engineering
    leadership as needed. Azure highly preferred. Perform other duties.
    """

    intelligence = build_jd_intelligence_from_rules(
        GenerateResumeRequest(
            job_description=job_description,
            target_role="Software Engineer IV",
            target_company="Velera",
            level="Senior",
        )
    )
    all_terms = {term.lower() for term in terms_from_intelligence(intelligence)}

    assert ".net" in all_terms
    assert "c#" in all_terms
    assert any(term in all_terms for term in {"azure", "microsoft azure", "cloud"})
    assert "technical specifications" in all_terms
    assert "code review" in all_terms or "peer code reviews" in all_terms
    assert "regulatory compliance" in all_terms
    assert "engineering leadership" in all_terms
    assert "azure highly" not in all_terms
    assert "other duties" not in all_terms


def test_numbered_raw_notes_do_not_become_metric_phrases() -> None:
    notes = """
    1. Developed and maintained web applications using ASP.NET Core and React, improving system reliability.
    2. Created and optimized stored procedures in MS SQL Server, reducing query execution time.
    3. Troubleshot application and database issues, implementing bug fixes and patches.
    Reduced query execution time by 35%; supported 4 release cycles.
    """

    metrics = extract_metric_phrases(notes)

    assert "Developed and maintained" not in " ".join(metrics)
    assert all(not item.startswith(("1.", "2.", "3.")) for item in metrics)
    assert any("35%" in item for item in metrics)
    assert any("4 release cycles" in item for item in metrics)


def terms_from_intelligence(intelligence) -> list[str]:
    return [
        keyword.term
        for field_name in (
            "critical_keywords",
            "important_keywords",
            "preferred_keywords",
            "hard_skills",
            "leadership_requirements",
            "security_compliance_requirements",
            "sdlc_delivery_requirements",
            "documentation_review_requirements",
        )
        for keyword in getattr(intelligence, field_name)
    ]
