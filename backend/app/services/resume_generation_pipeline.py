from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.schemas.resume import (
    AtsBreakdown,
    AtsAnalysis,
    AtsAnalysisBreakdown,
    CandidateProfile,
    GenerateResumeRequest,
    GenerateResumeResponse,
    GenerationMetadata,
    GeneratedContentProvenance,
    GeneratedResumeSection,
    ExperienceIntelligencePlan,
    ProfileEvidenceItem,
    ProfileMatchSummary,
    ResumeContact,
    ResumeContent,
    ResumeExperience,
    ResumeGenerationSettings,
    ResumePreferences,
    ResumeSuggestion,
    SectionVisibility,
    SkillCategory,
    StructuredGeneratedResume,
)
from app.services.ats_scoring import score_formatting, score_readability, score_title_match
from app.services.profile_matching import (
    PROFILE_MATCH_CACHE_VERSION,
    build_profile_evidence_index,
    calculate_non_overlapping_experience_months,
    match_job_to_profile,
)
from app.services.structured_bullets import bullet_text, make_generated_bullet, normalize_structured_resume_bullets
from app.services.summary_planner import (
    SummaryGenerationResult,
    build_summary_planner,
    deterministic_summary,
)


RESUME_GENERATION_ALGORITHM_VERSION = "resume-generation-v1-evidence-grounded"


class ResumeGenerationContext(BaseModel):
    profile_id: str = Field(alias="profileId")
    profile_version: int = Field(alias="profileVersion")
    profile_content_hash: str = Field(alias="profileContentHash")
    job_analysis: object = Field(alias="jobAnalysis")
    profile_match: ProfileMatchSummary = Field(alias="profileMatch")
    target_job_title: str = Field(alias="targetJobTitle")
    target_company: str = Field(default="", alias="targetCompany")
    selected_template_id: str = Field(default="classic-ats", alias="selectedTemplateId")
    approved_requirement_ids: list[str] = Field(default_factory=list, alias="approvedRequirementIds")
    excluded_requirement_ids: list[str] = Field(default_factory=list, alias="excludedRequirementIds")
    evidence_index: list[ProfileEvidenceItem] = Field(default_factory=list, alias="evidenceIndex")
    generation_settings: ResumeGenerationSettings = Field(default_factory=ResumeGenerationSettings, alias="generationSettings")

    model_config = {"populate_by_name": True}


class SelectedEvidence(BaseModel):
    evidence_id: str = Field(alias="evidenceId")
    source_record_id: str = Field(default="", alias="sourceRecordId")
    original_text: str = Field(alias="originalText")
    requirement_ids: list[str] = Field(default_factory=list, alias="requirementIds")
    strength_score: int = Field(alias="strengthScore")
    selection_reason: str = Field(alias="selectionReason")
    source_label: str = Field(alias="sourceLabel")

    model_config = {"populate_by_name": True}


class SelectedResumeEvidence(BaseModel):
    skills: list[SelectedEvidence] = Field(default_factory=list)
    summary: list[SelectedEvidence] = Field(default_factory=list)
    experience: dict[str, list[SelectedEvidence]] = Field(default_factory=dict)
    projects: dict[str, list[SelectedEvidence]] = Field(default_factory=dict)
    education: list[SelectedEvidence] = Field(default_factory=list)
    certifications: list[SelectedEvidence] = Field(default_factory=list)


def build_generation_context(
    profile_record,
    payload: GenerateResumeRequest,
    job_analysis,
) -> ResumeGenerationContext:
    match_response = match_job_to_profile(
        job_analysis,
        profile_record.profile_data,
        profile_record.profile_id,
        profile_record.updated_at,
        profile_record.profile_version,
        profile_record.content_hash,
    )
    evidence_index = build_profile_evidence_index(profile_record.profile_data, profile_record.profile_id)
    matched_ids = [match.requirement_id for match in match_response.match_summary.matched_requirements]
    return ResumeGenerationContext(
        profileId=profile_record.profile_id,
        profileVersion=profile_record.profile_version,
        profileContentHash=profile_record.content_hash,
        jobAnalysis=job_analysis,
        profileMatch=match_response.match_summary,
        targetJobTitle=payload.target_role or payload.target_role or profile_record.profile_data.title,
        targetCompany=payload.target_company,
        selectedTemplateId=payload.template_id,
        approvedRequirementIds=matched_ids,
        excludedRequirementIds=[match.requirement_id for match in match_response.match_summary.unmatched_requirements],
        evidenceIndex=evidence_index,
        generationSettings=payload.generation_settings,
    )


