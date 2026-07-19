from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.skill_normalization import (
    approved_skill_category_name,
    has_category_prefix,
    is_approved_skill_category_id,
    is_ambiguous_skill_category_alias,
    normalize_skill_name,
    resolve_skill_category_definition,
    skill_category_id,
)


US_STATE_ABBREVIATIONS = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "dc", "fl", "ga", "il", "ma", "mo", "nj", "ny", "pa", "tx", "va", "wa"
}
INDIAN_STATE_NAMES = {
    "andhra pradesh", "telangana", "karnataka", "tamil nadu", "maharashtra", "kerala", "delhi", "gujarat", "west bengal"
}


class ProfileLocation(BaseModel):
    city: str = ""
    state: str | None = None
    country: str = ""

    @field_validator("city", "country")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return _trimmed(value)

    @field_validator("state")
    @classmethod
    def normalize_state(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = _trimmed(value)
        return value or None

    @model_validator(mode="after")
    def validate_country(self):
        country_key = self.country.casefold()
        if self.country and self.city and country_key == self.city.casefold():
            raise ValueError("Location country cannot equal city.")
        if self.country and country_key in US_STATE_ABBREVIATIONS:
            raise ValueError("Location country cannot be a US state abbreviation.")
        if self.country and country_key in INDIAN_STATE_NAMES:
            raise ValueError("Location country cannot be an Indian state name.")
        return self


class ResumeContact(BaseModel):
    phone: str = ""
    email: str = ""
    location: str = ""
    location_data: ProfileLocation | None = Field(default=None, alias="locationData")
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""

    model_config = ConfigDict(populate_by_name=True)


class SkillCategory(BaseModel):
    category: str = ""
    category_id: str = Field(default="", alias="categoryId")
    category_name: str = Field(default="", alias="categoryName")
    order: int = 0
    items: list[str] = Field(default_factory=list)
    migration_review_required: bool = Field(default=False, alias="migrationReviewRequired")
    legacy_unparsed: str = Field(default="", alias="legacyUnparsed")

    @model_validator(mode="before")
    @classmethod
    def normalize_category_aliases(cls, data):
        if isinstance(data, dict):
            normalized = dict(data)
            category_name = normalized.get("categoryName") or normalized.get("category") or ""
            category_id = str(normalized.get("categoryId") or "")
            definition = resolve_skill_category_definition(category_id) or resolve_skill_category_definition(str(category_name))
            if definition:
                normalized["category"] = definition.category_name
                normalized["categoryName"] = definition.category_name
                normalized["categoryId"] = definition.category_id
                if str(category_name).strip() and str(category_name).strip().casefold() != definition.category_name.casefold():
                    normalized["migrationReviewRequired"] = True
            else:
                normalized["category"] = category_name
                normalized["categoryName"] = category_name
                normalized["categoryId"] = category_id or skill_category_id(str(category_name))
                if is_ambiguous_skill_category_alias(str(category_name)) or category_name:
                    normalized["migrationReviewRequired"] = normalized.get("migrationReviewRequired", True)
            return normalized
        return data

    @field_validator("category", "category_name", "category_id")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = _trimmed(value)
        if not value:
            raise ValueError("Skill category name and ID are required.")
        return value

    @field_validator("order")
    @classmethod
    def valid_order(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Skill category order must be non-negative.")
        return value

    @field_validator("items")
    @classmethod
    def normalize_items(cls, value: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        duplicates: set[str] = set()
        prefixed: list[str] = []
        for item in value:
            skill = normalize_skill_name(item)
            if not skill:
                continue
            if has_category_prefix(skill):
                prefixed.append(skill)
            key = skill.casefold()
            if key in seen:
                duplicates.add(skill)
            seen.add(key)
            output.append(skill)
        if prefixed:
            raise ValueError(f"Skill items cannot contain category labels: {', '.join(prefixed)}")
        if duplicates:
            raise ValueError(f"Duplicate skills inside one category are not allowed: {', '.join(sorted(duplicates))}")
        return output

    model_config = ConfigDict(populate_by_name=True)


class ResumeExperience(BaseModel):
    experience_id: str = Field(default="", alias="experienceId")
    company: str
    client_name: str | None = Field(default=None, alias="clientName")
    role: str
    location: str = ""
    location_data: ProfileLocation | None = Field(default=None, alias="locationData")
    start_date: str = Field(default="", alias="startDate")
    start_date_data: "ProfileExperienceDate | None" = Field(default=None, alias="startDateData")
    end_date: str = Field(default="", alias="endDate")
    end_date_data: "ProfileExperienceDate | None" = Field(default=None, alias="endDateData")
    is_current_role: bool = Field(default=False, alias="isCurrentRole")
    raw_notes: str = Field(default="", alias="rawNotes")
    bullets: list[str] = Field(default_factory=list)
    metric_flags: list[str] = Field(default_factory=list, alias="metricFlags")
    responsibilities: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    metrics: list["ExperienceMetric"] = Field(default_factory=list)
    legacy_notes: str = Field(default="", alias="legacyNotes")
    migration_review_required: bool = Field(default=False, alias="migrationReviewRequired")

    @field_validator("client_name", mode="before")
    @classmethod
    def blank_client_to_none(cls, value):
        if value is None:
            return None
        value = _trimmed(str(value))
        return value or None

    @field_validator("responsibilities", "achievements", "technologies", mode="before")
    @classmethod
    def normalize_string_array(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            value = value.splitlines()
        seen: set[str] = set()
        output: list[str] = []
        for item in value:
            text = re.sub(r"^\d+[.)]\s*", "", _trimmed(str(item)))
            key = text.casefold()
            if text and key not in seen:
                seen.add(key)
                output.append(text)
        return output

    @model_validator(mode="after")
    def validate_structured_experience(self):
        if self.is_current_role:
            self.end_date_data = None
            if not self.end_date:
                self.end_date = "Present"
        if self.start_date_data and self.end_date_data and (self.end_date_data.year, self.end_date_data.month or 1) < (
            self.start_date_data.year,
            self.start_date_data.month or 1,
        ):
            raise ValueError("Experience endDate must not be before startDate.")
        return self

    model_config = ConfigDict(populate_by_name=True)


class ProfileExperienceDate(BaseModel):
    month: int
    year: int

    @field_validator("month")
    @classmethod
    def valid_month(cls, value: int) -> int:
        if value < 0 or value > 12:
            raise ValueError("Experience month must be between 0 and 12.")
        return value

    @field_validator("year")
    @classmethod
    def valid_year(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Experience year must be non-negative.")
        return value


class ExperienceMetric(BaseModel):
    metric_id: str = Field(default="", alias="metricId")
    label: str = ""
    value: str = ""

    @model_validator(mode="after")
    def require_label_and_value_together(self):
        self.label = _trimmed(self.label)
        self.value = _trimmed(self.value)
        if bool(self.label) != bool(self.value):
            raise ValueError("Experience metrics require both label and value.")
        return self

    model_config = ConfigDict(populate_by_name=True)


class ResumeProject(BaseModel):
    project_id: str = Field(default="", alias="projectId")
    name: str
    org: str = ""
    link: str = ""
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    linked_experience_ids: list[str] = Field(default_factory=list, alias="linkedExperienceIds")

    @field_validator("linked_experience_ids")
    @classmethod
    def validate_linked_experience_ids(cls, value: list[str]) -> list[str]:
        cleaned = [_trimmed(item) for item in value]
        if any(not item for item in cleaned):
            raise ValueError("Project linkedExperienceIds cannot contain blank IDs.")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("Project linkedExperienceIds cannot contain duplicate IDs.")
        return cleaned

    model_config = ConfigDict(populate_by_name=True)


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
    first_name: str = Field(default="", alias="firstName")
    last_name: str = Field(default="", alias="lastName")
    title: str = ""
    contact: ResumeContact = Field(default_factory=ResumeContact)
    summary: str = ""
    skills: list[SkillCategory] = Field(default_factory=list)
    experience: list[ResumeExperience] = Field(default_factory=list)
    projects: list[ResumeProject] = Field(default_factory=list)
    education: list[ResumeEducation] = Field(default_factory=list)
    certifications: list[ResumeCertification] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_profile_identity(self):
        self.name = _trimmed(self.name)
        self.first_name = _trimmed(self.first_name)
        self.last_name = _trimmed(self.last_name)
        if not self.name and (self.first_name or self.last_name):
            self.name = _trimmed(f"{self.first_name} {self.last_name}")
        if self.name and not (self.first_name or self.last_name):
            parts = self.name.split()
            self.first_name = parts[0] if parts else ""
            self.last_name = " ".join(parts[1:])
        return self

    @model_validator(mode="after")
    def validate_project_experience_links(self):
        valid_experience_ids = {item.experience_id for item in self.experience if item.experience_id}
        for project in self.projects:
            missing = [experience_id for experience_id in project.linked_experience_ids if experience_id not in valid_experience_ids]
            if missing:
                raise ValueError(f"PROJECT_LINK_TARGET_NOT_FOUND: {project.name or project.project_id} references {', '.join(missing)}.")
        return self

    model_config = ConfigDict(populate_by_name=True)


def _trimmed(value: str) -> str:
    return " ".join(value.strip().split())


class CandidateLocation(BaseModel):
    city: str
    state: str | None = None
    country: str
    display_value: str = Field(alias="displayValue")

    @field_validator("city", "country", "display_value")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = _trimmed(value)
        if not value:
            raise ValueError("Location city, country, and displayValue are required.")
        return value

    @field_validator("state")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = _trimmed(value)
        return value or None

    @model_validator(mode="after")
    def validate_country(self):
        country_key = self.country.casefold()
        if self.country and self.city and country_key == self.city.casefold():
            raise ValueError("Location country cannot equal city.")
        if self.country and country_key in US_STATE_ABBREVIATIONS:
            raise ValueError("Location country cannot be a US state abbreviation.")
        if self.country and country_key in INDIAN_STATE_NAMES:
            raise ValueError("Location country cannot be an Indian state name.")
        return self

    model_config = ConfigDict(populate_by_name=True)


class CandidateSnapshot(BaseModel):
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")
    current_title: str = Field(alias="currentTitle")
    email: str
    phone: str
    location: CandidateLocation

    @field_validator("first_name", "last_name", "current_title", "phone")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = _trimmed(value)
        if not value:
            raise ValueError("Candidate firstName, lastName, currentTitle, and phone are required.")
        return value

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = _trimmed(value)
        if not value or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value):
            raise ValueError("A valid candidate email is required.")
        return value

    model_config = ConfigDict(populate_by_name=True)


class SkillCategorySnapshot(BaseModel):
    category_id: str = Field(alias="categoryId")
    category_name: str = Field(alias="categoryName")
    order: int
    items: list[str]

    @field_validator("category_id", "category_name")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = _trimmed(value)
        if not value:
            raise ValueError("Skill categoryId and categoryName are required.")
        return value

    @field_validator("order")
    @classmethod
    def order_must_be_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Skill category order must be non-negative.")
        return value

    @field_validator("items")
    @classmethod
    def normalize_skill_items(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        duplicates: set[str] = set()
        prefixed: list[str] = []
        for item in value:
            skill = normalize_skill_name(item)
            if not skill:
                continue
            if has_category_prefix(skill):
                prefixed.append(skill)
            key = skill.casefold()
            if key not in seen:
                normalized.append(skill)
                seen.add(key)
            else:
                duplicates.add(skill)
        if prefixed:
            raise ValueError(f"Skill items cannot contain category labels: {', '.join(prefixed)}")
        if duplicates:
            raise ValueError(f"Duplicate skills inside one category are not allowed: {', '.join(sorted(duplicates))}")
        if not normalized:
            raise ValueError("Every skill category must contain at least one skill.")
        return normalized

    @model_validator(mode="after")
    def validate_approved_category(self):
        if not is_approved_skill_category_id(self.category_id):
            raise ValueError(f"Unknown skill categoryId is not allowed in generate requests: {self.category_id}")
        expected_name = approved_skill_category_name(self.category_id)
        if expected_name and self.category_name != expected_name:
            raise ValueError(f"Skill categoryName must match approved category {expected_name}.")
        return self

    model_config = ConfigDict(populate_by_name=True)


class ExperienceDateSnapshot(BaseModel):
    month: int
    year: int
    display_value: str = Field(alias="displayValue")

    @field_validator("month")
    @classmethod
    def month_in_range(cls, value: int) -> int:
        if value < 0 or value > 12:
            raise ValueError("Experience date month must be between 0 and 12.")
        return value

    @field_validator("year")
    @classmethod
    def year_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Experience date year must be non-negative.")
        return value

    @field_validator("display_value")
    @classmethod
    def required_display_value(cls, value: str) -> str:
        value = _trimmed(value)
        if not value:
            raise ValueError("Experience date displayValue is required.")
        return value

    model_config = ConfigDict(populate_by_name=True)


class WorkExperienceSnapshot(BaseModel):
    experience_id: str = Field(alias="experienceId")
    company_name: str = Field(alias="companyName")
    client_name: str | None = Field(default=None, alias="clientName")
    role_title: str = Field(alias="roleTitle")
    location: CandidateLocation
    start_date: ExperienceDateSnapshot = Field(alias="startDate")
    end_date: ExperienceDateSnapshot | None = Field(default=None, alias="endDate")
    is_current_role: bool = Field(alias="isCurrentRole")

    @model_validator(mode="before")
    @classmethod
    def reject_generated_bullet_fields(cls, data):
        if isinstance(data, dict):
            banned = {"bullets", "resumePoints", "generatedBullets", "generatedResponsibilities", "tailoredPoints"}
            present = sorted(key for key in banned if key in data)
            if present:
                raise ValueError(f"Generated resume bullet fields are not accepted in workExperience: {', '.join(present)}")
        return data

    @field_validator("experience_id", "company_name", "role_title")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = _trimmed(value)
        if not value:
            raise ValueError("Experience ID, companyName, and roleTitle are required.")
        return value

    @field_validator("client_name")
    @classmethod
    def normalize_client_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = _trimmed(value)
        return value or None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.is_current_role:
            if self.end_date is not None:
                raise ValueError("endDate must be null when isCurrentRole is true.")
            return self
        if self.end_date is None:
            raise ValueError("endDate is required when isCurrentRole is false.")
        start_key = (self.start_date.year, self.start_date.month)
        end_key = (self.end_date.year, self.end_date.month)
        if all(start_key) and all(end_key) and end_key < start_key:
            raise ValueError("Experience endDate must not be before startDate.")
        return self

    model_config = ConfigDict(populate_by_name=True)


class JobSnapshot(BaseModel):
    description: str
    target_role: str = Field(alias="targetRole")
    target_company: str | None = Field(default=None, alias="targetCompany")
    level: str | None = None

    @field_validator("description", "target_role")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = _trimmed(value)
        if not value:
            raise ValueError("Job description and targetRole are required.")
        return value

    @field_validator("target_company", "level")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = _trimmed(value)
        return value or None

    model_config = ConfigDict(populate_by_name=True)


class HeaderVisibility(BaseModel):
    full_name: bool = Field(alias="fullName")
    current_title: bool = Field(alias="currentTitle")
    email: bool
    phone: bool
    location: bool
    linkedin_url: bool = Field(default=False, alias="linkedinUrl")
    github_url: bool = Field(default=False, alias="githubUrl")
    portfolio_url: bool = Field(default=False, alias="portfolioUrl")

    model_config = ConfigDict(populate_by_name=True)


class SectionVisibility(BaseModel):
    summary: bool
    skills: bool
    experience: bool
    projects: bool
    education: bool
    certifications: bool


class ResumePreferences(BaseModel):
    template_id: str = Field(alias="templateId")
    header_visibility: HeaderVisibility = Field(alias="headerVisibility")
    section_visibility: SectionVisibility = Field(alias="sectionVisibility")

    @field_validator("template_id")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = _trimmed(value)
        if not value:
            raise ValueError("resumePreferences.templateId is required.")
        return value

    model_config = ConfigDict(populate_by_name=True)


class GenerateResumeRequest(BaseModel):
    job_description: str = Field(default="", alias="job_description")
    target_role: str = Field(default="", alias="target_role")
    target_company: str = Field(default="", alias="target_company")
    level: str = "Senior"
    tone: str = "Professional"
    length: str = "1 page"
    candidate_profile: CandidateProfile | None = Field(default=None, alias="candidate_profile")
    job_analysis: JobAnalysisResponse | None = Field(default=None, alias="jobAnalysis")
    resume_intelligence_package_id: str = Field(default="", alias="resumeIntelligencePackageId")
    profile_id: str = Field(default="", alias="profileId")
    profile_version: int | None = Field(default=None, alias="profileVersion")
    candidate: CandidateSnapshot | None = None
    skills: list[SkillCategorySnapshot] | None = None
    work_experience: list[WorkExperienceSnapshot] | None = Field(default=None, alias="workExperience")
    job: JobSnapshot | None = None
    resume_preferences: ResumePreferences | None = Field(default=None, alias="resumePreferences")
    template_id: str = Field(default="classic-ats", alias="templateId")
    generation_settings: ResumeGenerationSettings = Field(default_factory=lambda: ResumeGenerationSettings(), alias="generationSettings")
    paper_size: str = Field(default="US Letter", alias="paper_size")

    @model_validator(mode="before")
    @classmethod
    def normalize_canonical_request(cls, data):
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        job = normalized.get("job")
        if isinstance(job, dict):
            normalized["job_description"] = job.get("description", "")
            normalized["target_role"] = job.get("targetRole", "")
            normalized["target_company"] = job.get("targetCompany") or ""
            if job.get("level") is not None:
                normalized["level"] = job.get("level") or ""
        preferences = normalized.get("resumePreferences")
        if isinstance(preferences, dict) and preferences.get("templateId"):
            normalized["templateId"] = preferences["templateId"]
        return normalized

    @model_validator(mode="after")
    def validate_generate_request(self):
        self.job_description = _trimmed(self.job_description)
        self.target_role = _trimmed(self.target_role)
        self.target_company = _trimmed(self.target_company)
        self.level = _trimmed(self.level) or "Senior"
        if not self.job_description:
            raise ValueError("Job description is required.")
        if not self.target_role:
            raise ValueError("Target role is required.")
        if self.skills is not None:
            category_ids: set[str] = set()
            duplicate_category_ids: set[str] = set()
            for category in self.skills:
                if category.category_id in category_ids:
                    duplicate_category_ids.add(category.category_id)
                category_ids.add(category.category_id)
            if duplicate_category_ids:
                raise ValueError(f"Duplicate skill category IDs are not allowed: {', '.join(sorted(duplicate_category_ids))}")
        return self

    @property
    def has_canonical_profile_snapshot(self) -> bool:
        return any(
            value is not None
            for value in (self.profile_version, self.candidate, self.skills, self.work_experience, self.job, self.resume_preferences)
        )

    model_config = ConfigDict(populate_by_name=True)


class ResumeContent(CandidateProfile):
    pass


class AtsBreakdown(BaseModel):
    keyword_match: int = Field(alias="keywordMatch")
    formatting: int
    readability: int
    matched_keywords: list[str] = Field(default_factory=list, alias="matchedKeywords")
    missing_keywords: list[str] = Field(default_factory=list, alias="missingKeywords")
    coverage: dict[str, list[dict[str, str]]] = Field(
        default_factory=lambda: {
            "supportedAndCovered": [],
            "supportedButNotRepresented": [],
            "adjacentUnsupported": [],
            "unmatched": [],
            "suggestedExcluded": [],
        }
    )

    model_config = ConfigDict(populate_by_name=True)


class AtsAnalysisBreakdown(BaseModel):
    keyword_match: int = Field(default=0, alias="keywordMatch")
    formatting: int = 0
    readability: int = 0
    matched_keywords: list[str] = Field(default_factory=list, alias="matchedKeywords")
    missing_keywords: list[str] = Field(default_factory=list, alias="missingKeywords")

    model_config = ConfigDict(populate_by_name=True)


class ResumeSuggestion(BaseModel):
    text: str
    points: int


def default_coverage() -> dict[str, list[dict[str, str]]]:
    return {
        "supportedAndCovered": [],
        "supportedButNotRepresented": [],
        "adjacentUnsupported": [],
        "unmatched": [],
        "suggestedExcluded": [],
    }


class AtsAnalysis(BaseModel):
    score: int = 0
    breakdown: AtsAnalysisBreakdown = Field(default_factory=AtsAnalysisBreakdown)
    coverage: dict[str, list[dict[str, str]]] = Field(default_factory=default_coverage)
    suggestions: list[ResumeSuggestion] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


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


class GenerationMetadata(BaseModel):
    model: str | None = None
    duration_ms: int = Field(default=0, alias="durationMs")
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), alias="generatedAt")
    pipeline_version: str = Field(default="", alias="pipelineVersion")

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


class GeneratedResumeBullet(BaseModel):
    bullet_id: str = Field(alias="bulletId")
    order: int
    generated_text: str = Field(default="", alias="generatedText")
    current_text: str = Field(alias="currentText")
    user_edited: bool = Field(default=False, alias="userEdited")
    supported_requirement_ids: list[str] = Field(default_factory=list, alias="supportedRequirementIds")
    supporting_evidence_ids: list[str] = Field(default_factory=list, alias="supportingEvidenceIds")
    validation_status: str = Field(default="validated", alias="validationStatus")
    warnings: list[str] = Field(default_factory=list)
    generation_method: str = Field(default="deterministic", alias="generationMethod")
    model: str = ""
    prompt_version: str = Field(default="", alias="promptVersion")

    @model_validator(mode="after")
    def sync_user_edited(self):
        if self.generated_text and self.current_text != self.generated_text:
            self.user_edited = True
        return self

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
    resume_header: dict[str, str] = Field(default_factory=dict, alias="resumeHeader")
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
    resume_id: str = Field(default="", alias="resumeId")
    # Deprecated compatibility field. Derived from structuredResume for older clients.
    resume: ResumeContent
    ats_analysis: AtsAnalysis = Field(default_factory=AtsAnalysis, alias="atsAnalysis")
    # Deprecated compatibility aliases. Canonical values live under atsAnalysis.
    ats_score: int = Field(default=0, alias="atsScore")
    breakdown: AtsBreakdown = Field(default_factory=lambda: AtsBreakdown(keywordMatch=0, formatting=0, readability=0))
    suggestions: list[ResumeSuggestion] = Field(default_factory=list)
    generation_metadata: GenerationMetadata = Field(default_factory=GenerationMetadata, alias="generationMetadata")
    # Internal diagnostics. Omitted from normal public serialization by default.
    layout_contract: LayoutContract | None = Field(default=None, alias="layoutContract", exclude=True)
    semantic_plan: SemanticRequirementPlan | None = Field(default=None, alias="semanticPlan", exclude=True)
    # Deprecated compatibility alias. Canonical generation execution data lives under generationMetadata.
    ai_metrics: ResumeAiMetrics = Field(default_factory=ResumeAiMetrics, alias="aiMetrics")
    structured_resume: StructuredGeneratedResume | None = Field(default=None, alias="structuredResume")
    validation_result: ResumeValidationResult | None = Field(default=None, alias="validationResult")
    # Deprecated compatibility alias. Always synchronized from resumeId.
    persisted_resume_id: str = Field(default="", alias="persistedResumeId")

    @model_validator(mode="after")
    def sync_canonical_and_legacy_fields(self):
        if self.resume_id:
            self.persisted_resume_id = self.resume_id
        elif self.persisted_resume_id:
            self.resume_id = self.persisted_resume_id

        has_canonical_ats = (
            self.ats_analysis.score
            or self.ats_analysis.breakdown.keyword_match
            or self.ats_analysis.breakdown.formatting
            or self.ats_analysis.breakdown.readability
            or self.ats_analysis.coverage != default_coverage()
            or self.ats_analysis.suggestions
        )
        if not has_canonical_ats:
            self.ats_analysis = AtsAnalysis(
                score=self.ats_score,
                breakdown=AtsAnalysisBreakdown(
                    keywordMatch=self.breakdown.keyword_match,
                    formatting=self.breakdown.formatting,
                    readability=self.breakdown.readability,
                    matchedKeywords=self.breakdown.matched_keywords,
                    missingKeywords=self.breakdown.missing_keywords,
                ),
                coverage=self.breakdown.coverage,
                suggestions=self.suggestions,
            )

        self.ats_score = self.ats_analysis.score
        self.breakdown = AtsBreakdown(
            keywordMatch=self.ats_analysis.breakdown.keyword_match,
            formatting=self.ats_analysis.breakdown.formatting,
            readability=self.ats_analysis.breakdown.readability,
            matchedKeywords=self.ats_analysis.breakdown.matched_keywords,
            missingKeywords=self.ats_analysis.breakdown.missing_keywords,
            coverage=self.ats_analysis.coverage,
        )
        self.suggestions = list(self.ats_analysis.suggestions)

        if not self.generation_metadata.pipeline_version and self.structured_resume:
            self.generation_metadata.pipeline_version = self.structured_resume.generation_algorithm_version
        if not self.generation_metadata.generated_at and self.structured_resume:
            self.generation_metadata.generated_at = self.structured_resume.created_at
        self.ai_metrics = self.ai_metrics.model_copy(
            update={
                "generation_time_ms": self.generation_metadata.duration_ms,
                "models_used": [self.generation_metadata.model] if self.generation_metadata.model else [],
                "ats_score": self.ats_analysis.score,
            }
        )
        return self

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
    project_id: str | None = Field(default=None, alias="projectId")
    linked_experience_ids: list[str] = Field(default_factory=list, alias="linkedExperienceIds")
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
    job_description: str = Field(default="", alias="jobDescription")
    target_role: str = Field(default="", alias="targetRole")
    target_company: str = Field(default="", alias="targetCompany")
    level: str = "Senior"
    generation_settings: ResumeGenerationSettings = Field(default_factory=ResumeGenerationSettings, alias="generationSettings")

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
    package_id: str = Field(default="", alias="packageId")
    job_description_hash: str = Field(default="", alias="jobDescriptionHash")
    summary_intelligence: SummaryIntelligence | None = Field(default=None, alias="summaryIntelligence")
    experience_intelligence: ExperienceIntelligencePlan | None = Field(default=None, alias="experienceIntelligence")
    validation_status: str = Field(default="", alias="validationStatus")
    validation_warnings: list[str] = Field(default_factory=list, alias="validationWarnings")

    model_config = ConfigDict(populate_by_name=True)


class SummaryIntelligence(BaseModel):
    summary: str
    selected_technologies: list[str] = Field(default_factory=list, alias="selectedTechnologies")
    selected_capabilities: list[str] = Field(default_factory=list, alias="selectedCapabilities")
    used_evidence_ids: list[str] = Field(default_factory=list, alias="usedEvidenceIds")
    excluded_jd_terms: list[str] = Field(default_factory=list, alias="excludedJdTerms")
    risk_flags: list[str] = Field(default_factory=list, alias="riskFlags")
    validation_status: str = Field(alias="validationStatus")
    validation_warnings: list[str] = Field(default_factory=list, alias="validationWarnings")
    generation_mode: str = Field(alias="generationMode")
    model: str
    profile_id: str = Field(alias="profileId")
    profile_version: int = Field(alias="profileVersion")
    profile_hash: str = Field(alias="profileHash")
    job_description_hash: str = Field(alias="jobDescriptionHash")
    target_role: str = Field(alias="targetRole")
    target_company: str = Field(default="", alias="targetCompany")
    level: str
    prompt_version: str = Field(default="", alias="promptVersion")
    model_configuration_hash: str = Field(default="", alias="modelConfigurationHash")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), alias="createdAt")

    @field_validator("summary", "validation_status", "generation_mode", "model", "profile_id", "profile_hash", "job_description_hash", "target_role", "level")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = _trimmed(value)
        if not value:
            raise ValueError("Summary Intelligence requires non-empty summary metadata.")
        return value

    @model_validator(mode="after")
    def validate_status(self):
        if self.validation_status not in {"valid", "invalid", "fallback"}:
            raise ValueError("summaryIntelligence.validationStatus must be valid, invalid, or fallback.")
        if self.validation_status == "invalid":
            raise ValueError("Invalid Summary Intelligence cannot be stored for package reuse.")
        return self

    model_config = ConfigDict(populate_by_name=True)


class ExperienceEvidenceSelection(BaseModel):
    evidence_id: str = Field(alias="evidenceId")
    evidence_type: str = Field(alias="evidenceType")
    text: str
    source_record_id: str = Field(alias="sourceRecordId")
    project_id: str = Field(default="", alias="projectId")
    linked_experience_ids: list[str] = Field(default_factory=list, alias="linkedExperienceIds")
    relevance_score: float = Field(default=0.0, ge=0.0, le=100.0, alias="relevanceScore")
    recency_score: float = Field(default=0.0, ge=0.0, le=100.0, alias="recencyScore")
    strength_score: float = Field(default=0.0, ge=0.0, le=100.0, alias="strengthScore")
    selection_reason: str = Field(default="", alias="selectionReason")

    model_config = ConfigDict(populate_by_name=True)


class ExperienceTechnologySelection(BaseModel):
    name: str
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")
    support_level: str = Field(default="verified", alias="supportLevel")
    selection_reason: str = Field(default="", alias="selectionReason")

    model_config = ConfigDict(populate_by_name=True)


class ExperienceCapabilitySelection(BaseModel):
    name: str
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")
    supported_requirement_ids: list[str] = Field(default_factory=list, alias="supportedRequirementIds")
    selection_reason: str = Field(default="", alias="selectionReason")

    model_config = ConfigDict(populate_by_name=True)


class ExperienceRolePlan(BaseModel):
    experience_id: str = Field(alias="experienceId")
    role_title: str = Field(alias="roleTitle")
    company: str = ""
    role_family: str = Field(default="", alias="roleFamily")
    bullet_count: int = Field(default=0, ge=0, alias="bulletCount")
    selected_evidence: list[ExperienceEvidenceSelection] = Field(default_factory=list, alias="selectedEvidence")
    selected_technologies: list[ExperienceTechnologySelection] = Field(default_factory=list, alias="selectedTechnologies")
    selected_capabilities: list[ExperienceCapabilitySelection] = Field(default_factory=list, alias="selectedCapabilities")
    supported_requirement_ids: list[str] = Field(default_factory=list, alias="supportedRequirementIds")
    bullet_themes: list[str] = Field(default_factory=list, alias="bulletThemes")
    excluded_jd_terms: list[str] = Field(default_factory=list, alias="excludedJdTerms")
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class ExperiencePromptRoleContext(BaseModel):
    role_title: str = Field(alias="roleTitle")
    company_name: str = Field(alias="companyName")
    client_name: str | None = Field(default=None, alias="clientName")
    is_current_role: bool = Field(default=False, alias="isCurrentRole")
    role_family: str = Field(default="", alias="roleFamily")

    model_config = ConfigDict(populate_by_name=True)


class ExperiencePromptTargetContext(BaseModel):
    target_role: str = Field(default="", alias="targetRole")
    target_company: str = Field(default="", alias="targetCompany")
    level: str = "Senior"
    target_themes: list[str] = Field(default_factory=list, alias="targetThemes")

    model_config = ConfigDict(populate_by_name=True)


class ExperiencePromptEvidence(BaseModel):
    evidence_id: str = Field(alias="evidenceId")
    evidence_type: str = Field(alias="evidenceType")
    text: str
    source_record_id: str = Field(alias="sourceRecordId")
    project_id: str | None = Field(default=None, alias="projectId")

    model_config = ConfigDict(populate_by_name=True)


class ExperiencePromptTechnology(BaseModel):
    name: str
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")

    model_config = ConfigDict(populate_by_name=True)


class ExperiencePromptCapability(BaseModel):
    name: str
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")
    supported_requirement_ids: list[str] = Field(default_factory=list, alias="supportedRequirementIds")

    model_config = ConfigDict(populate_by_name=True)


class ExperiencePromptMetric(BaseModel):
    value: str
    context: str
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")

    model_config = ConfigDict(populate_by_name=True)


class ExperiencePromptProject(BaseModel):
    project_id: str = Field(alias="projectId")
    project_name: str = Field(alias="projectName")
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")
    technologies: list[str] = Field(default_factory=list)
    approved_facts: list[str] = Field(default_factory=list, alias="approvedFacts")

    model_config = ConfigDict(populate_by_name=True)


class ExperienceWritingRules(BaseModel):
    bullet_count: int = Field(default=0, ge=0, alias="bulletCount")
    maximum_words_per_bullet: int = Field(default=30, ge=1, alias="maximumWordsPerBullet")
    use_only_approved_evidence: bool = Field(default=True, alias="useOnlyApprovedEvidence")
    do_not_invent_metrics: bool = Field(default=True, alias="doNotInventMetrics")
    do_not_invent_technologies: bool = Field(default=True, alias="doNotInventTechnologies")
    do_not_invent_leadership: bool = Field(default=True, alias="doNotInventLeadership")
    do_not_invent_architecture_ownership: bool = Field(default=True, alias="doNotInventArchitectureOwnership")
    do_not_use_unsupported_jd_terms: bool = Field(default=True, alias="doNotUseUnsupportedJdTerms")
    start_with_action_verb: bool = Field(default=True, alias="startWithActionVerb")
    avoid_first_person: bool = Field(default=True, alias="avoidFirstPerson")
    avoid_duplicate_openings: bool = Field(default=True, alias="avoidDuplicateOpenings")
    avoid_generic_filler: bool = Field(default=True, alias="avoidGenericFiller")

    model_config = ConfigDict(populate_by_name=True)


class ExperiencePromptValidationResult(BaseModel):
    is_valid: bool = Field(alias="isValid")
    codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class ExperiencePromptInput(BaseModel):
    experience_id: str = Field(alias="experienceId")
    role_context: ExperiencePromptRoleContext = Field(alias="roleContext")
    target_context: ExperiencePromptTargetContext = Field(alias="targetContext")
    approved_evidence: list[ExperiencePromptEvidence] = Field(default_factory=list, alias="approvedEvidence")
    approved_technologies: list[ExperiencePromptTechnology] = Field(default_factory=list, alias="approvedTechnologies")
    approved_capabilities: list[ExperiencePromptCapability] = Field(default_factory=list, alias="approvedCapabilities")
    approved_metrics: list[ExperiencePromptMetric] = Field(default_factory=list, alias="approvedMetrics")
    linked_projects: list[ExperiencePromptProject] = Field(default_factory=list, alias="linkedProjects")
    bullet_themes: list[str] = Field(default_factory=list, alias="bulletThemes")
    supported_requirement_ids: list[str] = Field(default_factory=list, alias="supportedRequirementIds")
    excluded_terms: list[str] = Field(default_factory=list, alias="excludedTerms")
    writing_rules: ExperienceWritingRules = Field(alias="writingRules")
    planner_version: str = Field(alias="plannerVersion")
    prompt_version: str = Field(alias="promptVersion")
    validation_result: ExperiencePromptValidationResult = Field(alias="validationResult")

    model_config = ConfigDict(populate_by_name=True)


class ExperienceBulletModelItem(BaseModel):
    generated_text: str = Field(alias="generatedText")
    supporting_evidence_ids: list[str] = Field(default_factory=list, alias="supportingEvidenceIds")
    supported_requirement_ids: list[str] = Field(default_factory=list, alias="supportedRequirementIds")

    model_config = ConfigDict(populate_by_name=True)


class ExperienceBulletModelResponse(BaseModel):
    experience_id: str = Field(alias="experienceId")
    bullets: list[ExperienceBulletModelItem] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class ExperienceBulletValidationIssue(BaseModel):
    code: str
    message: str = ""
    bullet_index: int | None = Field(default=None, alias="bulletIndex")
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")

    model_config = ConfigDict(populate_by_name=True)


class ExperienceBulletValidationResult(BaseModel):
    is_valid: bool = Field(alias="isValid")
    issues: list[ExperienceBulletValidationIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class ExperienceGeneratedBullet(BaseModel):
    bullet_id: str = Field(alias="bulletId")
    order: int
    generated_text: str = Field(alias="generatedText")
    current_text: str = Field(alias="currentText")
    user_edited: bool = Field(default=False, alias="userEdited")
    supporting_evidence_ids: list[str] = Field(default_factory=list, alias="supportingEvidenceIds")
    supported_requirement_ids: list[str] = Field(default_factory=list, alias="supportedRequirementIds")
    validation_status: str = Field(default="validated", alias="validationStatus")
    warnings: list[str] = Field(default_factory=list)
    generation_method: str = Field(default="openai", alias="generationMethod")
    model: str = ""
    prompt_version: str = Field(default="", alias="promptVersion")

    model_config = ConfigDict(populate_by_name=True)


class ExperienceBulletGenerationResult(BaseModel):
    experience_id: str = Field(alias="experienceId")
    bullets: list[ExperienceGeneratedBullet] = Field(default_factory=list)
    generation_method: str = Field(default="openai", alias="generationMethod")
    model: str = ""
    prompt_version: str = Field(alias="promptVersion")
    validation_result: ExperienceBulletValidationResult = Field(alias="validationResult")
    retry_count: int = Field(default=0, alias="retryCount")
    cache_hit: bool = Field(default=False, alias="cacheHit")

    model_config = ConfigDict(populate_by_name=True)


class ExperienceRoleIntelligence(BaseModel):
    experience_id: str = Field(alias="experienceId")
    bullets: list[ExperienceGeneratedBullet] = Field(default_factory=list)
    generation_mode: str = Field(default="openai", alias="generationMode")
    model: str = ""
    prompt_version: str = Field(alias="promptVersion")
    validation_status: str = Field(default="valid", alias="validationStatus")
    warnings: list[str] = Field(default_factory=list)
    model_configuration_hash: str = Field(default="", alias="modelConfigurationHash")

    model_config = ConfigDict(populate_by_name=True)


class ExperienceIntelligencePlan(BaseModel):
    planner_version: str = Field(alias="plannerVersion")
    role_family: str = Field(default="", alias="roleFamily")
    roles: list[ExperienceRolePlan] = Field(default_factory=list)
    experience_prompt_inputs: list[ExperiencePromptInput] = Field(default_factory=list, alias="experiencePromptInputs")
    role_intelligence: list[ExperienceRoleIntelligence] = Field(default_factory=list, alias="roleIntelligence")
    writer_prompt_version: str = Field(default="", alias="writerPromptVersion")
    writer_model: str = Field(default="", alias="writerModel")
    model_configuration_hash: str = Field(default="", alias="modelConfigurationHash")
    overall_validation_status: str = Field(default="", alias="overallValidationStatus")
    created_at: str = Field(default="", alias="createdAt")
    warnings: list[str] = Field(default_factory=list)
    validation_status: str = Field(default="valid", alias="validationStatus")

    @field_validator("planner_version")
    @classmethod
    def required_planner_version(cls, value: str) -> str:
        value = _trimmed(value)
        if not value:
            raise ValueError("Experience Intelligence requires a planner version.")
        return value

    model_config = ConfigDict(populate_by_name=True)


class ResumeIntelligencePackageSchema(BaseModel):
    package_id: str = Field(alias="packageId")
    profile_id: str = Field(alias="profileId")
    profile_version: int = Field(alias="profileVersion")
    job_description_hash: str = Field(alias="jobDescriptionHash")
    target_role: str = Field(alias="targetRole")
    target_company: str = Field(default="", alias="targetCompany")
    level: str = ""
    job_intelligence: dict = Field(default_factory=dict, alias="jobIntelligence")
    normalized_requirements: dict = Field(default_factory=dict, alias="normalizedRequirements")
    profile_match: dict = Field(default_factory=dict, alias="profileMatch")
    summary_intelligence: SummaryIntelligence | None = Field(default=None, alias="summaryIntelligence")
    experience_intelligence: ExperienceIntelligencePlan | None = Field(default=None, alias="experienceIntelligence")
    validation_status: str = Field(default="valid", alias="validationStatus")
    validation_warnings: list[str] = Field(default_factory=list, alias="validationWarnings")
    created_at: str = Field(default="", alias="createdAt")
    updated_at: str = Field(default="", alias="updatedAt")

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


class TypedRequirementLevel(str, Enum):
    required = "required"
    preferred = "preferred"
    responsibility = "responsibility"
    inferred = "inferred"


class TypedRequirementPriority(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class TypedJobRequirement(BaseModel):
    requirement_id: str = Field(alias="requirementId")
    canonical_term: str = Field(alias="canonicalTerm")
    original_terms: list[str] = Field(default_factory=list, alias="originalTerms")
    category: str
    requirement_level: TypedRequirementLevel = Field(alias="requirementLevel")
    priority: TypedRequirementPriority
    explicit: bool = True
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    evidence_text: str = Field(default="", alias="evidenceText")
    source_sentence: str = Field(default="", alias="sourceSentence")
    reason: str = ""

    model_config = ConfigDict(populate_by_name=True)


class NormalizedRequirements(BaseModel):
    technical_requirements: list[TypedJobRequirement] = Field(default_factory=list, alias="technicalRequirements")
    responsibility_requirements: list[TypedJobRequirement] = Field(default_factory=list, alias="responsibilityRequirements")
    experience_requirements: list[TypedJobRequirement] = Field(default_factory=list, alias="experienceRequirements")
    education_requirements: list[TypedJobRequirement] = Field(default_factory=list, alias="educationRequirements")
    certification_requirements: list[TypedJobRequirement] = Field(default_factory=list, alias="certificationRequirements")
    leadership_requirements: list[TypedJobRequirement] = Field(default_factory=list, alias="leadershipRequirements")
    soft_skill_requirements: list[TypedJobRequirement] = Field(default_factory=list, alias="softSkillRequirements")
    domain_requirements: list[TypedJobRequirement] = Field(default_factory=list, alias="domainRequirements")
    inferred_requirements: list[TypedJobRequirement] = Field(default_factory=list, alias="inferredRequirements")

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
    technical_requirements: list[TypedJobRequirement] = Field(default_factory=list, alias="technicalRequirements")
    responsibility_requirements: list[TypedJobRequirement] = Field(default_factory=list, alias="responsibilityRequirements")
    experience_requirements: list[TypedJobRequirement] = Field(default_factory=list, alias="experienceRequirements")
    education_requirements: list[TypedJobRequirement] = Field(default_factory=list, alias="educationRequirements")
    certification_requirements: list[TypedJobRequirement] = Field(default_factory=list, alias="certificationRequirements")
    leadership_requirements_typed: list[TypedJobRequirement] = Field(default_factory=list, alias="leadershipRequirements")
    soft_skill_requirements: list[TypedJobRequirement] = Field(default_factory=list, alias="softSkillRequirements")
    domain_requirements: list[TypedJobRequirement] = Field(default_factory=list, alias="domainRequirements")
    inferred_requirements_typed: list[TypedJobRequirement] = Field(default_factory=list, alias="inferredRequirements")
    excluded_noise_terms: list[str] = Field(default_factory=list, alias="excludedNoiseTerms")
    analysis_warnings: list[str] = Field(default_factory=list, alias="analysisWarnings")
    normalized_requirements: NormalizedRequirements = Field(default_factory=NormalizedRequirements, alias="normalizedRequirements")
    # Deprecated compatibility field. Derived from eligible typed requirements only.
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
