from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.schemas.resume import (
    AtsBreakdown,
    CandidateProfile,
    GenerateResumeRequest,
    GenerateResumeResponse,
    GeneratedContentProvenance,
    GeneratedResumeSection,
    LayoutContract,
    ProfileEvidenceItem,
    ProfileMatchSummary,
    ResumeContent,
    ResumeExperience,
    ResumeGenerationSettings,
    ResumeSuggestion,
    SkillCategory,
    StructuredGeneratedResume,
)
from app.services.ats_scoring import score_resume
from app.services.profile_matching import (
    PROFILE_MATCH_CACHE_VERSION,
    build_profile_evidence_index,
    calculate_non_overlapping_experience_months,
    match_job_to_profile,
)
from app.services.resume_validator import validate_structured_resume


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
) -> StructuredGeneratedResume:
    sections: list[GeneratedResumeSection] = []
    sections.append(summary_section(profile, context, selected))
    sections.append(skills_section(profile, context, selected))
    sections.extend(experience_sections(profile, context, selected))
    if context.generation_settings.include_projects and profile.projects:
        sections.append(projects_section(profile, context, selected))
    sections.append(education_section(profile, context, selected))
    if context.generation_settings.include_certifications and profile.certifications:
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
    return StructuredGeneratedResume(
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
        contact=profile.contact,
        sections=sections,
        createdAt=now,
        updatedAt=now,
    )


def summary_section(profile: CandidateProfile, context: ResumeGenerationContext, selected: SelectedResumeEvidence) -> GeneratedResumeSection:
    years = round(calculate_non_overlapping_experience_months(profile) / 12, 1)
    matched_terms = [match.requirement_value for match in context.profile_match.matched_requirements[:6]]
    domain_terms = [
        match.requirement_value
        for match in context.profile_match.matched_requirements
        if match.requirement_category.lower() == "domain"
    ]
    parts = [
        f"{profile.title or 'Software engineer'} with {years:g}+ years of experience" if years >= 1 else profile.title or "Software engineer",
        f"grounded in {', '.join(matched_terms[:4])}" if matched_terms else "grounded in stored engineering experience",
    ]
    if domain_terms:
        parts.append(f"with supported domain experience in {', '.join(domain_terms[:2])}")
    parts.append("focused on clear delivery, maintainable implementation, and evidence-backed resume claims")
    content = ". ".join(part for part in parts if part).strip() + "."
    evidence_ids = [item.evidence_id for item in [*selected.summary, *selected.skills][:8]]
    requirement_ids = dedupe([rid for item in [*selected.summary, *selected.skills] for rid in item.requirement_ids])[:8]
    return GeneratedResumeSection(
        sectionId="section-summary",
        type="summary",
        title="SUMMARY",
        order=1,
        content=content,
        provenance=GeneratedContentProvenance(
            supportingEvidenceIds=evidence_ids,
            supportedRequirementIds=requirement_ids,
            generationMethod="deterministic",
        ),
    )


def skills_section(profile: CandidateProfile, context: ResumeGenerationContext, selected: SelectedResumeEvidence) -> GeneratedResumeSection:
    matched_skill_text = [item.original_text for item in selected.skills]
    profile_skills = [skill for group in profile.skills for skill in group.items]
    ordered = dedupe([*matched_skill_text, *profile_skills])
    content = [{"category": "Technical Skills", "items": ordered}]
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


def experience_sections(profile: CandidateProfile, context: ResumeGenerationContext, selected: SelectedResumeEvidence) -> list[GeneratedResumeSection]:
    sections = []
    role_entries = []
    for index, role in enumerate(profile.experience):
        source_id = f"experience-{role.experience_id}" if role.experience_id else ""
        role_evidence = selected.experience.get(source_id, [])
        bullets = generate_role_bullets(role, role_evidence, context, recent=index == 0)
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
                generationMethod="deterministic",
            ),
        )
    )
    return sections


def generate_role_bullets(role: ResumeExperience, evidence: list[SelectedEvidence], context: ResumeGenerationContext, recent: bool) -> list[str]:
    limit = context.generation_settings.bullets_per_recent_role if recent else context.generation_settings.bullets_per_older_role
    source_items = evidence
    bullets = []
    for item in source_items[:limit]:
        if not bullet_evidence_is_substantive(item, role):
            continue
        text = clean_bullet(item.original_text)
        if not text:
            continue
        bullets.append(text)
    return dedupe(bullets)[:limit]


def bullet_evidence_is_substantive(item: SelectedEvidence, role: ResumeExperience) -> bool:
    value = item.original_text.strip()
    if len(value.split()) < 5:
        return False
    if value.lower() in {role.company.lower(), role.role.lower(), role.location.lower()}:
        return False
    return bool(
        re.search(
            r"(?i)\b(built|developed|designed|led|reviewed|supported|implemented|optimized|authored|coordinated|resolved|improved|created|maintained|integrated|delivered|api|sql|review|release|metric|%|workflow|application|service|database)\b",
            value,
        )
    )


def clean_bullet(text: str) -> str:
    value = re.sub(r"\s+", " ", text.strip(" -*•\t\r\n"))
    if not value:
        return ""
    if not re.match(r"(?i)^(built|developed|designed|led|reviewed|supported|implemented|optimized|authored|coordinated|resolved|improved|created|maintained|integrated|delivered)\b", value):
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
            bullets=item.get("bullets", []),
        )
        for item in section_map.get("experience", [])
        if isinstance(item, dict)
    ]
    return ResumeContent(
        name=profile.name,
        title=profile.title,
        contact=profile.contact,
        summary=section_map.get("summary", ""),
        skills=skills,
        experience=experience,
        projects=profile.projects,
        education=profile.education,
        certifications=profile.certifications,
    )


def build_generation_response(
    profile: CandidateProfile,
    payload: GenerateResumeRequest,
    context: ResumeGenerationContext,
    structured: StructuredGeneratedResume,
    validation,
) -> GenerateResumeResponse:
    resume = structured_to_resume_content(profile, structured)
    ats = score_resume(resume, payload)
    suggestions = [
        ResumeSuggestion(text=f"Missing supported evidence for {gap}.", points=4)
        for gap in context.profile_match.gaps[:5]
    ]
    return GenerateResumeResponse(
        resume=resume,
        atsScore=ats.score,
        breakdown=AtsBreakdown(
            keywordMatch=ats.breakdown.keyword_match,
            formatting=ats.breakdown.formatting,
            readability=ats.breakdown.readability,
            matchedKeywords=ats.breakdown.matched_keywords,
            missingKeywords=ats.breakdown.missing_keywords,
        ),
        suggestions=suggestions,
        layoutContract=LayoutContract(),
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