def build_generation_context_from_profile_match(
    profile_record,
    payload: GenerateResumeRequest,
    job_analysis,
    profile_match: ProfileMatchSummary,
) -> ResumeGenerationContext:
    evidence_index = build_profile_evidence_index(profile_record.profile_data, profile_record.profile_id)
    matched_ids = [match.requirement_id for match in profile_match.matched_requirements]
    return ResumeGenerationContext(
        profileId=profile_record.profile_id,
        profileVersion=profile_record.profile_version,
        profileContentHash=profile_record.content_hash,
        jobAnalysis=job_analysis,
        profileMatch=profile_match,
        targetJobTitle=payload.target_role or profile_record.profile_data.title,
        targetCompany=payload.target_company,
        selectedTemplateId=payload.template_id,
        approvedRequirementIds=matched_ids,
        excludedRequirementIds=[match.requirement_id for match in profile_match.unmatched_requirements],
        evidenceIndex=evidence_index,
        generationSettings=payload.generation_settings,
    )


def select_relevant_profile_evidence(context: ResumeGenerationContext) -> SelectedResumeEvidence:
    requirement_by_evidence: dict[str, list[str]] = {}
    for match in context.profile_match.matched_requirements:
        for evidence in match.evidence:
            requirement_by_evidence.setdefault(evidence.evidence_id, []).append(match.requirement_id)

    selected = SelectedResumeEvidence()
    for evidence in sorted(context.evidence_index, key=evidence_rank, reverse=True):
        requirement_ids = requirement_by_evidence.get(evidence.evidence_id, [])
        if not requirement_ids and evidence.evidence_type not in {"education", "certification"}:
            continue
        item = SelectedEvidence(
            evidenceId=evidence.evidence_id,
            sourceRecordId=evidence.source_record_id or "",
            originalText=evidence.original_text,
            requirementIds=requirement_ids,
            strengthScore=evidence.strength_score,
            selectionReason="Selected because it supports matched job requirements." if requirement_ids else "Selected as factual profile section data.",
            sourceLabel=evidence.source_label,
        )
        if evidence.evidence_type == "skill":
            selected.skills.append(item)
        elif evidence.evidence_type in {"work_experience", "achievement"} and evidence.source_record_id:
            selected.experience.setdefault(evidence.source_record_id, []).append(item)
        elif evidence.evidence_type == "project" and evidence.source_record_id:
            selected.projects.setdefault(evidence.source_record_id, []).append(item)
        elif evidence.evidence_type == "education":
            selected.education.append(item)
        elif evidence.evidence_type == "certification":
            selected.certifications.append(item)
        else:
            selected.summary.append(item)
    return selected


def evidence_rank(evidence: ProfileEvidenceItem) -> tuple[int, int]:
    type_rank = {
        "achievement": 6,
        "work_experience": 5,
        "skill": 4,
        "project": 3,
        "education": 2,
        "certification": 2,
        "summary": 1,
    }.get(str(evidence.evidence_type), 0)
    return (type_rank, evidence.strength_score)


