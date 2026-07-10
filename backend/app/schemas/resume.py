from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ResumeContact(BaseModel):
    phone: str = ""
    email: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""


class SkillCategory(BaseModel):
    category: str
    items: list[str] = Field(default_factory=list)


class ResumeExperience(BaseModel):
    experience_id: str = Field(default="", alias="experienceId")
    company: str
    role: str
    location: str = ""
    start_date: str = Field(default="", alias="startDate")
    end_date: str = Field(default="", alias="endDate")
    raw_notes: str = Field(default="", alias="rawNotes")
    bullets: list[str] = Field(default_factory=list)
    metric_flags: list[str] = Field(default_factory=list, alias="metricFlags")

    model_config = ConfigDict(populate_by_name=True)


class ResumeProject(BaseModel):
    project_id: str = Field(default="", alias="projectId")
    name: str
    org: str = ""
    link: str = ""
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class ResumeEducation(BaseModel):
    education_id: str = Field(default="", alias="educationId")
    degree: str
    institution: str
    location: str = ""
    grad_year: str = Field(default="", alias="gradYear")
    gpa: str = ""

    model_config = ConfigDict(populate_by_name=True)


class ResumeCertification(BaseModel):
    certification_id: str = Field(default="", alias="certificationId")
    name: str
    issuer: str = ""
    issued_date: str = Field(default="", alias="issuedDate")
    expiry_date: str = Field(default="", alias="expiryDate")

    model_config = ConfigDict(populate_by_name=True)


class CandidateProfile(BaseModel):
    name: str
    title: str = ""
    contact: ResumeContact = Field(default_factory=ResumeContact)
    summary: str = ""
    skills: list[SkillCategory] = Field(default_factory=list)
    experience: list[ResumeExperience] = Field(default_factory=list)
    projects: list[ResumeProject] = Field(default_factory=list)
    education: list[ResumeEducation] = Field(default_factory=list)
    certifications: list[ResumeCertification] = Field(default_factory=list)


class GenerateResumeRequest(BaseModel):
    job_description: str = Field(default="", alias="job_description")
    target_role: str = Field(default="", alias="target_role")
    target_company: str = Field(default="", alias="target_company")
    level: str = "Senior"
    tone: str = "Professional"
    length: str = "1 page"
    candidate_profile: CandidateProfile | None = Field(default=None, alias="candidate_profile")
    job_analysis: JobAnalysisResponse | None = Field(default=None, alias="jobAnalysis")
    profile_id: str = Field(default="", alias="profileId")
    template_id: str = Field(default="classic-ats", alias="templateId")
    generation_settings: ResumeGenerationSettings = Field(default_factory=lambda: ResumeGenerationSettings(), alias="generationSettings")
    paper_size: str = Field(default="US Letter", alias="paper_size")

    model_config = ConfigDict(populate_by_name=True)


class ResumeContent(CandidateProfile):
    pass


class AtsBreakdown(BaseModel):
    keyword_match: int = Field(alias="keywordMatch")
    formatting: int
    readability: int
    matched_keywords: list[str] = Field(default_factory=list, alias="matchedKeywords")
    missing_keywords: list[str] = Field(default_factory=list, alias="missingKeywords")

    model_config = ConfigDict(populate_by_name=True)


class ResumeSuggestion(BaseModel):
    text: str
    points: int


class LayoutContract(BaseModel):
    font: str = "Times New Roman"
    margins: dict[str, float] = Field(
        default_factory=lambda: {"top": 0.55, "bottom": 0.55, "left": 0.60, "right": 0.60}
    )
    paper_size: str = Field(default="US Letter", alias="paperSize")
    section_order: list[str] = Field(
        default_factory=lambda: [
            "SUMMARY",
            "TECHNICAL SKILLS",
            "PROFESSIONAL EXPERIENCE",
            "PROJECTS",
            "EDUCATION",
            "CERTIFICATIONS",
        ],
        alias="sectionOrder",
    )
    ats_safe: bool = Field(default=True, alias="atsSafe")

    model_config = ConfigDict(populate_by_name=True)


class SemanticKeywordItem(BaseModel):
    term: str
    category: str = "General"
    priority: str = "important"
    source: str = "exact"


class SemanticRequirementGroup(BaseModel):
    name: str
    category: str
    priority: str
    exact_keywords: list[str] = Field(default_factory=list, alias="exactKeywords")
    semantic_keywords: list[str] = Field(default_factory=list, alias="semanticKeywords")
    related_concepts: list[str] = Field(default_factory=list, alias="relatedConcepts")

    model_config = ConfigDict(populate_by_name=True)


