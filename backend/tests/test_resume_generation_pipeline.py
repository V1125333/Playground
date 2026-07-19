from types import SimpleNamespace

from app.schemas.resume import (
    CandidateProfile,
    GenerateResumeRequest,
    JobAnalysisResponse,
    JobKeywordAnalysisItem,
    ResumeContact,
    ResumeCertification,
    ResumeEducation,
    ResumeExperience,
    ResumeProject,
    SkillCategory,
)
from app.services.profile_service import compute_profile_content_hash, ensure_profile_record_ids
from app.services.resume_generation_pipeline import (
    RESUME_GENERATION_ALGORITHM_VERSION,
    assemble_structured_resume,
    build_generation_context,
    select_relevant_profile_evidence,
    structured_to_resume_content,
)
from app.services.resume_validator import validate_structured_resume

def keyword(value: str, *, category: str = "General", priority: str = "high", score: int = 90, source_type: str = "explicit") -> JobKeywordAnalysisItem:
    return JobKeywordAnalysisItem(
        id=f"keyword-{value.lower().replace(' ', '-')}",
        value=value,
        normalizedValue=value,
        category=category,
        sourceType=source_type,
        confidence="high" if source_type == "explicit" else "low",
        priority=priority,
        priorityScore=score,
        directFromJD=source_type == "explicit",
        evidenceText=f"JD mentions {value}" if source_type == "explicit" else None,
        sourceSentence=f"JD mentions {value}" if source_type == "explicit" else None,
        occurrenceCount=1,
    )


def analysis(*items: JobKeywordAnalysisItem) -> JobAnalysisResponse:
    return JobAnalysisResponse(
        roleInformation={"title": "Software Engineer", "seniority": "Senior"},
        keywords=list(items),
        analysisHash="test-analysis",
    )


def profile_record(profile: CandidateProfile):
    stable = ensure_profile_record_ids(profile)
    return SimpleNamespace(
        profile_id="11111111-1111-1111-1111-111111111111",
        profile_version=1,
        content_hash=compute_profile_content_hash(stable),
        updated_at="2026-07-09T00:00:00+00:00",
        profile_data=stable,
    )


def candidate() -> CandidateProfile:
    return ensure_profile_record_ids(
        CandidateProfile(
            name="Venu Madhav Pendurthi",
            title="Senior .NET Developer",
            contact=ResumeContact(email="venu@example.com", phone="+12014436937", location="Hartford, CT"),
            skills=[SkillCategory(category="Technical Skills", items=["C#", ".NET", "AWS", "SQL Server"])],
            experience=[
                ResumeExperience(
                    company="Infosys",
                    role="Senior .NET Developer",
                    startDate="2021-01",
                    endDate="Present",
                    rawNotes="Led code reviews and built C# .NET APIs with SQL Server, improving processing time by 20%.",
                ),
                ResumeExperience(
                    company="Healthcare Co",
                    role=".NET Developer",
                    startDate="2018-01",
                    endDate="2020-12",
                    rawNotes="Supported healthcare provider portal workflows using .NET and SQL Server.",
                ),
            ],
            education=[ResumeEducation(degree="Bachelor of Technology in Computer Science", institution="JNTU")],
            projects=[ResumeProject(name="Provider Portal", bullets=["Built C# portal workflows."], technologies=["C#"])],
            certifications=[ResumeCertification(name="Scrum Fundamentals", issuer="Scrum Alliance")],
        )
    )


def resume_preferences(header_visibility: dict | None = None, section_visibility: dict | None = None) -> dict:
    return {
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
            **(header_visibility or {}),
        },
        "sectionVisibility": {
            "summary": True,
            "skills": True,
            "experience": True,
            "projects": True,
            "education": True,
            "certifications": True,
            **(section_visibility or {}),
        },
    }