def assemble_structured_resume(
    profile: CandidateProfile,
    payload: GenerateResumeRequest,
    context: ResumeGenerationContext,
    selected: SelectedResumeEvidence,
    summary_generation: SummaryGenerationResult | None = None,
    experience_intelligence: ExperienceIntelligencePlan | None = None,
) -> StructuredGeneratedResume:
    sections: list[GeneratedResumeSection] = []
    section_visibility = effective_section_visibility(payload.resume_preferences)
    if section_visibility.summary:
        if summary_generation is None:
            planner = build_summary_planner(
                profile,
                payload,
                context.profile_match,
                context.evidence_index,
                round(calculate_non_overlapping_experience_months(profile) / 12, 1),
            )
            summary_generation = deterministic_summary(planner)
        sections.append(summary_section(summary_generation))
    if section_visibility.skills:
        sections.append(skills_section(profile, context, selected))
    if section_visibility.experience:
        sections.extend(experience_sections(profile, context, selected, experience_intelligence))
    if section_visibility.projects and context.generation_settings.include_projects and profile.projects:
        sections.append(projects_section(profile, context, selected))
    if section_visibility.education:
        sections.append(education_section(profile, context, selected))
    if section_visibility.certifications and context.generation_settings.include_certifications and profile.certifications:
        sections.append(certifications_section(profile, context, selected))
    sections = [section for section in sections if content_has_value(section.content)]
    now = datetime.now(timezone.utc).isoformat()
    missing_requirements = dedupe(
        [
            *context.profile_match.gaps,
            *[
                match.requirement_value
                for match in context.profile_match.partially_matched_requirements
                if match.requires_user_confirmation or not match.is_safe_to_use
            ],
        ]
    )
    resume = StructuredGeneratedResume(
        resumeHeader=build_resume_header(profile, payload.resume_preferences),
        resumeName=f"{profile.name} - {context.target_job_title}",
        targetJobTitle=context.target_job_title,
        targetCompany=context.target_company,
        jobDescription=payload.job_description,
        profileId=context.profile_id,
        profileVersion=context.profile_version,
        profileContentHash=context.profile_content_hash,
        matchingAlgorithmVersion=PROFILE_MATCH_CACHE_VERSION,
        generationAlgorithmVersion=RESUME_GENERATION_ALGORITHM_VERSION,
        templateId=context.selected_template_id,
        versionNumber=1,
        status="draft",
        matchScore=context.profile_match.overall_match_score,
        missingRequirements=missing_requirements,
        warnings=context.profile_match.warnings,
        contact=apply_header_visibility_to_contact(profile.contact, payload.resume_preferences),
        sections=sections,
        createdAt=now,
        updatedAt=now,
    )
    return normalize_structured_resume_bullets(resume)


def effective_section_visibility(preferences: ResumePreferences | None) -> SectionVisibility:
    if preferences:
        return preferences.section_visibility
    return SectionVisibility(
        summary=True,
        skills=True,
        experience=True,
        projects=True,
        education=True,
        certifications=True,
    )


def build_resume_header(profile: CandidateProfile, preferences: ResumePreferences | None) -> dict[str, str]:
    visibility = preferences.header_visibility if preferences else None
    header: dict[str, str] = {}
    if visibility is None or visibility.full_name:
        add_visible_header_value(header, "fullName", profile.name)
    if visibility is None or visibility.current_title:
        add_visible_header_value(header, "currentTitle", profile.title)
    if visibility is None or visibility.email:
        add_visible_header_value(header, "email", profile.contact.email)
    if visibility is None or visibility.phone:
        add_visible_header_value(header, "phone", profile.contact.phone)
    if visibility is None or visibility.location:
        add_visible_header_value(header, "location", profile.contact.location)
    if visibility is not None and visibility.linkedin_url:
        add_visible_header_value(header, "linkedinUrl", profile.contact.linkedin)
    elif visibility is None:
        add_visible_header_value(header, "linkedinUrl", profile.contact.linkedin)
    if visibility is not None and visibility.github_url:
        add_visible_header_value(header, "githubUrl", profile.contact.github)
    elif visibility is None:
        add_visible_header_value(header, "githubUrl", profile.contact.github)
    if visibility is not None and visibility.portfolio_url:
        add_visible_header_value(header, "portfolioUrl", profile.contact.portfolio)
    elif visibility is None:
        add_visible_header_value(header, "portfolioUrl", profile.contact.portfolio)
    return header


def add_visible_header_value(header: dict[str, str], key: str, value: str) -> None:
    value = (value or "").strip()
    if value:
        header[key] = value


def apply_header_visibility_to_contact(contact: ResumeContact, preferences: ResumePreferences | None) -> ResumeContact:
    visibility = preferences.header_visibility if preferences else None
    if visibility is None:
        return contact
    return contact.model_copy(
        update={
            "email": contact.email if visibility.email else "",
            "phone": contact.phone if visibility.phone else "",
            "location": contact.location if visibility.location else "",
            "linkedin": contact.linkedin if visibility.linkedin_url else "",
            "github": contact.github if visibility.github_url else "",
            "portfolio": contact.portfolio if visibility.portfolio_url else "",
        }
    )


