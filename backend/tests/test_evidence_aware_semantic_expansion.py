from app.schemas.resume import GenerateResumeRequest
from app.services.llm import build_jd_intelligence_from_rules, build_job_analysis_response


def analysis_for(job_description: str, target_role: str = "Software Engineer") -> set[str]:
    payload = GenerateResumeRequest(
        job_description=job_description,
        target_role=target_role,
        target_company="Target Company",
        level="Senior",
    )
    intelligence = build_jd_intelligence_from_rules(payload)
    response = build_job_analysis_response(payload, intelligence)
    return {item.value.lower() for item in response.explicit_keywords}


def assert_not_explicit(terms: set[str], unexpected: set[str]) -> None:
    assert not {item.lower() for item in unexpected}.intersection(terms)


def test_cloud_platforms_stays_broad_without_specific_cloud_products() -> None:
    terms = analysis_for("Experience working with cloud platforms.")

    assert "cloud platforms" in terms
    assert_not_explicit(
        terms,
        {"Azure", "AWS", "GCP", "Docker", "Kubernetes", "Azure DevOps"},
    )


def test_named_cloud_platforms_are_explicit() -> None:
    terms = analysis_for("Experience with Azure and AWS cloud platforms.")

    assert "azure" in terms
    assert "aws" in terms
    assert "cloud platforms" in terms
    assert "gcp" not in terms


def test_testing_and_cicd_best_practices_do_not_expand_to_test_tools() -> None:
    terms = analysis_for("Follow testing and CI/CD best practices.")

    assert "testing best practices" in terms or "testing" in terms
    assert "ci/cd" in terms
    assert_not_explicit(
        terms,
        {"MSTest", "MS-Test", "NUnit", "Regression Testing", "Unit Testing"},
    )


def test_named_unit_testing_and_nunit_are_explicit() -> None:
    terms = analysis_for("Write unit tests using NUnit.")

    assert "unit testing" in terms
    assert "nunit" in terms


def test_web_technologies_and_application_frameworks_stay_broad() -> None:
    terms = analysis_for("Experience with modern web technologies and application frameworks.")

    assert "modern web technologies" in terms
    assert "application frameworks" in terms
    assert_not_explicit(terms, {"React", "Angular", "ASP.NET Core", "MVC"})


def test_named_aspnet_core_mvc_is_explicit() -> None:
    terms = analysis_for("Build applications using ASP.NET Core MVC.")

    assert "asp.net core" in terms
    assert "mvc" in terms


def test_databases_stays_broad_without_specific_database_products() -> None:
    terms = analysis_for("Experience with databases.")

    assert "databases" in terms
    assert_not_explicit(terms, {"SQL Server", "MS SQL Server", "PostgreSQL", "Oracle"})


def test_named_databases_are_explicit() -> None:
    terms = analysis_for("Experience with SQL Server and PostgreSQL databases.")

    assert "ms sql server" in terms or "sql server" in terms
    assert "postgresql" in terms
    assert "databases" in terms


def test_version_control_and_cicd_do_not_expand_to_specific_tools() -> None:
    terms = analysis_for("Experience with version control and CI/CD.")

    assert "version control" in terms
    assert "ci/cd" in terms
    assert_not_explicit(terms, {"Git", "GitHub Actions", "Jenkins", "Azure DevOps"})


def test_named_git_and_jenkins_are_explicit() -> None:
    terms = analysis_for("Experience using Git and Jenkins.")

    assert "git" in terms
    assert "jenkins" in terms


def test_trading_jd_preserves_broad_terms_without_unsupported_specifics() -> None:
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

    terms = analysis_for(job_description, "Senior Software Engineer")

    expected = {
        "c#",
        ".net",
        "python",
        "object-oriented development",
        "cloud platforms",
        "databases",
        "application frameworks",
        "modern web technologies",
        "ci/cd",
        "version control",
        "testing best practices",
        "code review",
        "financial services",
        "trading",
        "valuation",
        "research applications",
        "front-office applications",
        "technical leadership",
        "stakeholder collaboration",
        "troubleshooting",
        "problem solving",
    }
    assert expected.issubset(terms)
    assert_not_explicit(
        terms,
        {
            "Azure",
            "AWS",
            "GCP",
            "Azure DevOps",
            "Docker",
            "Kubernetes",
            "ASP.NET Core",
            "MVC",
            "MSTest",
            "MS-Test",
            "NUnit",
            "Jest",
            "Regression Testing",
            "Integration Testing",
            "Test Automation",
            "Jenkins",
            "GitHub Actions",
            "SQL Server",
            "MS SQL Server",
            "PostgreSQL",
            "Oracle",
        },
    )