def build_result(job_analysis, *, header_visibility: dict | None = None, section_visibility: dict | None = None):
    profile = candidate()
    profile.contact = ResumeContact(
        email="venu@example.com",
        phone="+12014436937",
        location="Hartford, CT",
        linkedin="https://linkedin.com/in/venu",
        github="https://github.com/venu",
        portfolio="https://venu.dev",
    )
    payload = GenerateResumeRequest(
        profileId="11111111-1111-1111-1111-111111111111",
        job_description="Need C#, .NET, Azure, Trading, Financial Services, Technical Leadership.",
        target_role="Software Engineer IV",
        target_company="Target",
        jobAnalysis=job_analysis,
        resumePreferences=resume_preferences(header_visibility, section_visibility),
    )
    context = build_generation_context(profile_record(profile), payload, job_analysis)
    selected = select_relevant_profile_evidence(context)
    structured = assemble_structured_resume(profile, payload, context, selected)
    validation = validate_structured_resume(structured, context.evidence_index, context.profile_match)
    resume = structured_to_resume_content(profile, structured)
    return profile, context, selected, structured, validation, resume


def test_exact_matched_skill_appears_and_unmatched_skill_does_not() -> None:
    _, _, _, _, _, resume = build_result(
        analysis(keyword("C#"), keyword(".NET"), keyword("Azure", category="Cloud"))
    )
    skills = [skill for group in resume.skills for skill in group.items]

    assert "C#" in skills
    assert ".NET" in skills
    assert "Azure" not in skills


def test_adjacent_skill_is_not_renamed_to_required_skill() -> None:
    _, context, _, structured, _, resume = build_result(analysis(keyword("Azure", category="Cloud")))
    skills = [skill for group in resume.skills for skill in group.items]

    assert "AWS" not in [match.requirement_value for match in context.profile_match.matched_requirements]
    assert "Azure" not in skills
    assert "AWS" in skills or not skills
    assert "Azure" in structured.missing_requirements


def test_generated_skills_are_grouped_for_resume_display() -> None:
    _, _, _, structured, _, resume = build_result(analysis(keyword("C#"), keyword(".NET"), keyword("SQL Server")))
    skills_section = next(section for section in structured.sections if section.type == "skills")
    categories = [group["category"] for group in skills_section.content]

    assert "Technical Skills" not in categories
    assert "Programming Languages" in categories
    assert "Backend Frameworks & Tools" in categories
    assert "Databases" in categories
    assert any(group.category == "Programming Languages" and "C#" in group.items for group in resume.skills)
    assert any(group.category == "Backend Frameworks & Tools" and ".NET" in group.items for group in resume.skills)


def test_compound_azure_skill_is_split_into_resume_friendly_items() -> None:
    profile = candidate()
    profile.skills = [
        SkillCategory(
            category="Cloud Platforms & Services",
            categoryId="cloud-platforms-services",
            categoryName="Cloud Platforms & Services",
            order=0,
            items=["Microsoft Azure (App Service, Azure SQL)"],
        )
    ]
    payload = GenerateResumeRequest(
        profileId="11111111-1111-1111-1111-111111111111",
        job_description="Need Azure cloud development.",
        target_role="Software Engineer IV",
        target_company="Target",
        jobAnalysis=analysis(keyword("Azure", category="Cloud")),
        resumePreferences=resume_preferences(),
    )
    context = build_generation_context(profile_record(profile), payload, payload.job_analysis)
    selected = select_relevant_profile_evidence(context)
    structured = assemble_structured_resume(profile, payload, context, selected)
    skills_section = next(section for section in structured.sections if section.type == "skills")

    assert skills_section.content == [
        {
            "category": "Cloud & Infrastructure",
            "items": ["Microsoft Azure", "Azure App Service", "Azure SQL Database"],
        }
    ]


def test_summary_includes_only_supported_domains() -> None:
    _, _, _, structured, _, _ = build_result(analysis(keyword("Trading", category="Domain")))
    summary = next(section.content for section in structured.sections if section.type == "summary")

    assert "Trading" not in summary


def test_existing_metric_is_preserved_and_no_new_metric_is_fabricated() -> None:
    _, _, _, _, validation, resume = build_result(analysis(keyword("C#"), keyword(".NET")))
    text = " ".join(bullet for role in resume.experience for bullet in role.bullets)

    assert "20%" in text
    assert "40%" not in text
    assert validation.is_valid is True


def test_bullets_use_same_role_evidence_and_valid_ids() -> None:
    _, context, _, structured, validation, resume = build_result(analysis(keyword("C#"), keyword("Technical Leadership", category="Leadership")))
    evidence_ids = {item.evidence_id for item in context.evidence_index}
    experience_section = next(section for section in structured.sections if section.type == "experience")

    assert resume.experience[0].bullets
    assert set(experience_section.provenance.supporting_evidence_ids) <= evidence_ids
    assert validation.is_valid is True