def summary_section(summary_generation: SummaryGenerationResult) -> GeneratedResumeSection:
    return GeneratedResumeSection(
        sectionId="section-summary",
        type="summary",
        title="SUMMARY",
        order=1,
        content=summary_generation.summary,
        provenance=GeneratedContentProvenance(
            supportingEvidenceIds=summary_generation.used_evidence_ids[:8],
            supportedRequirementIds=[],
            generationMethod=summary_generation.generation_method,
            warnings=summary_generation.risk_flags,
        ),
    )


def skills_section(profile: CandidateProfile, context: ResumeGenerationContext, selected: SelectedResumeEvidence) -> GeneratedResumeSection:
    content = grouped_resume_skills(profile, selected)
    return GeneratedResumeSection(
        sectionId="section-skills",
        type="skills",
        title="TECHNICAL SKILLS",
        order=2,
        content=content,
        provenance=GeneratedContentProvenance(
            supportingEvidenceIds=[item.evidence_id for item in selected.skills],
            supportedRequirementIds=dedupe([rid for item in selected.skills for rid in item.requirement_ids]),
            generationMethod="deterministic",
        ),
    )


RESUME_SKILL_CATEGORY_DISPLAY = {
    "programming languages": "Programming Languages",
    "backend development": "Backend Frameworks & Tools",
    "frameworks & libraries": "Backend Frameworks & Tools",
    "apis & integration": "Backend Frameworks & Tools",
    "frontend development": "Frontend Frameworks & UI",
    "cloud platforms & services": "Cloud & Infrastructure",
    "databases": "Databases",
    "devops, ci/cd & containers": "DevOps & Tools",
    "tools & development environments": "DevOps & Tools",
    "testing & quality assurance": "Testing & Quality",
    "data engineering & etl": "Data Processing & Orchestration",
    "data analytics & reporting": "Data & Reporting",
    "architecture & system design": "Architecture & Design",
    "security & identity": "Security & Identity",
    "software development practices": "Development Practices",
    "methodologies & ways of working": "Development Practices",
    "backend / .net": "Backend Frameworks & Tools",
    "backend": "Backend Frameworks & Tools",
    "frontend": "Frontend Frameworks & UI",
    "cloud": "Cloud & Infrastructure",
    "testing": "Testing & Quality",
    "devops & tools": "DevOps & Tools",
    "data & reporting": "Data & Reporting",
    "methodologies": "Development Practices",
}


RESUME_SKILL_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Programming Languages", ("c#", "javascript", "typescript", "python", "sql", "sql/t-sql", "t-sql", "scala", "java")),
    ("Cloud & Infrastructure", ("microsoft azure", "azure", "azure app service", "azure sql", "aws", "google cloud", "terraform", "cloudwatch")),
    ("Data Processing & Orchestration", ("apache spark", "databricks", "airflow", "ssis", "etl")),
    ("Backend Frameworks & Tools", (".net", "asp.net core", "asp.net mvc", "web api", "restful api", "rest api", "entity framework", "linq", "node.js", "docker", "kubernetes")),
    ("Frontend Frameworks & UI", ("react", "angular", "next.js", "html5", "css3", "html", "css")),
    ("Databases", ("microsoft sql server", "ms sql server", "sql server", "mysql", "mongodb", "oracle", "postgresql", "snowflake")),
    ("Testing & Quality", ("nunit", "mstest", "jest", "jasmine", "sonarqube", "testing")),
    ("DevOps & Tools", ("git", "github", "jenkins", "tfs", "postman", "swagger", "visual studio", "ci/cd")),
    ("Data & Reporting", ("ssrs", "power bi", "tableau", "reporting")),
    ("Architecture & Design", ("object-oriented", "oop", "enterprise application design", "microservices", "system design")),
    ("Development Practices", ("agile", "scrum", "code review", "debugging", "documentation", "performance tuning")),
)


def grouped_resume_skills(profile: CandidateProfile, selected: SelectedResumeEvidence) -> list[dict[str, list[str] | str]]:
    matched_skills = {item.original_text.strip().casefold() for item in selected.skills if item.original_text.strip()}
    buckets: dict[str, list[str]] = {}

    for group in sorted(profile.skills, key=lambda item: item.order):
        ordered_items = sorted(
            [skill for skill in expanded_resume_skill_items(group.items) if skill],
            key=lambda skill: 0 if skill.casefold() in matched_skills else 1,
        )
        if is_flat_technical_skill_group(group):
            for skill in ordered_items:
                add_resume_skill_items(buckets, infer_resume_skill_category([skill]), [skill])
        else:
            add_resume_skill_items(buckets, resume_skill_category_name(group), ordered_items)

    if not buckets:
        add_resume_skill_items(
            buckets,
            "Technical Skills",
            [skill for skill in expanded_resume_skill_items([item.original_text for item in selected.skills]) if skill],
        )

    return [{"category": category, "items": items} for category, items in buckets.items() if items]


