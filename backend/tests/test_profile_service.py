from app.schemas.resume import (
    CandidateProfile,
    ResumeContact,
    ResumeEducation,
    ResumeExperience,
    SkillCategory,
)
from app.services.profile_matching import build_profile_evidence_index, profile_match_cache_key
from app.services.profile_service import (
    calculate_profile_completeness,
    compute_profile_content_hash,
    ensure_profile_record_ids,
    user_id_from_email,
)
from tests.test_profile_matching import analysis, keyword


def sample_profile() -> CandidateProfile:
    return CandidateProfile(
        name="Venu Madhav Pendurthi",
        title="Senior .NET Developer",
        contact=ResumeContact(
            email="venu@example.com",
            phone="+12014436937",
            location="Hartford, CT",
            linkedin="https://linkedin.com/in/venu",
        ),
        summary="Senior full-stack .NET developer.",
        skills=[SkillCategory(category="Technical Skills", items=["C#", ".NET", "SQL Server"])],
        experience=[
            ResumeExperience(
                company="Infosys",
                role="Senior .NET Developer",
                startDate="2021-01",
                endDate="Present",
                rawNotes="Built C# APIs and SQL Server integrations.",
            )
        ],
        education=[ResumeEducation(degree="Bachelor of Technology in Computer Science", institution="JNTU")],
    )


def test_profile_content_hash_is_deterministic() -> None:
    profile = sample_profile()

    assert compute_profile_content_hash(profile) == compute_profile_content_hash(profile)


def test_profile_update_changes_content_hash() -> None:
    profile = sample_profile()
    changed = profile.model_copy(update={"title": "Lead .NET Developer"})

    assert compute_profile_content_hash(profile) != compute_profile_content_hash(changed)


def test_completeness_calculation_is_deterministic() -> None:
    score = calculate_profile_completeness(sample_profile())

    assert 80 <= score <= 100


def test_stable_parent_ids_are_added() -> None:
    profile = ensure_profile_record_ids(sample_profile())

    assert profile.experience[0].experience_id.startswith("experience-")
    assert profile.education[0].education_id.startswith("education-")


def test_reordered_experiences_keep_stable_evidence_ids() -> None:
    first = ResumeExperience(
        company="Infosys",
        role="Senior .NET Developer",
        startDate="2021-01",
        rawNotes="Built C# APIs.",
    )
    second = ResumeExperience(
        company="TCS",
        role=".NET Developer",
        startDate="2016-12",
        rawNotes="Built SQL Server applications.",
    )
    profile_a = ensure_profile_record_ids(sample_profile().model_copy(update={"experience": [first, second]}))
    profile_b = profile_a.model_copy(update={"experience": list(reversed(profile_a.experience))})

    ids_a = {item.evidence_id for item in build_profile_evidence_index(profile_a, "profile-1")}
    ids_b = {item.evidence_id for item in build_profile_evidence_index(profile_b, "profile-1")}

    assert ids_a == ids_b


def test_reordered_skills_keep_stable_evidence_ids() -> None:
    profile_a = sample_profile()
    profile_b = profile_a.model_copy(
        update={"skills": [SkillCategory(category="Technical Skills", items=["SQL Server", ".NET", "C#"])]}
    )

    skill_ids_a = {
        item.evidence_id
        for item in build_profile_evidence_index(profile_a, "profile-1")
        if item.evidence_type == "skill"
    }
    skill_ids_b = {
        item.evidence_id
        for item in build_profile_evidence_index(profile_b, "profile-1")
        if item.evidence_type == "skill"
    }

    assert skill_ids_a == skill_ids_b


def test_user_id_from_email_is_stable_and_case_insensitive() -> None:
    assert user_id_from_email("Venu@Example.com") == user_id_from_email("venu@example.com")


def test_match_cache_key_changes_with_profile_version_and_hash() -> None:
    profile = sample_profile()
    job_analysis = analysis(keyword("C#"))
    first = profile_match_cache_key(job_analysis, profile, "profile-1", "2026-07-09", 1, "hash-a")
    second = profile_match_cache_key(job_analysis, profile, "profile-1", "2026-07-09", 2, "hash-b")

    assert first != second