class CandidateEvidenceMatch(BaseModel):
    requirement: str
    confidence: str = "missing"
    evidence: list[str] = Field(default_factory=list)
    supported_keywords: list[str] = Field(default_factory=list, alias="supportedKeywords")
    missing_keywords: list[str] = Field(default_factory=list, alias="missingKeywords")
    suggested_resume_use: list[str] = Field(default_factory=list, alias="suggestedResumeUse")

    model_config = ConfigDict(populate_by_name=True)


class AtsKeywordPlanItem(BaseModel):
    keyword: str
    priority: str
    target_sections: list[str] = Field(default_factory=list, alias="targetSections")
    confidence: str = "missing"
    guidance: str = ""

    model_config = ConfigDict(populate_by_name=True)


class SemanticRequirementPlan(BaseModel):
    exact_keywords: list[SemanticKeywordItem] = Field(default_factory=list, alias="exactKeywords")
    semantic_keywords: list[SemanticKeywordItem] = Field(default_factory=list, alias="semanticKeywords")
    requirement_groups: list[SemanticRequirementGroup] = Field(default_factory=list, alias="requirementGroups")
    candidate_evidence_map: list[CandidateEvidenceMatch] = Field(default_factory=list, alias="candidateEvidenceMap")
    missing_requirements: list[str] = Field(default_factory=list, alias="missingRequirements")
    weak_requirements: list[str] = Field(default_factory=list, alias="weakRequirements")
    ats_keyword_plan: list[AtsKeywordPlanItem] = Field(default_factory=list, alias="atsKeywordPlan")

    model_config = ConfigDict(populate_by_name=True)


class ResumeAiMetrics(BaseModel):
    generation_time_ms: int = Field(default=0, alias="generationTimeMs")
    ai_cost: float = Field(default=0.0, alias="aiCost")
    tokens_used: int = Field(default=0, alias="tokensUsed")
    models_used: list[str] = Field(default_factory=list, alias="modelsUsed")
    cache_used: bool = Field(default=False, alias="cacheUsed")
    ats_score: int = Field(default=0, alias="atsScore")
    validation_score: int = Field(default=100, alias="validationScore")

    model_config = ConfigDict(populate_by_name=True)


class ResumeGenerationSettings(BaseModel):
    maximum_pages: int = Field(default=2, alias="maximumPages")
    bullets_per_recent_role: int = Field(default=5, alias="bulletsPerRecentRole")
    bullets_per_older_role: int = Field(default=3, alias="bulletsPerOlderRole")
    include_projects: bool = Field(default=True, alias="includeProjects")
    include_certifications: bool = Field(default=True, alias="includeCertifications")
    include_unmatched_keywords: bool = Field(default=False, alias="includeUnmatchedKeywords")
    writing_style: str = Field(default="balanced", alias="writingStyle")

    model_config = ConfigDict(populate_by_name=True)


class GeneratedContentProvenance(BaseModel):
    supporting_evidence_ids: list[str] = Field(default_factory=list, alias="supportingEvidenceIds")
    supported_requirement_ids: list[str] = Field(default_factory=list, alias="supportedRequirementIds")
    generation_method: str = Field(default="deterministic", alias="generationMethod")
    validation_status: str = Field(default="validated", alias="validationStatus")
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class GeneratedResumeSection(BaseModel):
    section_id: str = Field(alias="sectionId")
    type: str
    title: str
    order: int
    visible: bool = True
    content: Any
    provenance: GeneratedContentProvenance = Field(default_factory=GeneratedContentProvenance)

    model_config = ConfigDict(populate_by_name=True)


class ResumeValidationIssue(BaseModel):
    code: str
    severity: str
    message: str
    section_id: str = Field(default="", alias="sectionId")
    content_id: str = Field(default="", alias="contentId")
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")

    model_config = ConfigDict(populate_by_name=True)


class ResumeValidationResult(BaseModel):
    is_valid: bool = Field(alias="isValid")
    errors: list[ResumeValidationIssue] = Field(default_factory=list)
    warnings: list[ResumeValidationIssue] = Field(default_factory=list)
    rejected_content_ids: list[str] = Field(default_factory=list, alias="rejectedContentIds")

    model_config = ConfigDict(populate_by_name=True)