def resume_skill_category_name(group: SkillCategory) -> str:
    raw_category = (group.category_name or group.category or "Technical Skills").strip()
    normalized = raw_category.casefold()
    if is_flat_technical_skill_group(group):
        return infer_resume_skill_category(group.items)
    return RESUME_SKILL_CATEGORY_DISPLAY.get(normalized, raw_category)


def is_flat_technical_skill_group(group: SkillCategory) -> bool:
    raw_category = (group.category_name or group.category or "").strip().casefold()
    return raw_category in {"technical skills", "skills"}


def infer_resume_skill_category(items: list[str]) -> str:
    normalized_items = [normalize_resume_skill_key(item) for item in expanded_resume_skill_items(items)]
    for category, terms in RESUME_SKILL_CATEGORY_RULES:
        if any(item in terms for item in normalized_items):
            return category
    for category, terms in RESUME_SKILL_CATEGORY_RULES:
        if any(any(len(term) > 3 and term in item for term in terms) for item in normalized_items):
            return category
    return "Technical Skills"


def expanded_resume_skill_items(items: list[str]) -> list[str]:
    output: list[str] = []
    for item in items:
        output.extend(expand_resume_skill_item(item))
    return dedupe(output)


def expand_resume_skill_item(item: str) -> list[str]:
    value = " ".join(str(item).strip().split()).strip(" ,;")
    if not value:
        return []
    if ":" in value:
        left, right = value.split(":", 1)
        if left.strip().casefold() in RESUME_SKILL_CATEGORY_DISPLAY or left.strip().casefold() in {"technical skills", "skills"}:
            value = right.strip()
    normalized = normalize_resume_skill_key(value)
    if normalized.startswith("microsoft azure") and "(" in value and ")" in value:
        details = value[value.find("(") + 1 : value.rfind(")")]
        expanded = ["Microsoft Azure"]
        for part in re.split(r"[,/;]", details):
            key = normalize_resume_skill_key(part)
            if "app service" in key:
                expanded.append("Azure App Service")
            elif "azure sql" in key or key == "sql":
                expanded.append("Azure SQL Database")
        return dedupe(expanded)
    if normalized.startswith("microsoft azure") and "app service" in normalized:
        return ["Microsoft Azure", "Azure App Service"]
    if normalized in {"azure sql", "azure sql database"} or normalized.startswith("azure sql"):
        return ["Azure SQL Database"]
    return [value]


def add_resume_skill_items(buckets: dict[str, list[str]], category: str, items: list[str]) -> None:
    seen_global = {skill.casefold() for values in buckets.values() for skill in values}
    target = buckets.setdefault(category, [])
    for item in items:
        key = item.casefold()
        if key and key not in seen_global:
            target.append(item)
            seen_global.add(key)


def normalize_resume_skill_key(value: str) -> str:
    return (
        value.casefold()
        .strip()
        .strip("()")
        .replace("sql / t-sql", "sql/t-sql")
        .replace("sql / tsql", "sql/t-sql")
        .replace("t sql", "t-sql")
    )