def test_unsupported_domains_are_missing_not_claimed() -> None:
    _, context, _, structured, _, _ = build_result(analysis(keyword("Trading", category="Domain"), keyword("Financial Services", category="Domain")))

    assert "Trading" in context.profile_match.gaps
    assert "Financial Services" in context.profile_match.gaps
    assert "Trading" in structured.missing_requirements


def test_education_values_remain_unchanged() -> None:
    _, _, _, structured, _, _ = build_result(analysis(keyword("Bachelor's Degree", category="Education")))
    education = next(section.content for section in structured.sections if section.type == "education")

    assert education[0]["degree"] == candidate().education[0].degree
    assert education[0]["institution"] == candidate().education[0].institution


def test_generation_algorithm_version_is_set() -> None:
    _, _, _, structured, _, _ = build_result(analysis(keyword("C#")))

    assert structured.generation_algorithm_version == RESUME_GENERATION_ALGORITHM_VERSION


def test_header_visibility_flags_build_structured_header_and_filter_contact() -> None:
    _, _, _, hidden, _, hidden_resume = build_result(
        analysis(keyword("C#")),
        header_visibility={
            "fullName": True,
            "currentTitle": False,
            "email": False,
            "phone": True,
            "location": False,
            "linkedinUrl": False,
            "githubUrl": False,
            "portfolioUrl": False,
        },
    )

    assert hidden.resume_header == {"fullName": "Venu Madhav Pendurthi", "phone": "+12014436937"}
    assert hidden.contact.email == ""
    assert hidden.contact.phone == "+12014436937"
    assert hidden.contact.location == ""
    assert hidden.contact.linkedin == ""
    assert hidden.contact.github == ""
    assert hidden.contact.portfolio == ""
    assert hidden_resume.name == "Venu Madhav Pendurthi"
    assert hidden_resume.title == ""
    assert hidden_resume.contact.linkedin == ""
    assert hidden_resume.contact.github == ""
    assert hidden_resume.contact.portfolio == ""

    _, _, _, visible, _, visible_resume = build_result(
        analysis(keyword("C#")),
        header_visibility={
            "fullName": False,
            "currentTitle": True,
            "email": True,
            "phone": False,
            "location": True,
            "linkedinUrl": True,
            "githubUrl": True,
            "portfolioUrl": True,
        },
    )

    assert "fullName" not in visible.resume_header
    assert visible.resume_header == {
        "currentTitle": "Senior .NET Developer",
        "email": "venu@example.com",
        "location": "Hartford, CT",
        "linkedinUrl": "https://linkedin.com/in/venu",
        "githubUrl": "https://github.com/venu",
        "portfolioUrl": "https://venu.dev",
    }
    assert visible.contact.phone == ""
    assert visible.contact.linkedin == "https://linkedin.com/in/venu"
    assert visible.contact.github == "https://github.com/venu"
    assert visible.contact.portfolio == "https://venu.dev"
    assert visible_resume.name == ""
    assert visible_resume.title == "Senior .NET Developer"


def test_section_visibility_excludes_sections_before_structured_resume_rendering() -> None:
    _, _, _, structured, _, resume = build_result(
        analysis(keyword("C#")),
        section_visibility={
            "summary": False,
            "skills": False,
            "experience": True,
            "projects": False,
            "education": False,
            "certifications": False,
        },
    )

    section_types = [section.type for section in structured.sections]
    assert section_types == ["experience"]
    assert resume.summary == ""
    assert resume.skills == []
    assert resume.projects == []
    assert resume.education == []
    assert resume.certifications == []


def test_unmapped_project_still_renders_in_projects_section() -> None:
    _, _, _, structured, _, resume = build_result(
        analysis(keyword("C#")),
        section_visibility={"projects": True},
    )

    projects_section = next(section for section in structured.sections if section.type == "projects")

    assert projects_section.content[0]["name"] == "Provider Portal"
    assert projects_section.content[0]["sourceRecordId"].startswith("project-project-")
    assert resume.projects[0].name == "Provider Portal"
    assert resume.projects[0].linked_experience_ids == []