class StructuredGeneratedResume(BaseModel):
    resume_id: str = Field(default="", alias="resumeId")
    user_id: str = Field(default="", alias="userId")
    resume_name: str = Field(alias="resumeName")
    target_job_title: str = Field(alias="targetJobTitle")
    target_company: str = Field(default="", alias="targetCompany")
    job_description: str = Field(alias="jobDescription")
    profile_id: str = Field(alias="profileId")
    profile_version: int = Field(alias="profileVersion")
    profile_content_hash: str = Field(alias="profileContentHash")
    job_analysis_version: str = Field(default="job-analysis-v4-grounded-extraction", alias="jobAnalysisVersion")
    matching_algorithm_version: str = Field(alias="matchingAlgorithmVersion")
    generation_algorithm_version: str = Field(alias="generationAlgorithmVersion")
    template_id: str = Field(alias="templateId")
    version_number: int = Field(default=1, alias="versionNumber")
    status: str = "draft"
    match_score: int = Field(default=0, alias="matchScore")
    missing_requirements: list[str] = Field(default_factory=list, alias="missingRequirements")
    warnings: list[str] = Field(default_factory=list)
    contact: ResumeContact
    sections: list[GeneratedResumeSection] = Field(default_factory=list)
    created_at: str = Field(default="", alias="createdAt")
    updated_at: str = Field(default="", alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)


class GenerateResumeResponse(BaseModel):
    resume: ResumeContent
    ats_score: int = Field(alias="atsScore")
    breakdown: AtsBreakdown
    suggestions: list[ResumeSuggestion] = Field(default_factory=list)
    layout_contract: LayoutContract = Field(default_factory=LayoutContract, alias="layoutContract")
    semantic_plan: SemanticRequirementPlan = Field(default_factory=SemanticRequirementPlan, alias="semanticPlan")
    ai_metrics: ResumeAiMetrics = Field(default_factory=ResumeAiMetrics, alias="aiMetrics")
    structured_resume: StructuredGeneratedResume | None = Field(default=None, alias="structuredResume")
    validation_result: ResumeValidationResult | None = Field(default=None, alias="validationResult")
    persisted_resume_id: str = Field(default="", alias="persistedResumeId")

    model_config = ConfigDict(populate_by_name=True)


class StructuredResumeRecord(BaseModel):
    resume_id: str = Field(alias="resumeId")
    user_id: str = Field(alias="userId")
    profile_id: str = Field(alias="profileId")
    profile_version: int = Field(alias="profileVersion")
    profile_content_hash: str = Field(alias="profileContentHash")
    resume_name: str = Field(alias="resumeName")
    target_job_title: str = Field(alias="targetJobTitle")
    target_company: str = Field(default="", alias="targetCompany")
    job_description: str = Field(alias="jobDescription")
    job_analysis_json: dict[str, Any] = Field(default_factory=dict, alias="jobAnalysisJson")
    profile_match_json: dict[str, Any] = Field(default_factory=dict, alias="profileMatchJson")
    resume_json: StructuredGeneratedResume = Field(alias="resumeJson")
    template_id: str = Field(alias="templateId")
    match_score: int = Field(alias="matchScore")
    generation_algorithm_version: str = Field(alias="generationAlgorithmVersion")
    status: str
    version_number: int = Field(alias="versionNumber")
    parent_resume_id: str = Field(default="", alias="parentResumeId")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)


class UpdateStructuredResumeRequest(BaseModel):
    resume_json: StructuredGeneratedResume = Field(alias="resumeJson")
    status: str = "draft"

    model_config = ConfigDict(populate_by_name=True)


class ExportResumeRequest(BaseModel):
    resume: ResumeContent


class JobAnalysisRequest(BaseModel):
    job_description: str = Field(default="", alias="job_description")
    target_role: str = Field(default="", alias="target_role")
    target_company: str = Field(default="", alias="target_company")
    level: str = "Senior"

    model_config = ConfigDict(populate_by_name=True)


class JobRoleInformation(BaseModel):
    title: str = ""
    seniority: str = ""
    experience: str = ""
    domain: str = ""


class PhaseOneJobIntelligence(BaseModel):
    role_title: str = Field(default="", alias="roleTitle")
    seniority_level: str = Field(default="", alias="seniorityLevel")
    engineering_type: str = Field(default="", alias="engineeringType")
    experience_expectation: str = Field(default="", alias="experienceExpectation")
    primary_mission: str = Field(default="", alias="primaryMission")
    domain_context: list[str] = Field(default_factory=list, alias="domainContext")
    ownership_expectations: list[str] = Field(default_factory=list, alias="ownershipExpectations")
    collaboration_expectations: list[str] = Field(default_factory=list, alias="collaborationExpectations")
    delivery_expectations: list[str] = Field(default_factory=list, alias="deliveryExpectations")
    resume_tone: str = Field(default="", alias="resumeTone")

    model_config = ConfigDict(populate_by_name=True)