def experience_sections(
    profile: CandidateProfile,
    context: ResumeGenerationContext,
    selected: SelectedResumeEvidence,
    experience_intelligence: ExperienceIntelligencePlan | None = None,
) -> list[GeneratedResumeSection]:
    sections = []
    role_entries = []
    generated_by_experience = {
        item.experience_id: item
        for item in (experience_intelligence.role_intelligence if experience_intelligence else [])
        if item.validation_status in {"valid", "fallback", "warning"} and item.bullets
    }
    for index, role in enumerate(profile.experience):
        source_id = f"experience-{role.experience_id}" if role.experience_id else ""
        role_evidence = selected.experience.get(source_id, [])
        role_intelligence = generated_by_experience.get(role.experience_id)
        bullets = (
            [bullet.model_dump(mode="json", by_alias=True) for bullet in role_intelligence.bullets]
            if role_intelligence
            else generate_role_bullets(role, role_evidence, context, recent=index == 0)
        )
        role_entries.append(
            {
                "company": role.company,
                "role": role.role,
                "location": role.location,
                "startDate": role.start_date,
                "endDate": role.end_date,
                "bullets": bullets,
                "sourceRecordId": source_id,
            }
        )
    evidence_items = [item for values in selected.experience.values() for item in values]
    sections.append(
        GeneratedResumeSection(
            sectionId="section-experience",
            type="experience",
            title="PROFESSIONAL EXPERIENCE",
            order=3,
            content=role_entries,
            provenance=GeneratedContentProvenance(
                supportingEvidenceIds=dedupe([item.evidence_id for item in evidence_items]),
                supportedRequirementIds=dedupe([rid for item in evidence_items for rid in item.requirement_ids]),
                generationMethod="experience_intelligence" if generated_by_experience else "deterministic",
            ),
        )
    )
    return sections


def generate_role_bullets(role: ResumeExperience, evidence: list[SelectedEvidence], context: ResumeGenerationContext, recent: bool) -> list[dict]:
    limit = context.generation_settings.bullets_per_recent_role if recent else context.generation_settings.bullets_per_older_role
    source_items = evidence
    bullets = []
    source_record_id = f"experience-{role.experience_id}" if role.experience_id else stable_text_id(role.company, role.role, role.start_date)
    for item in source_items[:limit]:
        if not bullet_evidence_is_substantive(item, role):
            continue
        text = clean_bullet(item.original_text)
        if not text:
            continue
        bullets.append(
            make_generated_bullet(
                resume_scope=context.profile_content_hash,
                source_record_id=source_record_id,
                evidence_id=item.evidence_id,
                order=len(bullets) + 1,
                text=text,
                requirement_ids=item.requirement_ids,
            )
        )
    return dedupe_bullets(bullets)[:limit]


def bullet_evidence_is_substantive(item: SelectedEvidence, role: ResumeExperience) -> bool:
    value = item.original_text.strip()
    if len(value.split()) < 5:
        return False
    if value.lower() in {role.company.lower(), role.role.lower(), role.location.lower()}:
        return False
    return bool(
        re.search(
            r"(?i)\b(built|developed|designed|led|reviewed|supported|implemented|optimized|authored|coordinated|resolved|improved|created|maintained|integrated|delivered|worked with|collaborated|partnered|qa|product owners?|business analysts?|deployment teams?|stakeholders?|api|sql|review|release|metric|%|workflow|application|service|database)\b",
            value,
        )
    )


def clean_bullet(text: str) -> str:
    value = re.sub(r"\s+", " ", text.strip(" -*•\t\r\n"))
    if not value:
        return ""
    if re.match(r"(?i)^worked with\b", value):
        value = re.sub(r"(?i)^worked with\b", "Collaborated with", value, count=1)
    if not re.match(r"(?i)^(built|developed|designed|led|reviewed|supported|implemented|optimized|authored|coordinated|collaborated|partnered|resolved|improved|created|maintained|integrated|delivered)\b", value):
        value = "Delivered " + value[:1].lower() + value[1:]
    return value.rstrip(".") + "."


def projects_section(profile: CandidateProfile, context: ResumeGenerationContext, selected: SelectedResumeEvidence) -> GeneratedResumeSection:
    content = [
        {
            "name": project.name,
            "org": project.org,
            "link": project.link,
            "technologies": project.technologies,
            "bullets": [clean_bullet(bullet) for bullet in project.bullets if clean_bullet(bullet)],
            "sourceRecordId": f"project-{project.project_id}",
        }
        for project in profile.projects
    ]
    evidence_items = [item for values in selected.projects.values() for item in values]
    return GeneratedResumeSection(
        sectionId="section-projects",
        type="projects",
        title="PROJECTS",
        order=4,
        content=content,
        provenance=GeneratedContentProvenance(
            supportingEvidenceIds=[item.evidence_id for item in evidence_items],
            supportedRequirementIds=dedupe([rid for item in evidence_items for rid in item.requirement_ids]),
        ),
    )


