from app.schemas.resume import GenerateResumeRequest
from app.services.llm import (
    build_jd_intelligence_from_rules,
    build_job_analysis_response,
    extract_jd_intelligence_with_openai,
    is_generic_standalone_keyword,
)


def explicit_terms(job_description: str, target_role: str = "Software Engineer") -> set[str]:
    payload = GenerateResumeRequest(
        job_description=job_description,
        target_role=target_role,
        target_company="Target Company",
        level="Senior",
    )
    response = build_job_analysis_response(payload, build_jd_intelligence_from_rules(payload))
    return {item.value for item in response.explicit_keywords}


def test_prompt_contains_grounded_extraction_rules() -> None:
    names = extract_jd_intelligence_with_openai.__code__.co_names
    constants = " ".join(str(item) for item in extract_jd_intelligence_with_openai.__code__.co_consts)

    assert "chat_completion" in names
    assert "evidence-grounded JD Intelligence Extraction" in constants
    assert "never invent products" in constants
    assert "Cloud Platforms" in constants
    assert "job-analysis-v4-grounded-extraction" in constants


def test_cloud_and_database_broad_terms_do_not_expand_to_products() -> None:
    terms = explicit_terms("Experience working with cloud platforms and databases.")

    assert {"Cloud Platforms", "Databases"}.issubset(terms)
    assert not {"Azure", "AWS", "GCP", "SQL Server", "PostgreSQL"}.intersection(terms)


def test_direct_technologies_are_extracted() -> None:
    terms = explicit_terms("Strong experience with C#/.NET and Python.")

    assert {"C#", ".NET", "Python"}.issubset(terms)


def test_testing_version_control_and_cicd_stay_broad() -> None:
    terms = explicit_terms("Adhere to testing, version control, and CI/CD best practices.")

    assert {"Testing Best Practices", "Version Control", "CI/CD"}.issubset(terms)
    assert not {"Best Practices", "MSTest", "NUnit", "Git", "Jenkins"}.intersection(terms)


def test_guidance_and_knowledge_sharing_are_meaningful_terms() -> None:
    terms = explicit_terms("Provide technical guidance to developers and promote knowledge sharing.")

    assert "Technical Leadership" in terms
    assert "Knowledge Sharing" in terms
    assert not {"Developers", "Guidance", "Teams"}.intersection(terms)


def test_requirements_gathering_and_stakeholder_collaboration() -> None:
    terms = explicit_terms("Partner with business users, technology teams, and stakeholders to gather requirements.")

    assert {"Requirements Gathering", "Stakeholder Collaboration"}.issubset(terms)
    assert not {"Business Users", "Technology Teams", "Stakeholders", "Requirements"}.intersection(terms)


def test_scalable_reliable_high_performing_phrase_cleanup() -> None:
    terms = explicit_terms("Build scalable, reliable, and high-performing software solutions.")

    assert {"High-Performance Software"}.intersection(terms)
    assert not {"Scalable", "Reliable", "High Performing", "Software", "Solutions"}.intersection(terms)


def test_web_technologies_and_frameworks_stay_broad() -> None:
    terms = explicit_terms("Experience with modern web technologies and application frameworks.")

    assert {"Modern Web Technologies", "Application Frameworks"}.issubset(terms)
    assert not {"React", "Angular", "ASP.NET Core", "MVC"}.intersection(terms)


def test_named_framework_and_cloud_are_explicit() -> None:
    terms = explicit_terms("Experience with ASP.NET Core MVC and Azure.")

    assert {"ASP.NET Core", "MVC", "Azure"}.issubset(terms)


def test_generic_standalone_cleanup() -> None:
    retained = {"Code Review", "Requirements Gathering"}
    rejected = {"Best Practices", "Applications", "Software"}

    assert all(not is_generic_standalone_keyword(term) for term in retained)
    assert all(is_generic_standalone_keyword(term) for term in rejected)


def test_original_financial_services_jd_grounded_extraction() -> None:
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
    terms = explicit_terms(job_description, "Senior Software Engineer")

    expected = {
        "C#",
        ".NET",
        "Python",
        "Object-Oriented Development",
        "Financial Services",
        "Trading",
        "Valuation",
        "Research Applications",
        "front-office applications",
        "Testing Best Practices",
        "Version Control",
        "CI/CD",
        "Code Review",
        "Technical Leadership",
        "Knowledge Sharing",
        "Requirements Gathering",
        "Stakeholder Collaboration",
        "Communication Skills",
        "Workflow Analysis",
        "Operational Efficiency",
        "Troubleshooting",
        "Problem Solving",
        "Quality Improvement",
        "Bachelor's Degree",
        "7+ Years of Experience",
    }
    unsupported = {
        "Azure",
        "AWS",
        "GCP",
        "Docker",
        "Kubernetes",
        "Azure DevOps",
        "ASP.NET Core",
        "MVC",
        "MSTest",
        "NUnit",
        "Jest",
        "Regression Testing",
        "Jenkins",
        "GitHub Actions",
        "SQL Server",
        "PostgreSQL",
        "Oracle",
    }
    weak = {
        "Best Practices",
        "Applications",
        "Solutions",
        "Development",
        "Technologies",
        "Software",
        "Teams",
        "Stakeholders",
        "Requirements",
    }

    assert expected.issubset(terms)
    assert not unsupported.intersection(terms)
    assert not weak.intersection(terms)