class PhaseOneJobIntelligenceResponse(BaseModel):
    job_intelligence: PhaseOneJobIntelligence = Field(default_factory=PhaseOneJobIntelligence, alias="jobIntelligence")

    model_config = ConfigDict(populate_by_name=True)


class KeywordSourceType(str, Enum):
    explicit = "explicit"
    inferred = "inferred"
    suggested = "suggested"


class KeywordConfidence(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class KeywordPriority(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class MatchClassification(str, Enum):
    exact = "exact"
    normalized = "normalized"
    adjacent = "adjacent"
    unmatched = "unmatched"


class ProfileEvidenceType(str, Enum):
    skill = "skill"
    work_experience = "work_experience"
    achievement = "achievement"
    project = "project"
    education = "education"
    certification = "certification"
    summary = "summary"


class ProfileEvidenceItem(BaseModel):
    evidence_id: str = Field(alias="evidenceId")
    evidence_type: ProfileEvidenceType = Field(alias="evidenceType")
    source_record_id: str | None = Field(default=None, alias="sourceRecordId")
    source_label: str = Field(alias="sourceLabel")
    original_text: str = Field(alias="originalText")
    matched_text: str | None = Field(default=None, alias="matchedText")
    company_name: str | None = Field(default=None, alias="companyName")
    role_title: str | None = Field(default=None, alias="roleTitle")
    project_name: str | None = Field(default=None, alias="projectName")
    strength_score: int = Field(default=0, ge=0, le=100, alias="strengthScore")
    reason: str = ""

    model_config = ConfigDict(populate_by_name=True)


class RequirementMatch(BaseModel):
    requirement_id: str = Field(alias="requirementId")
    requirement_value: str = Field(alias="requirementValue")
    requirement_category: str = Field(alias="requirementCategory")
    requirement_priority: str = Field(alias="requirementPriority")
    requirement_priority_score: int = Field(default=0, ge=0, le=100, alias="requirementPriorityScore")
    source_type: KeywordSourceType = Field(default=KeywordSourceType.explicit, alias="sourceType")

    classification: MatchClassification
    match_score: int = Field(ge=0, le=100, alias="matchScore")

    evidence: list[ProfileEvidenceItem] = Field(default_factory=list)
    adjacent_evidence: list[ProfileEvidenceItem] = Field(default_factory=list, alias="adjacentEvidence")

    is_safe_to_use: bool = Field(default=False, alias="isSafeToUse")
    requires_user_confirmation: bool = Field(default=False, alias="requiresUserConfirmation")
    reason: str = ""

    model_config = ConfigDict(populate_by_name=True)


class ProfileMatchSummary(BaseModel):
    overall_match_score: int = Field(default=0, ge=0, le=100, alias="overallMatchScore")
    core_requirement_score: int = Field(default=0, ge=0, le=100, alias="coreRequirementScore")
    supporting_requirement_score: int = Field(default=0, ge=0, le=100, alias="supportingRequirementScore")

    exact_match_count: int = Field(default=0, alias="exactMatchCount")
    normalized_match_count: int = Field(default=0, alias="normalizedMatchCount")
    adjacent_match_count: int = Field(default=0, alias="adjacentMatchCount")
    unmatched_count: int = Field(default=0, alias="unmatchedCount")

    matched_requirements: list[RequirementMatch] = Field(default_factory=list, alias="matchedRequirements")
    partially_matched_requirements: list[RequirementMatch] = Field(default_factory=list, alias="partiallyMatchedRequirements")
    unmatched_requirements: list[RequirementMatch] = Field(default_factory=list, alias="unmatchedRequirements")

    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    transferable_strengths: list[str] = Field(default_factory=list, alias="transferableStrengths")
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class ProfileMatchRequest(BaseModel):
    candidate_profile: CandidateProfile | None = Field(default=None, alias="candidate_profile")
    job_analysis: JobAnalysisResponse = Field(alias="jobAnalysis")
    profile_id: str = Field(default="", alias="profileId")
    profile_updated_at: str = Field(default="", alias="profileUpdatedAt")

    model_config = ConfigDict(populate_by_name=True)


class ProfileMatchResponse(BaseModel):
    match_summary: ProfileMatchSummary = Field(alias="matchSummary")
    cache_version: str = Field(alias="cacheVersion")
    cache_hit: bool = Field(default=False, alias="cacheHit")
    profile_id: str = Field(default="", alias="profileId")
    profile_version: int = Field(default=0, alias="profileVersion")
    profile_updated_at: str = Field(default="", alias="profileUpdatedAt")
    profile_content_hash: str = Field(default="", alias="profileContentHash")
    matching_algorithm_version: str = Field(default="", alias="matchingAlgorithmVersion")

    model_config = ConfigDict(populate_by_name=True)


class CandidateProfileRecord(BaseModel):
    profile_id: str = Field(alias="profileId")
    user_id: str = Field(alias="userId")
    profile_name: str = Field(alias="profileName")
    profile_data: CandidateProfile = Field(alias="profileData")
    schema_version: int = Field(alias="schemaVersion")
    profile_version: int = Field(alias="profileVersion")
    completeness_score: int = Field(alias="completenessScore")
    content_hash: str = Field(alias="contentHash")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)


class CreateCandidateProfileRequest(BaseModel):
    profile_name: str = Field(default="Primary Profile", alias="profileName")
    profile_data: CandidateProfile = Field(alias="profileData")

    model_config = ConfigDict(populate_by_name=True)


class UpdateCandidateProfileRequest(BaseModel):
    profile_name: str | None = Field(default=None, alias="profileName")
    profile_data: CandidateProfile = Field(alias="profileData")
    expected_profile_version: int | None = Field(default=None, alias="expectedProfileVersion")

    model_config = ConfigDict(populate_by_name=True)


def normalize_keyword_priority_score(value: Any) -> int:
    if value is None or value == "":
        return 50
    score = int(round(float(value)))
    if 0 <= score <= 10:
        return score * 10
    return score


def keyword_priority_from_score(score: int) -> KeywordPriority:
    if score >= 70:
        return KeywordPriority.high
    if score >= 40:
        return KeywordPriority.medium
    return KeywordPriority.low


def keyword_confidence_from_legacy(value: Any) -> KeywordConfidence:
    if isinstance(value, str) and value.lower() in {"high", "medium", "low"}:
        return KeywordConfidence(value.lower())
    try:
        score = float(value)
    except (TypeError, ValueError):
        return KeywordConfidence.medium
    if score > 1:
        score = score / 100
    if score >= 0.85:
        return KeywordConfidence.high
    if score >= 0.55:
        return KeywordConfidence.medium
    return KeywordConfidence.low


class JobKeywordAnalysisItem(BaseModel):
    id: str
    value: str = Field(min_length=1)
    normalized_value: str = Field(min_length=1, alias="normalizedValue")
    category: str = Field(default="General", min_length=1)
    source_type: KeywordSourceType = Field(default=KeywordSourceType.inferred, alias="sourceType")
    confidence: KeywordConfidence = KeywordConfidence.medium
    priority: KeywordPriority = KeywordPriority.medium
    priority_score: int = Field(default=50, ge=0, le=100, alias="priorityScore")
    direct_from_jd: bool = Field(default=False, alias="directFromJD")
    evidence_text: str | None = Field(default=None, alias="evidenceText")
    source_sentence: str | None = Field(default=None, alias="sourceSentence")
    reason: str | None = None
    occurrence_count: int = Field(default=1, ge=1, alias="occurrenceCount")

    # Deprecated compatibility fields. Keep these until all frontend/backend call sites use the typed fields.
    term: str = ""
    recruiter_weight: int = Field(default=5, alias="recruiterWeight")
    explicit: bool = False

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def populate_typed_keyword_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        values = dict(data)
        value = str(values.get("value") or values.get("term") or "").strip()
        category = str(values.get("category") or "General").strip()
        priority_score = normalize_keyword_priority_score(
            values.get("priorityScore", values.get("priority_score"))
        )
        legacy_priority = str(values.get("priority") or "").lower()
        explicit = bool(values.get("explicit", False))

        if "id" not in values and value:
            values["id"] = f"{category}:{value}".lower().replace(" ", "-")
        values["value"] = value
        values["term"] = str(values.get("term") or value).strip()
        values["normalizedValue"] = str(
            values.get("normalizedValue") or values.get("normalized_value") or value
        ).strip()
        values["category"] = category
        values["priorityScore"] = priority_score
        if legacy_priority in {"critical", "important", "preferred"} or "priority" not in values:
            values["priority"] = keyword_priority_from_score(priority_score).value
        values["confidence"] = keyword_confidence_from_legacy(values.get("confidence"))

        source_type = values.get("sourceType", values.get("source_type"))
        if source_type is None:
            source_type = KeywordSourceType.explicit.value if explicit else KeywordSourceType.inferred.value
        values["sourceType"] = source_type

        if "directFromJD" not in values and "direct_from_jd" not in values:
            values["directFromJD"] = source_type == KeywordSourceType.explicit.value and explicit

        if "occurrenceCount" not in values and "occurrence_count" not in values:
            values["occurrenceCount"] = 1

        return values

    @field_validator("value", "normalized_value", "category")
    @classmethod
    def reject_blank_keyword_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("keyword text fields must not be blank")
        return cleaned

    @model_validator(mode="after")
    def validate_source_consistency(self) -> "JobKeywordAnalysisItem":
        if self.direct_from_jd and self.source_type != KeywordSourceType.explicit:
            raise ValueError("direct_from_jd can only be true when source_type is explicit")
        if self.source_type == KeywordSourceType.explicit and self.direct_from_jd:
            has_evidence = bool((self.evidence_text or "").strip() or (self.source_sentence or "").strip())
            if not has_evidence:
                # Current extraction has not yet wired evidence text. Keep compatibility for now.
                self.reason = self.reason or "Explicit keyword accepted without evidence during legacy migration."
        self.term = self.term or self.value
        self.explicit = self.source_type == KeywordSourceType.explicit and self.direct_from_jd
        return self


class ExcludedKeywordItem(BaseModel):
    value: str = Field(min_length=1)
    normalized_value: str = Field(min_length=1, alias="normalizedValue")
    reason: str = Field(min_length=1)
    original_source_type: KeywordSourceType | None = Field(default=None, alias="originalSourceType")

    model_config = ConfigDict(populate_by_name=True)


class RequirementResumeEvidence(BaseModel):
    primary_placement: list[str] = Field(default_factory=list, alias="primaryPlacement")
    secondary_placement: list[str] = Field(default_factory=list, alias="secondaryPlacement")
    avoid_placement: list[str] = Field(default_factory=list, alias="avoidPlacement")

    model_config = ConfigDict(populate_by_name=True)


class RequirementPriorityDetail(BaseModel):
    level: str = "Important"
    score: int = 7
    reason: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class RequirementImprovementGuidance(BaseModel):
    when_missing: list[str] = Field(default_factory=list, alias="whenMissing")

    model_config = ConfigDict(populate_by_name=True)


class RequirementConfidence(BaseModel):
    score: int = 85
    reason: str = ""

    model_config = ConfigDict(populate_by_name=True)


class RequirementQualityScore(BaseModel):
    completeness: int = 100
    specificity: int = 95
    resume_usability: int = Field(default=98, alias="resumeUsability")

    model_config = ConfigDict(populate_by_name=True)


class RequirementIntelligenceItem(BaseModel):
    id: str
    name: str
    category: str
    capability_group: str = Field(default="", alias="capabilityGroup")
    priority: str
    priority_detail: RequirementPriorityDetail = Field(default_factory=RequirementPriorityDetail, alias="priorityDetail")
    priority_reason: str = Field(default="", alias="priorityReason")
    meaning: str
    resume_evidence: RequirementResumeEvidence = Field(default_factory=RequirementResumeEvidence, alias="resumeEvidence", exclude=True)
    resume_placement_strategy: RequirementResumeEvidence = Field(default_factory=RequirementResumeEvidence, alias="resumePlacementStrategy")
    business_context: list[str] = Field(default_factory=list, alias="businessContext")
    improvement_guidance: RequirementImprovementGuidance = Field(default_factory=RequirementImprovementGuidance, alias="improvementGuidance")
    capability_id: str = Field(default="", alias="capabilityId")
    confidence: RequirementConfidence = Field(default_factory=RequirementConfidence)
    quality_score: RequirementQualityScore = Field(default_factory=RequirementQualityScore, alias="qualityScore")
    expected_resume_signals: list[str] = Field(default_factory=list, alias="expectedResumeSignals")
    canonical_terms: list[str] = Field(default_factory=list, alias="canonicalTerms")
    source_phrases: list[str] = Field(default_factory=list, alias="sourcePhrases")
    is_explicit: bool = Field(default=True, alias="isExplicit")
    parent_id: str = Field(default="", alias="parentId")
    child_ids: list[str] = Field(default_factory=list, alias="childIds")

    model_config = ConfigDict(populate_by_name=True)


class RequirementRelationship(BaseModel):
    group_id: str = Field(default="", alias="groupId")
    group_name: str = Field(default="", alias="groupName")
    requirement_ids: list[str] = Field(default_factory=list, alias="requirementIds")
    parent_id: str = Field(default="", alias="parentId")
    parent: str = ""
    child_ids: list[str] = Field(default_factory=list, alias="childIds")
    children: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class RequirementIntelligence(BaseModel):
    requirements: list[RequirementIntelligenceItem] = Field(default_factory=list)
    relationship_graph: list[RequirementRelationship] = Field(default_factory=list, alias="relationshipGraph")
    noise_removed: list[str] = Field(default_factory=list, alias="noiseRemoved")

    model_config = ConfigDict(populate_by_name=True)


class RequirementIntelligenceResponse(BaseModel):
    requirement_intelligence: RequirementIntelligence = Field(default_factory=RequirementIntelligence, alias="requirementIntelligence")

    model_config = ConfigDict(populate_by_name=True)


class RequirementIntelligenceRequest(JobAnalysisRequest):
    job_intelligence: PhaseOneJobIntelligenceResponse | None = Field(default=None, alias="jobIntelligence")

    model_config = ConfigDict(populate_by_name=True)


class CandidateEvidence(BaseModel):
    company: str = ""
    role: str = ""
    project: str = ""
    technology: str = ""
    skill: str = ""
    source: str = ""
    source_text: str = Field(default="", alias="sourceText")

    model_config = ConfigDict(populate_by_name=True)


class CandidateIntelligence(BaseModel):
    technologies: list[str] = Field(default_factory=list)
    programming_languages: list[str] = Field(default_factory=list, alias="programmingLanguages")
    frameworks: list[str] = Field(default_factory=list)
    cloud: list[str] = Field(default_factory=list)
    databases: list[str] = Field(default_factory=list)
    api: list[str] = Field(default_factory=list)
    architecture: list[str] = Field(default_factory=list)
    leadership: list[str] = Field(default_factory=list)
    testing: list[str] = Field(default_factory=list)
    documentation: list[str] = Field(default_factory=list)
    deployment: list[str] = Field(default_factory=list)
    security: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    business_context: list[str] = Field(default_factory=list, alias="businessContext")
    projects: list[dict[str, str | list[str]]] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    mentoring: list[str] = Field(default_factory=list)
    decision_making: list[str] = Field(default_factory=list, alias="decisionMaking")
    ownership: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class RequirementCoverageItem(BaseModel):
    requirement_id: str = Field(alias="requirementId")
    requirement_name: str = Field(alias="requirementName")
    capability_id: str = Field(default="", alias="capabilityId")
    coverage: str
    confidence: int
    evidence: list[CandidateEvidence] = Field(default_factory=list)
    recommended_placement: list[str] = Field(default_factory=list, alias="recommendedPlacement")
    improvement_suggestions: list[str] = Field(default_factory=list, alias="improvementSuggestions")

    model_config = ConfigDict(populate_by_name=True)


class CoverageMatrix(BaseModel):
    total: int = 0
    strong: int = 0
    moderate: int = 0
    weak: int = 0
    missing: int = 0
    coverage_percent: int = Field(default=0, alias="coveragePercent")

    model_config = ConfigDict(populate_by_name=True)


class CandidateIntelligenceRequest(JobAnalysisRequest):
    candidate_profile: CandidateProfile = Field(alias="candidate_profile")
    job_intelligence: PhaseOneJobIntelligenceResponse = Field(alias="jobIntelligence")
    requirement_intelligence: RequirementIntelligenceResponse = Field(alias="requirementIntelligence")
    existing_resume_data: ResumeContent | None = Field(default=None, alias="existingResumeData")

    model_config = ConfigDict(populate_by_name=True)


class CandidateIntelligenceResponse(BaseModel):
    candidate_intelligence: CandidateIntelligence = Field(alias="candidateIntelligence")
    requirement_coverage: list[RequirementCoverageItem] = Field(default_factory=list, alias="requirementCoverage")
    coverage_matrix: CoverageMatrix = Field(default_factory=CoverageMatrix, alias="coverageMatrix")
    improvement_suggestions: list[str] = Field(default_factory=list, alias="improvementSuggestions")

    model_config = ConfigDict(populate_by_name=True)


class ExperienceStrategyItem(BaseModel):
    company: str = ""
    role: str = ""
    strategy: str = ""
    emphasize: list[str] = Field(default_factory=list)
    de_emphasize: list[str] = Field(default_factory=list, alias="deEmphasize")
    requirements_to_cover: list[str] = Field(default_factory=list, alias="requirementsToCover")
    tone: str = ""

    model_config = ConfigDict(populate_by_name=True)


class ResumeStrategy(BaseModel):
    target_role: str = Field(default="", alias="targetRole")
    target_seniority: str = Field(default="", alias="targetSeniority")
    target_domain: str = Field(default="", alias="targetDomain")
    resume_positioning: str = Field(default="", alias="resumePositioning")
    primary_experience_focus: str = Field(default="", alias="primaryExperienceFocus")
    secondary_experience_focus: str = Field(default="", alias="secondaryExperienceFocus")
    tertiary_experience_focus: str = Field(default="", alias="tertiaryExperienceFocus")
    overall_narrative: str = Field(default="", alias="overallNarrative")
    emphasize: list[str] = Field(default_factory=list)
    de_emphasize: list[str] = Field(default_factory=list, alias="deEmphasize")
    transferable_language: list[str] = Field(default_factory=list, alias="transferableLanguage")
    domain_translation_rules: list[str] = Field(default_factory=list, alias="domainTranslationRules")
    requirements_to_cover: list[str] = Field(default_factory=list, alias="requirementsToCover")
    skills_to_prioritize: list[str] = Field(default_factory=list, alias="skillsToPrioritize")
    skills_to_avoid_or_reduce: list[str] = Field(default_factory=list, alias="skillsToAvoidOrReduce")
    experience_strategy: list[ExperienceStrategyItem] = Field(default_factory=list, alias="experienceStrategy")
    summary_strategy: str = Field(default="", alias="summaryStrategy")
    skills_strategy: str = Field(default="", alias="skillsStrategy")
    bullet_strategy: str = Field(default="", alias="bulletStrategy")
    truthfulness_rules: list[str] = Field(default_factory=list, alias="truthfulnessRules")

    model_config = ConfigDict(populate_by_name=True)


class ResumeStrategyRequest(JobAnalysisRequest):
    candidate_profile: CandidateProfile = Field(alias="candidate_profile")
    job_intelligence: PhaseOneJobIntelligenceResponse = Field(alias="jobIntelligence")
    requirement_intelligence: RequirementIntelligenceResponse = Field(alias="requirementIntelligence")
    existing_resume_data: ResumeContent | None = Field(default=None, alias="existingResumeData")

    model_config = ConfigDict(populate_by_name=True)


class ResumeStrategyResponse(BaseModel):
    resume_strategy: ResumeStrategy = Field(alias="resumeStrategy")

    model_config = ConfigDict(populate_by_name=True)


class JobAnalysisResponse(BaseModel):
    role_information: JobRoleInformation = Field(default_factory=JobRoleInformation, alias="roleInformation")
    keywords: list[JobKeywordAnalysisItem] = Field(default_factory=list)
    explicit_keywords: list[JobKeywordAnalysisItem] = Field(default_factory=list, alias="explicitKeywords")
    inferred_keywords: list[JobKeywordAnalysisItem] = Field(default_factory=list, alias="inferredKeywords")
    suggested_keywords: list[JobKeywordAnalysisItem] = Field(default_factory=list, alias="suggestedKeywords")
    excluded_terms: list[ExcludedKeywordItem] = Field(default_factory=list, alias="excludedTerms")
    technical_skills: dict[str, list[JobKeywordAnalysisItem]] = Field(default_factory=dict, alias="technicalSkills")
    leadership_competencies: list[JobKeywordAnalysisItem] = Field(default_factory=list, alias="leadershipCompetencies")
    business_competencies: list[JobKeywordAnalysisItem] = Field(default_factory=list, alias="businessCompetencies")
    responsibilities: list[JobKeywordAnalysisItem] = Field(default_factory=list)
    action_verbs: list[str] = Field(default_factory=list, alias="actionVerbs")
    explicit_ats_keywords: list[JobKeywordAnalysisItem] = Field(default_factory=list, alias="explicitAtsKeywords")
    implicit_inferred_skills: list[JobKeywordAnalysisItem] = Field(default_factory=list, alias="implicitInferredSkills")
    hidden_inferred_skills: list[JobKeywordAnalysisItem] = Field(default_factory=list, alias="hiddenInferredSkills")
    ats_focus_areas: list[str] = Field(default_factory=list, alias="atsFocusAreas")
    noise_terms_to_exclude: list[str] = Field(default_factory=list, alias="noiseTermsToExclude")
    total_extracted_keywords: int = Field(default=0, alias="totalExtractedKeywords")
    analysis_hash: str = Field(default="", alias="analysisHash")

    model_config = ConfigDict(populate_by_name=True)