def education_section(profile: CandidateProfile, context: ResumeGenerationContext, selected: SelectedResumeEvidence) -> GeneratedResumeSection:
    content = [
        {
            "degree": item.degree,
            "institution": item.institution,
            "location": item.location,
            "gradYear": item.grad_year,
            "gpa": item.gpa,
            "sourceRecordId": f"education-{item.education_id}",
        }
        for item in profile.education
    ]
    return GeneratedResumeSection(
        sectionId="section-education",
        type="education",
        title="EDUCATION",
        order=5,
        content=content,
        provenance=GeneratedContentProvenance(
            supportingEvidenceIds=[item.evidence_id for item in selected.education],
            supportedRequirementIds=dedupe([rid for item in selected.education for rid in item.requirement_ids]),
        ),
    )


def certifications_section(profile: CandidateProfile, context: ResumeGenerationContext, selected: SelectedResumeEvidence) -> GeneratedResumeSection:
    content = [
        {
            "name": item.name,
            "issuer": item.issuer,
            "issuedDate": item.issued_date,
            "expiryDate": item.expiry_date,
            "sourceRecordId": f"certification-{item.certification_id}",
        }
        for item in profile.certifications
    ]
    return GeneratedResumeSection(
        sectionId="section-certifications",
        type="certifications",
        title="CERTIFICATIONS",
        order=6,
        content=content,
        provenance=GeneratedContentProvenance(
            supportingEvidenceIds=[item.evidence_id for item in selected.certifications],
            supportedRequirementIds=dedupe([rid for item in selected.certifications for rid in item.requirement_ids]),
        ),
    )


def content_has_value(content) -> bool:
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return bool(content)
    if isinstance(content, dict):
        return bool(content)
    return content is not None


def structured_to_resume_content(profile: CandidateProfile, structured: StructuredGeneratedResume) -> ResumeContent:
    section_map = {section.type: section.content for section in structured.sections}
    skills = [
        SkillCategory(category=item.get("category", "Technical Skills"), items=item.get("items", []))
        for item in section_map.get("skills", [])
        if isinstance(item, dict)
    ]
    experience = [
        ResumeExperience(
            experienceId=item.get("sourceRecordId", "").replace("experience-", ""),
            company=item.get("company", ""),
            role=item.get("role", ""),
            location=item.get("location", ""),
            startDate=item.get("startDate", ""),
            endDate=item.get("endDate", ""),
            bullets=[bullet_text(bullet) for bullet in item.get("bullets", []) if bullet_text(bullet)],
        )
        for item in section_map.get("experience", [])
        if isinstance(item, dict)
    ]
    return ResumeContent(
        name=structured.resume_header.get("fullName", ""),
        title=structured.resume_header.get("currentTitle", ""),
        contact=structured.contact,
        summary=section_map.get("summary", ""),
        skills=skills,
        experience=experience,
        projects=profile.projects if "projects" in section_map else [],
        education=profile.education if "education" in section_map else [],
        certifications=profile.certifications if "certifications" in section_map else [],
    )


def build_generation_response(
    profile: CandidateProfile,
    payload: GenerateResumeRequest,
    context: ResumeGenerationContext,
    structured: StructuredGeneratedResume,
    validation,
) -> GenerateResumeResponse:
    resume = structured_to_resume_content(profile, structured)
    coverage = evidence_aware_ats_coverage(structured, context)
    keyword_score = evidence_aware_keyword_score(coverage)
    formatting_score = score_formatting(resume)
    readability_score = score_readability(resume)
    title_score = score_title_match(resume, payload.target_role, payload.job_description)
    ats_score = evidence_aware_overall_score(
        keyword_score=keyword_score,
        title_score=title_score,
        formatting_score=formatting_score,
        readability_score=readability_score,
    )
    matched_keywords = [item["value"] for item in coverage["supportedAndCovered"]][:24]
    missing_keywords = [
        item["value"]
        for item in [*coverage["supportedButNotRepresented"], *coverage["adjacentUnsupported"], *coverage["unmatched"]]
    ][:16]
    suggestions = [
        ResumeSuggestion(text=f"Missing supported evidence for {gap}.", points=4)
        for gap in context.profile_match.gaps[:5]
    ]
    return GenerateResumeResponse(
        resumeId=structured.resume_id,
        resume=resume,
        atsAnalysis=AtsAnalysis(
            score=ats_score,
            breakdown=AtsAnalysisBreakdown(
                keywordMatch=keyword_score,
                formatting=formatting_score,
                readability=readability_score,
                matchedKeywords=matched_keywords,
                missingKeywords=missing_keywords,
            ),
            coverage=coverage,
            suggestions=suggestions,
        ),
        atsScore=ats_score,
        breakdown=AtsBreakdown(
            keywordMatch=keyword_score,
            formatting=formatting_score,
            readability=readability_score,
            matchedKeywords=matched_keywords,
            missingKeywords=missing_keywords,
            coverage=coverage,
        ),
        suggestions=suggestions,
        generationMetadata=GenerationMetadata(
            model=None,
            durationMs=0,
            generatedAt=structured.created_at,
            pipelineVersion=structured.generation_algorithm_version,
        ),
        structuredResume=structured,
        validationResult=validation,
    )


def normalized_job_hash(job_description: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", job_description.strip().lower()).encode("utf-8")).hexdigest()


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def dedupe_bullets(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for item in items:
        key = bullet_text(item).lower().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def stable_text_id(*values: str) -> str:
    return "generated-" + normalized_job_hash("|".join(values))[:16]


def evidence_aware_ats_coverage(structured: StructuredGeneratedResume, context: ResumeGenerationContext) -> dict[str, list[dict[str, str]]]:
    represented = represented_requirement_ids(structured)
    coverage = {
        "supportedAndCovered": [],
        "supportedButNotRepresented": [],
        "adjacentUnsupported": [],
        "unmatched": [],
        "suggestedExcluded": [],
    }
    for match in context.profile_match.matched_requirements:
        item = coverage_item(match.requirement_id, match.requirement_value, match.classification.value)
        if match.requirement_id in represented:
            coverage["supportedAndCovered"].append(item)
        else:
            coverage["supportedButNotRepresented"].append(item)
    for match in context.profile_match.partially_matched_requirements:
        coverage["adjacentUnsupported"].append(coverage_item(match.requirement_id, match.requirement_value, match.classification.value))
    for match in context.profile_match.unmatched_requirements:
        coverage["unmatched"].append(coverage_item(match.requirement_id, match.requirement_value, match.classification.value))
    suggested = getattr(context.job_analysis, "suggested_keywords", []) or []
    for item in suggested:
        value = getattr(item, "value", "") or getattr(item, "term", "")
        coverage["suggestedExcluded"].append(coverage_item(getattr(item, "id", ""), value, "suggested"))
    return coverage


def evidence_aware_keyword_score(coverage: dict[str, list[dict[str, str]]]) -> int:
    covered = len(coverage.get("supportedAndCovered", []))
    supported_unrepresented = len(coverage.get("supportedButNotRepresented", []))
    adjacent = len(coverage.get("adjacentUnsupported", []))
    unmatched = len(coverage.get("unmatched", []))
    total = covered + supported_unrepresented + adjacent + unmatched
    if total <= 0:
        return 0
    earned = covered + supported_unrepresented * 0.35
    return clamp_score(round((earned / total) * 100))


def evidence_aware_overall_score(
    *,
    keyword_score: int,
    title_score: int,
    formatting_score: int,
    readability_score: int,
) -> int:
    return clamp_score(
        round(
            keyword_score * 0.58
            + title_score * 0.14
            + formatting_score * 0.16
            + readability_score * 0.12
        )
    )


def represented_requirement_ids(structured: StructuredGeneratedResume) -> set[str]:
    represented: set[str] = set()
    for section in structured.sections:
        if section.type == "experience":
            for entry in section.content if isinstance(section.content, list) else []:
                if not isinstance(entry, dict):
                    continue
                for bullet in entry.get("bullets", []):
                    if isinstance(bullet, dict) and bullet.get("validationStatus") in {"validated", "valid", "fallback", "warning"}:
                        represented.update(str(value) for value in bullet.get("supportedRequirementIds", []) if value)
        elif section.provenance.validation_status == "validated":
            represented.update(section.provenance.supported_requirement_ids)
    return represented


def coverage_item(requirement_id: str, value: str, classification: str) -> dict[str, str]:
    return {"requirementId": requirement_id, "value": value, "classification": classification}


def clamp_score(value: int) -> int:
    return max(0, min(100, value))
