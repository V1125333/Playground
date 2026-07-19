from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from app.schemas.resume import (
    CandidateProfile,
    GenerateResumeRequest,
    ProfileEvidenceItem,
    ProfileEvidenceType,
    ProfileMatchSummary,
    RequirementMatch,
)
from app.services.ai_usage import recent_job_id


SUMMARY_PLANNER_VERSION = "summary-planner-v1"
SUMMARY_MAX_WORDS = 80
SUMMARY_MIN_SENTENCES = 2
SUMMARY_MAX_SENTENCES = 3


class SummaryValidationCode(str, Enum):
    metadata_leakage = "METADATA_LEAKAGE"
    raw_company_name_in_capability = "RAW_COMPANY_NAME_IN_CAPABILITY"
    raw_client_name_in_capability = "RAW_CLIENT_NAME_IN_CAPABILITY"
    location_leakage = "LOCATION_LEAKAGE"
    invalid_experience_display = "INVALID_EXPERIENCE_DISPLAY"
    overloaded_technology_list = "OVERLOADED_TECHNOLOGY_LIST"
    generic_repetitive_language = "GENERIC_REPETITIVE_LANGUAGE"
    unsupported_reputation_claim = "UNSUPPORTED_REPUTATION_CLAIM"
    unsupported_technology_claim = "UNSUPPORTED_TECHNOLOGY_CLAIM"
    unsupported_capability_claim = "UNSUPPORTED_CAPABILITY_CLAIM"
    invented_metric = "INVENTED_METRIC"
    internal_terminology = "INTERNAL_TERMINOLOGY"
    invalid_evidence_id = "INVALID_EVIDENCE_ID"
    missing_identity = "MISSING_IDENTITY"
    invalid_length = "INVALID_LENGTH"
    insufficient_jd_adaptation = "INSUFFICIENT_JD_ADAPTATION"
    reused_generic_summary = "REUSED_GENERIC_SUMMARY"
    missing_target_role_theme = "MISSING_TARGET_ROLE_THEME"
    low_signal_variation = "LOW_SIGNAL_VARIATION"
    generic_capabilities_dominate = "GENERIC_CAPABILITIES_DOMINATE"
    identical_technology_selection = "IDENTICAL_TECHNOLOGY_SELECTION"


class SummaryEvidenceClass(str, Enum):
    responsibility = "responsibility"
    achievement = "achievement"
    capability = "capability"
    technology = "technology"
    project_capability = "project_capability"
    verified_domain = "verified_domain"
    collaboration_delivery_capability = "collaboration_delivery_capability"
    company_name = "company_name"
    client_name = "client_name"
    location = "location"
    date = "date"
    contact_data = "contact_data"
    education = "education"
    certification_title = "certification_title"
    role_heading_metadata = "role_heading_metadata"
    excluded_metadata = "excluded_metadata"

INTERNAL_TERMS = {
    "grounded in",
    "evidence-backed",
    "resume claims",
    "ats",
    "profile match",
    "summary planner",
    "planner",
    "evidence id",
    "target role",
    "jd",
    "job analysis",
}

LEADERSHIP_TERMS = {
    "leadership",
    "mentoring",
    "mentor",
    "led",
    "lead",
    "technical ownership",
    "owned",
    "ownership",
    "code reviews",
    "reviewed",
}

ARCHITECTURE_TERMS = {
    "architecture",
    "architectural",
    "solution design",
    "system design",
    "scalable",
    "enterprise application design",
}

TECH_CATEGORY_HINTS = {
    "c#",
    ".net",
    ".net framework",
    "asp.net core",
    "asp.net mvc",
    "sql server",
    "microsoft sql server",
    "t-sql",
    "rest api",
    "restful api",
    "web api",
    "azure",
    "aws",
    "java",
    "javascript",
    "typescript",
    "python",
    "fastapi",
    "rag",
    "langchain",
    "azure data factory",
    "adf",
    "databricks",
    "spark",
    "apache spark",
    "react",
    "angular",
    "next.js",
    "docker",
    "kubernetes",
    "spring boot",
}

DOMAIN_HINTS = {
    "healthcare",
    "provider",
    "claims",
    "authorization",
    "financial services",
    "banking",
    "trading",
    "insurance",
    "government",
    "education",
    "retail",
}

KNOWN_DOMAIN_MAPPINGS = {
    "molina healthcare": "healthcare",
    "molina health care": "healthcare",
    "healthcare": "healthcare",
    "health care": "healthcare",
    "provider": "healthcare",
    "claims": "healthcare",
    "authorization": "healthcare",
    "western union": "financial services",
    "financial services": "financial services",
    "banking": "financial services",
    "trading": "financial services",
    "insurance": "insurance",
}

SUMMARY_TECH_ALIASES = [
    ("asp.net core", "ASP.NET Core"),
    ("asp.net mvc", "ASP.NET MVC"),
    ("azure data factory", "Azure Data Factory"),
    ("adf", "Azure Data Factory"),
    ("microsoft sql server", "SQL Server"),
    ("sql server", "SQL Server"),
    ("t-sql", "SQL Server"),
    ("azure", "Azure"),
    ("c#", "C#"),
    (".net framework", ".NET Framework"),
    ("restful api", "REST APIs"),
    ("rest api", "REST APIs"),
    ("web api", "Web API"),
    ("javascript", "JavaScript"),
    ("typescript", "TypeScript"),
    ("python", "Python"),
    ("fastapi", "FastAPI"),
    ("langchain", "LangChain"),
    ("rag", "RAG"),
    ("databricks", "Databricks"),
    ("apache spark", "Apache Spark"),
    ("spark", "Apache Spark"),
    ("react", "React"),
    ("angular", "Angular"),
    ("next.js", "Next.js"),
    ("docker", "Docker"),
    ("kubernetes", "Kubernetes"),
    ("aws", "AWS"),
    ("java", "Java"),
    ("spring boot", "Spring Boot"),
]

SUMMARY_TECH_PRIORITY = [
    "C#",
    "ASP.NET Core",
    "ASP.NET MVC",
    "SQL Server",
    "REST APIs",
    ".NET Framework",
    "Azure",
    "JavaScript",
    "TypeScript",
    "React",
    "Angular",
    "Python",
    "Azure Data Factory",
    "Databricks",
    "Apache Spark",
    "FastAPI",
    "RAG",
    "LangChain",
    "Docker",
    "Kubernetes",
]

GENERIC_SUMMARY_CAPABILITIES = {
    "requirements analysis",
    "technical documentation",
    "Agile delivery",
    "cross-functional collaboration",
    "debugging and problem solving",
    "maintainable implementation",
}


class SummarySignal(BaseModel):
    value: str
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")
    source: str = ""

    @field_validator("value")
    @classmethod
    def clean_value(cls, value: str) -> str:
        return clean_text(value)

    @field_validator("evidence_ids")
    @classmethod
    def require_evidence(cls, value: list[str]) -> list[str]:
        output = [item.strip() for item in value if item.strip()]
        if not output:
            raise ValueError("Summary signals require supporting evidence IDs.")
        return output

    model_config = {"populate_by_name": True}


class SummaryTechnologySignal(SummarySignal):
    scope: str = "profile"


class SummaryJdPriority(BaseModel):
    requirement_id: str = Field(alias="requirementId")
    value: str
    category: str = ""
    priority: str = ""
    priority_score: int = Field(default=0, alias="priorityScore")
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")

    model_config = {"populate_by_name": True}


class SummaryCandidateIdentity(BaseModel):
    full_name: str = Field(alias="fullName")
    current_title: str = Field(alias="currentTitle")
    years_of_experience: float = Field(default=0, alias="yearsOfExperience")
    years_of_experience_display: str = Field(default="", alias="yearsOfExperienceDisplay")
    primary_positioning: str = Field(default="", alias="primaryPositioning")

    model_config = {"populate_by_name": True}


class SummarySignalScore(BaseModel):
    value: str
    signal_type: str = Field(alias="signalType")
    score: float
    factors: dict[str, float] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")
    selected: bool = False
    reason: str = ""

    model_config = {"populate_by_name": True}


class SummaryTargetEmphasis(BaseModel):
    role_family: str = Field(default="Full Stack Development", alias="roleFamily")
    top_supported_technologies: list[str] = Field(default_factory=list, alias="topSupportedTechnologies")
    top_supported_capabilities: list[str] = Field(default_factory=list, alias="topSupportedCapabilities")
    target_work_themes: list[str] = Field(default_factory=list, alias="targetWorkThemes")
    relevant_domains: list[str] = Field(default_factory=list, alias="relevantDomains")
    excluded_unsupported_signals: list[str] = Field(default_factory=list, alias="excludedUnsupportedSignals")

    model_config = {"populate_by_name": True}


class SummaryPlannerDiagnostics(BaseModel):
    considered_signals: list[SummarySignalScore] = Field(default_factory=list, alias="consideredSignals")
    selected_signals: list[SummarySignalScore] = Field(default_factory=list, alias="selectedSignals")
    rejected_signals: list[SummarySignalScore] = Field(default_factory=list, alias="rejectedSignals")
    role_family: str = Field(default="Full Stack Development", alias="roleFamily")
    variation_score: float = Field(default=0, alias="variationScore")
    selection_reasons: list[str] = Field(default_factory=list, alias="selectionReasons")

    model_config = {"populate_by_name": True}


class SummaryPlanner(BaseModel):
    planner_version: str = Field(default=SUMMARY_PLANNER_VERSION, alias="plannerVersion")
    candidate_identity: SummaryCandidateIdentity = Field(alias="candidateIdentity")
    profile_level_technologies: list[SummaryTechnologySignal] = Field(default_factory=list, alias="profileLevelTechnologies")
    experience_level_technologies: list[SummaryTechnologySignal] = Field(default_factory=list, alias="experienceLevelTechnologies")
    project_level_technologies: list[SummaryTechnologySignal] = Field(default_factory=list, alias="projectLevelTechnologies")
    verified_capabilities: list[SummarySignal] = Field(default_factory=list, alias="verifiedCapabilities")
    verified_domains: list[SummarySignal] = Field(default_factory=list, alias="verifiedDomains")
    supported_jd_priorities: list[SummaryJdPriority] = Field(default_factory=list, alias="supportedJdPriorities")
    unsupported_jd_only_technologies: list[str] = Field(default_factory=list, alias="unsupportedJdOnlyTechnologies")
    excluded_metadata_terms: list[str] = Field(default_factory=list, alias="excludedMetadataTerms")
    excluded_company_terms: list[str] = Field(default_factory=list, alias="excludedCompanyTerms")
    excluded_client_terms: list[str] = Field(default_factory=list, alias="excludedClientTerms")
    excluded_location_terms: list[str] = Field(default_factory=list, alias="excludedLocationTerms")
    allowed_metrics: list[SummarySignal] = Field(default_factory=list, alias="allowedMetrics")
    target_emphasis: SummaryTargetEmphasis = Field(default_factory=SummaryTargetEmphasis, alias="targetEmphasis")
    debug_diagnostics: SummaryPlannerDiagnostics = Field(default_factory=SummaryPlannerDiagnostics, alias="debugDiagnostics")
    constraints: dict[str, object] = Field(default_factory=dict)

    @property
    def evidence_ids(self) -> set[str]:
        output: set[str] = set()
        for collection in (
            self.profile_level_technologies,
            self.experience_level_technologies,
            self.project_level_technologies,
            self.verified_capabilities,
            self.verified_domains,
            self.allowed_metrics,
        ):
            for signal in collection:
                output.update(signal.evidence_ids)
        for priority in self.supported_jd_priorities:
            output.update(priority.evidence_ids)
        return output

    @property
    def supported_technology_values(self) -> set[str]:
        return {
            signal.value
            for collection in (self.profile_level_technologies, self.experience_level_technologies, self.project_level_technologies)
            for signal in collection
        }

    model_config = {"populate_by_name": True}


class SummaryGenerationResult(BaseModel):
    summary: str
    used_evidence_ids: list[str] = Field(default_factory=list, alias="usedEvidenceIds")
    used_signals: list[str] = Field(default_factory=list, alias="usedSignals")
    excluded_signals: list[str] = Field(default_factory=list, alias="excludedSignals")
    risk_flags: list[str] = Field(default_factory=list, alias="riskFlags")
    generation_method: str = Field(default="deterministic", alias="generationMethod")

    @field_validator("summary")
    @classmethod
    def clean_summary(cls, value: str) -> str:
        return clean_text(value)

    model_config = {"populate_by_name": True}


class SummaryValidationResult(BaseModel):
    is_valid: bool = Field(alias="isValid")
    errors: list[str] = Field(default_factory=list)
    validation_codes: list[SummaryValidationCode] = Field(default_factory=list, alias="validationCodes")
    warnings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


@dataclass(frozen=True)
class SummaryBuildResult:
    planner: SummaryPlanner
    generation: SummaryGenerationResult
    validation: SummaryValidationResult


def build_summary_planner(
    profile: CandidateProfile,
    payload: GenerateResumeRequest,
    profile_match: ProfileMatchSummary,
    evidence_index: list[ProfileEvidenceItem],
    years_of_experience: float,
) -> SummaryPlanner:
    evidence_by_id = {item.evidence_id: item for item in evidence_index}
    matched = [match for match in profile_match.matched_requirements if match.is_safe_to_use]
    supported_requirement_evidence = {
        evidence.evidence_id
        for match in matched
        for evidence in match.evidence
        if evidence.evidence_id in evidence_by_id
    }
    focus = payload_focus_text(payload)
    profile_tech, experience_tech, project_tech = technology_signals(evidence_index, supported_requirement_evidence)
    profile_tech = dedupe_signals([*profile_tech, *supplemental_technology_signals(evidence_index, profile.title, focus)])
    capabilities = capability_signals(evidence_index, supported_requirement_evidence)
    capabilities = dedupe_signals([*capabilities, *supplemental_capability_signals(evidence_index, focus)])
    domains = domain_signals(evidence_index, supported_requirement_evidence)
    metrics = metric_signals(evidence_index, supported_requirement_evidence)
    priorities = supported_jd_priorities(matched)
    unsupported = unsupported_jd_technologies(profile_match)
    excluded_metadata, excluded_companies, excluded_clients, excluded_locations = metadata_exclusion_terms(evidence_index)

    planner = SummaryPlanner(
        candidateIdentity=SummaryCandidateIdentity(
            fullName=profile.name,
            currentTitle=profile.title or payload.target_role,
            yearsOfExperience=years_of_experience,
            yearsOfExperienceDisplay=experience_display_value(years_of_experience),
            primaryPositioning=profile.title or "Software engineer",
        ),
        profileLevelTechnologies=profile_tech,
        experienceLevelTechnologies=experience_tech,
        projectLevelTechnologies=project_tech,
        verifiedCapabilities=capabilities,
        verifiedDomains=domains,
        supportedJdPriorities=priorities,
        unsupportedJdOnlyTechnologies=unsupported,
        excludedMetadataTerms=excluded_metadata,
        excludedCompanyTerms=excluded_companies,
        excludedClientTerms=excluded_clients,
        excludedLocationTerms=excluded_locations,
        allowedMetrics=metrics,
        constraints={
            "sentenceCount": "2-3",
            "maxWords": SUMMARY_MAX_WORDS,
            "preserveCandidateIdentity": True,
            "forbiddenTerms": sorted(INTERNAL_TERMS),
            "doNotMention": [
                "education unless required as the candidate identity",
                "unsupported JD-only technologies",
                "internal matching terminology",
            ],
            "jobFocusText": focus,
        },
    )
    return apply_target_emphasis(planner)


async def build_validated_summary(
    planner: SummaryPlanner,
    *,
    ai_service: object | None = None,
    job_id: str = "",
    use_ai: bool | None = None,
    max_retries: int = 1,
) -> SummaryBuildResult:
    del ai_service, job_id, use_ai, max_retries

    fallback = deterministic_summary(planner)
    validation = validate_summary_result(fallback, planner)
    if not validation.is_valid:
        repaired = repair_summary_result(fallback, planner, validation)
        repaired_validation = validate_summary_result(repaired, planner)
        return SummaryBuildResult(planner, repaired, repaired_validation)
    return SummaryBuildResult(planner, fallback, validation)


def apply_target_emphasis(planner: SummaryPlanner) -> SummaryPlanner:
    focus = jd_focus_text(planner)
    role_family = classify_role_family(focus)
    technology_scores = score_technology_signals(planner, role_family, focus)
    capability_scores = score_capability_signals(planner, role_family, focus)
    selected_technologies = select_technologies_for_role(technology_scores, role_family, limit=4)
    selected_capabilities = select_capabilities_for_role(capability_scores, role_family, limit=4)
    domains = prioritize_terms([item.value for item in planner.verified_domains if domain_relevant_to_focus(item.value, focus)], limit=2)
    themes = role_family_work_themes(role_family, selected_capabilities, focus)
    emphasis = SummaryTargetEmphasis(
        roleFamily=role_family,
        topSupportedTechnologies=selected_technologies,
        topSupportedCapabilities=selected_capabilities,
        targetWorkThemes=themes,
        relevantDomains=domains,
        excludedUnsupportedSignals=planner.unsupported_jd_only_technologies,
    )
    selected = [score.model_copy(update={"selected": True}) for score in [*technology_scores, *capability_scores] if score.value in {*selected_technologies, *selected_capabilities}]
    rejected = [score for score in [*technology_scores, *capability_scores] if score.value not in {*selected_technologies, *selected_capabilities}]
    diagnostics = SummaryPlannerDiagnostics(
        consideredSignals=[*technology_scores, *capability_scores],
        selectedSignals=selected,
        rejectedSignals=rejected[:20],
        roleFamily=role_family,
        variationScore=target_emphasis_variation_score(emphasis),
        selectionReasons=[score.reason for score in selected],
    )
    constraints = {
        **planner.constraints,
        "rankingWeights": {
            "jdRelevance": 0.40,
            "evidenceStrength": 0.30,
            "candidateIdentityRelevance": 0.15,
            "recency": 0.10,
            "frequency": 0.05,
        },
        "baselineTechnologySet": baseline_technology_set(planner),
    }
    return planner.model_copy(update={"target_emphasis": emphasis, "debug_diagnostics": diagnostics, "constraints": constraints})


def deterministic_summary(planner: SummaryPlanner) -> SummaryGenerationResult:
    identity = planner.candidate_identity
    emphasis = planner.target_emphasis
    primary_tech = emphasis.top_supported_technologies[:4]
    capability_terms = emphasis.top_supported_capabilities[:4]
    domain_terms = emphasis.relevant_domains[:2]
    work_theme = emphasis.target_work_themes[0] if emphasis.target_work_themes else "enterprise application delivery"
    first = (
        f"{identity.current_title or 'Software engineer'} with {identity.years_of_experience_display or experience_display_value(identity.years_of_experience)} of experience "
        f"working in {work_theme}"
    )
    if primary_tech:
        first += f" using {human_join(primary_tech)}"
    first += "."

    second_parts = capability_terms[:4] or role_family_default_capabilities(emphasis.role_family)
    second = f"Experienced in {human_join(second_parts)} for role-specific delivery."
    if domain_terms:
        second = f"Experienced in {human_join(second_parts)} for {human_join(domain_terms)} environments."

    third = closing_value_statement(emphasis.role_family, capability_terms)
    summary = clean_text(" ".join([first, second, third]))

    used = planner_evidence_for_terms(planner, [*primary_tech, *capability_terms, *domain_terms])
    return SummaryGenerationResult(
        summary=summary,
        usedEvidenceIds=used,
        usedSignals=dedupe_text([*primary_tech, *capability_terms, *domain_terms]),
        excludedSignals=planner.unsupported_jd_only_technologies,
        riskFlags=[],
        generationMethod="deterministic",
    )


def validate_summary_result(result: SummaryGenerationResult, planner: SummaryPlanner) -> SummaryValidationResult:
    errors: list[str] = []
    codes: list[SummaryValidationCode] = []
    warnings: list[str] = []
    summary = clean_text(result.summary)
    lowered = summary.casefold()
    allowed_evidence = planner.evidence_ids
    allowed_tech = {normalize_text(value) for value in planner.supported_technology_values}
    allowed_tech.update(normalize_text(canonical_summary_technology(value)) for value in planner.supported_technology_values)
    unsupported_tech = {normalize_text(value) for value in planner.unsupported_jd_only_technologies}
    allowed_capabilities = {normalize_text(signal.value) for signal in planner.verified_capabilities}

    def add_error(code: SummaryValidationCode, message: str) -> None:
        errors.append(message)
        codes.append(code)

    if not summary:
        add_error(SummaryValidationCode.invalid_length, "Summary is empty.")
    sentence_count = count_sentences(summary)
    if sentence_count < SUMMARY_MIN_SENTENCES or sentence_count > SUMMARY_MAX_SENTENCES:
        add_error(SummaryValidationCode.invalid_length, "Summary must be 2-3 sentences.")
    if word_count(summary) > SUMMARY_MAX_WORDS:
        add_error(SummaryValidationCode.invalid_length, f"Summary exceeds {SUMMARY_MAX_WORDS} words.")
    if normalize_text(planner.candidate_identity.current_title) not in normalize_text(summary):
        add_error(SummaryValidationCode.missing_identity, "Summary is missing the candidate's professional identity.")
    if re.search(r"\b\d+\.\d+\+\s+years?\b", lowered):
        add_error(SummaryValidationCode.invalid_experience_display, "Summary uses an unprofessional decimal experience display.")
    if "known for" in lowered and not any(leadership_or_collaboration_term(value) for value in allowed_capabilities):
        add_error(SummaryValidationCode.unsupported_reputation_claim, "Summary uses an unsupported reputation claim.")
    for term in INTERNAL_TERMS:
        if term in lowered:
            add_error(SummaryValidationCode.internal_terminology, f"Summary contains internal/system terminology: {term}.")
    for tech in unsupported_tech:
        if tech and phrase_present(lowered, tech) and tech not in allowed_tech:
            add_error(SummaryValidationCode.unsupported_technology_claim, f"Summary claims unsupported technology: {tech}.")
    for term in planner.excluded_company_terms:
        if phrase_present(summary, term):
            add_error(SummaryValidationCode.raw_company_name_in_capability, f"Summary contains excluded company name: {term}.")
    for term in planner.excluded_client_terms:
        if phrase_present(summary, term):
            add_error(SummaryValidationCode.raw_client_name_in_capability, f"Summary contains excluded client name: {term}.")
    for term in planner.excluded_location_terms:
        if phrase_present(summary, term):
            add_error(SummaryValidationCode.location_leakage, f"Summary contains excluded location: {term}.")
    for term in planner.excluded_metadata_terms:
        if phrase_present(summary, term):
            add_error(SummaryValidationCode.metadata_leakage, f"Summary contains excluded metadata term: {term}.")
    if mentions_leadership(summary) and not any(leadership_or_collaboration_term(value) for value in allowed_capabilities):
        add_error(SummaryValidationCode.unsupported_capability_claim, "Summary claims unsupported leadership or ownership capability.")
    if mentions_architecture(summary) and not any(architecture_term(value) for value in allowed_capabilities):
        add_error(SummaryValidationCode.unsupported_capability_claim, "Summary claims unsupported architecture/design capability.")
    if contains_invented_metric(summary, planner):
        add_error(SummaryValidationCode.invented_metric, "Summary appears to contain an unsupported metric.")
    if looks_like_keyword_list(summary):
        add_error(SummaryValidationCode.overloaded_technology_list, "Summary reads like a keyword list.")
    if re.search(r"\bmicrosoft azure\s*\(", lowered) or "microsoft sql server" in lowered:
        add_error(SummaryValidationCode.overloaded_technology_list, "Summary contains overloaded or non-canonical technology names.")
    if has_generic_repetitive_language(summary):
        add_error(SummaryValidationCode.generic_repetitive_language, "Summary contains generic or repetitive language.")
    repeated = repeated_phrases(summary)
    if repeated:
        add_error(SummaryValidationCode.generic_repetitive_language, f"Summary repeats phrases: {', '.join(repeated[:3])}.")
    selected_signals = dedupe_text(
        [
            *planner.target_emphasis.top_supported_technologies,
            *planner.target_emphasis.top_supported_capabilities,
            *planner.target_emphasis.relevant_domains,
        ]
    )
    visible_selected = [signal for signal in selected_signals if phrase_present(summary, signal)]
    if len(visible_selected) < min(2, len(selected_signals)):
        add_error(SummaryValidationCode.insufficient_jd_adaptation, "Summary does not include enough JD-specific supported signals.")
    if planner.target_emphasis.target_work_themes and not any(theme_present(summary, theme) for theme in planner.target_emphasis.target_work_themes):
        add_error(SummaryValidationCode.missing_target_role_theme, "Summary is missing the target-role work theme.")
    selected_capabilities = planner.target_emphasis.top_supported_capabilities
    if selected_capabilities:
        generic_count = sum(1 for value in selected_capabilities if normalize_text(value) in {normalize_text(item) for item in GENERIC_SUMMARY_CAPABILITIES})
        if generic_count >= max(2, len(selected_capabilities) - 1):
            add_error(SummaryValidationCode.generic_capabilities_dominate, "Generic capabilities dominate the summary target emphasis.")
    if is_reused_generic_summary(summary):
        add_error(SummaryValidationCode.reused_generic_summary, "Summary uses reusable generic wording instead of target-specific positioning.")
    if planner.debug_diagnostics.variation_score < 0.35 and planner.target_emphasis.role_family not in {".NET Application Development"}:
        add_error(SummaryValidationCode.low_signal_variation, "Summary target emphasis has low variation for this role family.")
    baseline_tech = {normalize_text(value) for value in planner.constraints.get("baselineTechnologySet", []) if isinstance(value, str)}
    selected_tech = {normalize_text(value) for value in planner.target_emphasis.top_supported_technologies}
    if (
        selected_tech
        and selected_tech == baseline_tech
        and planner.target_emphasis.role_family in {"Data Engineering", "AI / Generative AI Engineering"}
    ):
        add_error(SummaryValidationCode.identical_technology_selection, "Technology selection did not change for a distinct role family.")
    invalid_ids = [item for item in result.used_evidence_ids if item not in allowed_evidence]
    if invalid_ids:
        add_error(SummaryValidationCode.invalid_evidence_id, f"Summary used evidence IDs not present in planner: {', '.join(invalid_ids[:5])}.")
    if not result.used_evidence_ids and any([planner.profile_level_technologies, planner.experience_level_technologies, planner.verified_capabilities]):
        warnings.append("Summary did not declare used evidence IDs.")

    return SummaryValidationResult(isValid=not errors, errors=errors, validationCodes=dedupe_codes(codes), warnings=warnings)


def repair_summary_result(
    result: SummaryGenerationResult,
    planner: SummaryPlanner,
    validation: SummaryValidationResult,
) -> SummaryGenerationResult:
    fallback = deterministic_summary(planner)
    fallback.risk_flags = dedupe_text([*result.risk_flags, *validation.errors, "deterministic fallback used"])
    return fallback


def technology_signals(
    evidence_index: list[ProfileEvidenceItem],
    supported_ids: set[str],
) -> tuple[list[SummaryTechnologySignal], list[SummaryTechnologySignal], list[SummaryTechnologySignal]]:
    profile_level: list[SummaryTechnologySignal] = []
    experience_level: list[SummaryTechnologySignal] = []
    project_level: list[SummaryTechnologySignal] = []
    for evidence in evidence_index:
        if evidence.evidence_id not in supported_ids:
            continue
        if evidence.evidence_type == ProfileEvidenceType.skill and looks_like_technology(evidence.original_text):
            value = canonical_summary_technology(evidence.original_text)
            signal = SummaryTechnologySignal(
                value=value,
                evidenceIds=[evidence.evidence_id],
                source=evidence.source_label,
                scope="experience" if evidence.source_record_id else "profile",
            )
            if evidence.source_record_id and evidence.source_record_id.startswith("experience-"):
                experience_level.append(signal)
            else:
                profile_level.append(signal)
        elif evidence.evidence_type == ProfileEvidenceType.project:
            for tech in extract_known_technologies(evidence.original_text):
                project_level.append(
                    SummaryTechnologySignal(
                        value=tech,
                        evidenceIds=[evidence.evidence_id],
                        source=evidence.source_label,
                        scope="project",
                    )
                )
    return dedupe_signals(profile_level), dedupe_signals(experience_level), dedupe_signals(project_level)


def capability_signals(evidence_index: list[ProfileEvidenceItem], supported_ids: set[str]) -> list[SummarySignal]:
    signals: list[SummarySignal] = []
    for evidence in evidence_index:
        if evidence.evidence_id not in supported_ids:
            continue
        if not is_summary_content_evidence(evidence):
            continue
        if evidence.evidence_type not in {ProfileEvidenceType.work_experience, ProfileEvidenceType.achievement, ProfileEvidenceType.project}:
            continue
        value = capability_from_text(evidence.original_text)
        if value:
            signals.append(SummarySignal(value=value, evidenceIds=[evidence.evidence_id], source=evidence.source_label))
    return dedupe_signals(signals)


def supplemental_technology_signals(evidence_index: list[ProfileEvidenceItem], identity_title: str, focus: str) -> list[SummaryTechnologySignal]:
    signals: list[SummaryTechnologySignal] = []
    for evidence in evidence_index:
        if evidence.evidence_type != ProfileEvidenceType.skill or not looks_like_technology(evidence.original_text):
            continue
        value = canonical_summary_technology(evidence.original_text)
        if technology_relevance_score(value, focus, normalize_text(identity_title)) <= 0:
            continue
        signals.append(
            SummaryTechnologySignal(
                value=value,
                evidenceIds=[evidence.evidence_id],
                source=evidence.source_label,
                scope="experience" if evidence.source_record_id else "profile",
            )
        )
    return dedupe_signals(signals)


def supplemental_capability_signals(evidence_index: list[ProfileEvidenceItem], focus: str) -> list[SummarySignal]:
    signals: list[SummarySignal] = []
    for evidence in evidence_index:
        if not is_summary_content_evidence(evidence):
            continue
        if evidence.evidence_type not in {ProfileEvidenceType.work_experience, ProfileEvidenceType.achievement, ProfileEvidenceType.project}:
            continue
        value = capability_from_text(evidence.original_text)
        if not value or capability_relevance_score(value, focus) <= 20:
            continue
        signals.append(SummarySignal(value=value, evidenceIds=[evidence.evidence_id], source=evidence.source_label))
    return dedupe_signals(signals)


def domain_signals(evidence_index: list[ProfileEvidenceItem], supported_ids: set[str]) -> list[SummarySignal]:
    signals: list[SummarySignal] = []
    for evidence in evidence_index:
        if evidence.evidence_id not in supported_ids:
            continue
        domain = mapped_domain(evidence)
        if domain:
            signals.append(SummarySignal(value=domain, evidenceIds=[evidence.evidence_id], source=evidence.source_label))
    return dedupe_signals(signals)


def metric_signals(evidence_index: list[ProfileEvidenceItem], supported_ids: set[str]) -> list[SummarySignal]:
    signals: list[SummarySignal] = []
    for evidence in evidence_index:
        if (
            evidence.evidence_id in supported_ids
            and is_summary_content_evidence(evidence)
            and re.search(r"\b\d+(?:\.\d+)?\s*(?:%|percent|users?|teams?|hours?|days?)\b", evidence.original_text, re.IGNORECASE)
        ):
            signals.append(SummarySignal(value=evidence.original_text, evidenceIds=[evidence.evidence_id], source=evidence.source_label))
    return dedupe_signals(signals)


def supported_jd_priorities(matches: list[RequirementMatch]) -> list[SummaryJdPriority]:
    output: list[SummaryJdPriority] = []
    for match in sorted(matches, key=lambda item: item.requirement_priority_score, reverse=True):
        evidence_ids = [item.evidence_id for item in match.evidence if item.evidence_id]
        if not evidence_ids:
            continue
        output.append(
            SummaryJdPriority(
                requirementId=match.requirement_id,
                value=match.requirement_value,
                category=match.requirement_category,
                priority=match.requirement_priority,
                priorityScore=match.requirement_priority_score,
                evidenceIds=dedupe_text(evidence_ids),
            )
        )
    return output[:12]


def unsupported_jd_technologies(profile_match: ProfileMatchSummary) -> list[str]:
    values: list[str] = []
    for match in [*profile_match.unmatched_requirements, *profile_match.partially_matched_requirements]:
        if looks_like_technology(match.requirement_value) or match.requirement_category.casefold() in {"technology", "cloud", "languages", "frameworks"}:
            values.append(match.requirement_value)
    return dedupe_text(values)


def looks_like_technology(value: str) -> bool:
    normalized = normalize_text(value)
    return any(term in normalized for term in TECH_CATEGORY_HINTS)


def extract_known_technologies(value: str) -> list[str]:
    normalized = normalize_text(value)
    found = []
    for term in TECH_CATEGORY_HINTS:
        if term in normalized:
            found.append(canonical_summary_technology(display_technology(term)))
    return dedupe_text(found)


def capability_from_text(value: str) -> str:
    text = normalize_text(value)
    patterns = [
        ("production troubleshooting", ("production defect", "production issue", "troubleshoot", "root cause", "issue resolution")),
        ("code reviews", ("code review", "reviewed")),
        ("technical documentation", ("document", "technical changes", "release notes")),
        ("debugging and problem solving", ("debug", "problem-solving", "problem solving", "defect")),
        ("database optimization", ("optimize", "query", "stored procedure", "sql")),
        ("application modernization", ("modernization", "refactor", "upgrade")),
        ("Agile delivery", ("agile", "scrum", "sprint")),
        ("cross-functional collaboration", ("collaborat", "stakeholder", "product owner", "qa", "infrastructure")),
        ("technical ownership", ("ownership", "independently manage", "lead", "led")),
        ("solution design", ("design", "architecture", "enterprise application")),
        ("release and deployment support", ("deployment", "release")),
    ]
    for label, terms in patterns:
        if any(term in text for term in terms):
            return label
    return ""


def is_summary_content_evidence(evidence: ProfileEvidenceItem) -> bool:
    return classify_summary_evidence(evidence) in {
        SummaryEvidenceClass.responsibility,
        SummaryEvidenceClass.achievement,
        SummaryEvidenceClass.capability,
        SummaryEvidenceClass.project_capability,
        SummaryEvidenceClass.collaboration_delivery_capability,
    }


def classify_summary_evidence(evidence: ProfileEvidenceItem) -> SummaryEvidenceClass:
    evidence_id = normalize_text(evidence.evidence_id)
    source_label = normalize_text(evidence.source_label)
    reason = normalize_text(evidence.reason)
    if evidence.evidence_type == ProfileEvidenceType.skill:
        return SummaryEvidenceClass.technology
    if evidence.evidence_type == ProfileEvidenceType.education:
        return SummaryEvidenceClass.education
    if evidence.evidence_type == ProfileEvidenceType.certification:
        return SummaryEvidenceClass.certification_title
    if evidence.evidence_type == ProfileEvidenceType.project:
        return SummaryEvidenceClass.project_capability
    if evidence.evidence_type == ProfileEvidenceType.achievement:
        return SummaryEvidenceClass.achievement
    if evidence.evidence_type == ProfileEvidenceType.summary:
        return SummaryEvidenceClass.role_heading_metadata
    if "stored work-experience field" in reason:
        if "-company-" in evidence_id:
            return SummaryEvidenceClass.company_name
        if "-client-" in evidence_id:
            return SummaryEvidenceClass.client_name
        if "-location-" in evidence_id:
            return SummaryEvidenceClass.location
        if "-role-" in evidence_id:
            return SummaryEvidenceClass.role_heading_metadata
        if "-raw-notes-" in evidence_id or "-legacy-notes-" in evidence_id:
            return SummaryEvidenceClass.excluded_metadata
        return SummaryEvidenceClass.excluded_metadata
    if "structured responsibility" in reason or "-responsibility-" in evidence_id or "-statement-" in evidence_id:
        capability = capability_from_text(evidence.original_text)
        if leadership_or_collaboration_term(capability):
            return SummaryEvidenceClass.collaboration_delivery_capability
        return SummaryEvidenceClass.responsibility
    if " at " in source_label and clean_text(evidence.original_text) == clean_text(evidence.role_title or ""):
        return SummaryEvidenceClass.role_heading_metadata
    return SummaryEvidenceClass.excluded_metadata


def metadata_exclusion_terms(evidence_index: list[ProfileEvidenceItem]) -> tuple[list[str], list[str], list[str], list[str]]:
    all_terms: list[str] = []
    companies: list[str] = []
    clients: list[str] = []
    locations: list[str] = []
    for evidence in evidence_index:
        classification = classify_summary_evidence(evidence)
        text = clean_text(evidence.original_text)
        if not text:
            continue
        if classification == SummaryEvidenceClass.company_name:
            companies.append(text)
            all_terms.append(text)
        elif classification == SummaryEvidenceClass.client_name:
            clients.append(text)
            all_terms.append(text)
        elif classification == SummaryEvidenceClass.location:
            locations.append(text)
            all_terms.append(text)
        elif classification in {
            SummaryEvidenceClass.date,
            SummaryEvidenceClass.contact_data,
            SummaryEvidenceClass.education,
            SummaryEvidenceClass.certification_title,
            SummaryEvidenceClass.role_heading_metadata,
            SummaryEvidenceClass.excluded_metadata,
        }:
            if evidence.evidence_type == ProfileEvidenceType.summary and evidence.source_label == "Profile title":
                continue
            all_terms.append(text)
    return dedupe_text(all_terms), dedupe_text(companies), dedupe_text(clients), dedupe_text(locations)


def mapped_domain(evidence: ProfileEvidenceItem) -> str:
    text = normalize_text(evidence.original_text)
    classification = classify_summary_evidence(evidence)
    if classification in {
        SummaryEvidenceClass.company_name,
        SummaryEvidenceClass.client_name,
        SummaryEvidenceClass.responsibility,
        SummaryEvidenceClass.achievement,
        SummaryEvidenceClass.project_capability,
        SummaryEvidenceClass.collaboration_delivery_capability,
    }:
        for phrase, domain in KNOWN_DOMAIN_MAPPINGS.items():
            if phrase in text:
                return domain
    return ""


def experience_display_value(years: float) -> str:
    whole_years = max(0, int(years))
    if whole_years <= 0:
        return "less than 1 year"
    return f"{whole_years}+ years"


def canonical_summary_technology(value: str) -> str:
    normalized = normalize_text(value)
    for pattern, canonical in SUMMARY_TECH_ALIASES:
        if pattern in normalized:
            return canonical
    return clean_display_term(value)


def prioritize_technologies(values: list[str], *, limit: int) -> list[str]:
    canonical_values = dedupe_text([canonical_summary_technology(value) for value in values if clean_text(value)])
    priority = {value: index for index, value in enumerate(SUMMARY_TECH_PRIORITY)}
    canonical_values.sort(key=lambda value: (priority.get(value, len(priority)), value.casefold()))
    output: list[str] = []
    for value in canonical_values:
        if value == ".NET Framework" and any(item in output for item in ["ASP.NET Core", "ASP.NET MVC"]):
            continue
        if value == "Web API" and "REST APIs" in output:
            continue
        output.append(value)
        if len(output) >= limit:
            break
    return output


def prioritize_summary_technologies(planner: SummaryPlanner, values: list[str], *, limit: int) -> list[str]:
    canonical_values = dedupe_text([canonical_summary_technology(value) for value in values if clean_text(value)])
    focus = jd_focus_text(planner)
    identity = normalize_text(planner.candidate_identity.current_title)
    scored: list[tuple[int, str]] = []
    for value in canonical_values:
        if value == "Azure" and not any(term in focus for term in ["azure", "cloud"]):
            continue
        if value == "AWS" and not any(term in focus for term in ["aws", "cloud"]):
            continue
        score = technology_relevance_score(value, focus, identity)
        if score > 0:
            scored.append((score, value))
    priority = {value: index for index, value in enumerate(SUMMARY_TECH_PRIORITY)}
    scored.sort(key=lambda item: (-item[0], priority.get(item[1], len(priority)), item[1].casefold()))
    return [item[1] for item in scored[:limit]]


def technology_relevance_score(value: str, focus: str, identity: str) -> int:
    normalized = normalize_text(value)
    score = 0
    if normalized in {"c#", "asp.net core", "asp.net mvc"} and ".net" in identity:
        score += 80
    if normalized == ".net framework" and ".net" in identity:
        score += 50
    if normalized == "sql server" and any(term in focus for term in ["sql", "database", "stored procedure", "query", "data"]):
        score += 70
    if normalized == "rest apis" and any(term in focus for term in ["api", "architecture", "interface", "integration"]):
        score += 65
    if normalized in focus:
        score += 60
    if normalized in {"azure", "aws"} and any(term in focus for term in [normalized, "cloud"]):
        score += 70
    if normalized in {"react", "angular", "javascript", "typescript"} and any(term in focus for term in ["front-end", "frontend", "user interface", "ui"]):
        score += 55
    return score


def prioritize_capabilities(planner: SummaryPlanner, values: list[str], *, limit: int) -> list[str]:
    candidates = dedupe_text([clean_display_term(value) for value in values if clean_display_term(value)])
    focus = jd_focus_text(planner)
    scored: list[tuple[int, int, str]] = []
    for index, value in enumerate(candidates):
        scored.append((capability_relevance_score(value, focus), index, value))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored[:limit] if item[0] > 0] or candidates[:limit]


def capability_relevance_score(value: str, focus: str) -> int:
    normalized = normalize_text(value)
    score = 20
    if "production troubleshooting" in normalized and any(term in focus for term in ["issue", "support", "troubleshoot", "problem solve", "defect"]):
        score += 85
    if "debugging" in normalized and any(term in focus for term in ["debug", "problem solve", "issue", "defect"]):
        score += 75
    if "cross-functional collaboration" in normalized and any(term in focus for term in ["stakeholder", "collaborat", "customer", "product manager", "project manager", "business analyst", "qa", "support team"]):
        score += 80
    if "technical documentation" in normalized and any(term in focus for term in ["document", "communication", "technical changes"]):
        score += 65
    if "database optimization" in normalized and any(term in focus for term in ["database", "query", "sql"]):
        score += 65
    if "code reviews" in normalized and any(term in focus for term in ["quality", "code review", "standards", "best practices"]):
        score += 55
    if "release" in normalized and any(term in focus for term in ["schedule", "deployment", "after hours", "support"]):
        score += 45
    if "agile" in normalized and any(term in focus for term in ["project", "schedule", "assigned tasks"]):
        score += 35
    return score


def classify_role_family(focus: str) -> str:
    support_score = sum(
        1
        for term in [
            "production support",
            "application support",
            "app support",
            "support and maintain",
            "issue resolution",
            "incident",
            "defect",
            "troubleshoot",
            "after hours support",
            "reliability",
        ]
        if term in focus
    )
    if any(term in focus for term in ["generative ai", "genai", "rag", "llm", "langchain", "ai engineer", "machine learning"]):
        return "AI / Generative AI Engineering"
    if any(term in focus for term in ["data engineer", "etl", "data pipeline", "databricks", "spark", "azure data factory", "adf", "data warehouse"]):
        return "Data Engineering"
    if support_score >= 2:
        return "Production Support / Application Maintenance"
    if any(term in focus for term in ["devops", "ci/cd", "cloud deployment", "infrastructure", "kubernetes", "docker"]):
        return "Cloud / DevOps"
    if any(term in focus for term in ["database developer", "stored procedure", "query", "sql server database", "database development"]):
        return "Database Development"
    if any(term in focus for term in ["java", "spring boot", "spring"]):
        return "Java Backend Development"
    if any(term in focus for term in ["c#", ".net", "asp.net"]):
        return ".NET Application Development"
    if any(term in focus for term in ["full stack", "front-end", "frontend", "back-end", "backend", "react", "angular"]):
        return "Full Stack Development"
    return "Full Stack Development"


def score_technology_signals(planner: SummaryPlanner, role_family: str, focus: str) -> list[SummarySignalScore]:
    signals = dedupe_signals(
        [
            *planner.experience_level_technologies,
            *planner.profile_level_technologies,
            *planner.project_level_technologies,
        ]
    )
    identity = normalize_text(planner.candidate_identity.current_title)
    scores: list[SummarySignalScore] = []
    for signal in signals:
        value = canonical_summary_technology(signal.value)
        factors = signal_score_factors(value, "technology", signal.evidence_ids, role_family, focus, identity, signal.scope)
        score = weighted_score(factors)
        if score <= 0:
            continue
        scores.append(
            SummarySignalScore(
                value=value,
                signalType="technology",
                score=round(score, 2),
                factors=factors,
                evidenceIds=signal.evidence_ids,
                reason=selection_reason(value, role_family, factors),
            )
        )
    priority = {value: index for index, value in enumerate(SUMMARY_TECH_PRIORITY)}
    scores.sort(key=lambda item: (-item.score, priority.get(item.value, len(priority)), item.value.casefold()))
    return dedupe_score_values(scores)


def score_capability_signals(planner: SummaryPlanner, role_family: str, focus: str) -> list[SummarySignalScore]:
    identity = normalize_text(planner.candidate_identity.current_title)
    scores: list[SummarySignalScore] = []
    for signal in planner.verified_capabilities:
        factors = signal_score_factors(signal.value, "capability", signal.evidence_ids, role_family, focus, identity, signal.source)
        score = weighted_score(factors)
        if score <= 0:
            continue
        scores.append(
            SummarySignalScore(
                value=clean_display_term(signal.value),
                signalType="capability",
                score=round(score, 2),
                factors=factors,
                evidenceIds=signal.evidence_ids,
                reason=selection_reason(signal.value, role_family, factors),
            )
        )
    scores.sort(key=lambda item: (-item.score, generic_capability_penalty(item.value), item.value.casefold()))
    return dedupe_score_values(scores)


def signal_score_factors(
    value: str,
    signal_type: str,
    evidence_ids: list[str],
    role_family: str,
    focus: str,
    identity: str,
    source: str,
) -> dict[str, float]:
    normalized = normalize_text(value)
    jd = jd_relevance_factor(normalized, signal_type, role_family, focus)
    evidence_strength = min(100.0, 55.0 + (len(evidence_ids) * 12.0))
    identity_relevance = identity_relevance_factor(normalized, role_family, identity)
    recency = 80.0 if any(term in normalize_text(source) for term in ["infosys", "current", "present", "profile"]) else 55.0
    frequency = min(100.0, len(evidence_ids) * 20.0)
    return {
        "jdRelevance": jd,
        "evidenceStrength": evidence_strength,
        "candidateIdentityRelevance": identity_relevance,
        "recency": recency,
        "frequency": frequency,
    }


def weighted_score(factors: dict[str, float]) -> float:
    return (
        factors.get("jdRelevance", 0) * 0.40
        + factors.get("evidenceStrength", 0) * 0.30
        + factors.get("candidateIdentityRelevance", 0) * 0.15
        + factors.get("recency", 0) * 0.10
        + factors.get("frequency", 0) * 0.05
    )


def jd_relevance_factor(value: str, signal_type: str, role_family: str, focus: str) -> float:
    if value in focus:
        return 100.0
    families = {
        ".NET Application Development": {
            "c#",
            ".net framework",
            "asp.net core",
            "asp.net mvc",
            "sql server",
            "rest apis",
            "solution design",
            "code reviews",
            "database optimization",
        },
        "Full Stack Development": {
            "c#",
            "asp.net core",
            "asp.net mvc",
            "rest apis",
            "react",
            "angular",
            "javascript",
            "typescript",
            "sql server",
            "solution design",
        },
        "Production Support / Application Maintenance": {
            "production troubleshooting",
            "debugging and problem solving",
            "release and deployment support",
            "technical documentation",
            "cross-functional collaboration",
            "database optimization",
            "sql server",
            ".net framework",
            "c#",
        },
        "Data Engineering": {
            "python",
            "sql server",
            "azure data factory",
            "databricks",
            "apache spark",
            "database optimization",
            "technical documentation",
        },
        "AI / Generative AI Engineering": {
            "python",
            "fastapi",
            "rag",
            "langchain",
            "rest apis",
            "solution design",
            "technical documentation",
        },
        "Java Backend Development": {
            "rest apis",
            "sql server",
            "database optimization",
            "solution design",
            "code reviews",
            "debugging and problem solving",
        },
        "Cloud / DevOps": {
            "azure",
            "docker",
            "kubernetes",
            "release and deployment support",
            "technical documentation",
        },
        "Database Development": {
            "sql server",
            "database optimization",
            "technical documentation",
            "debugging and problem solving",
        },
    }
    if value in families.get(role_family, set()):
        return 90.0
    if signal_type == "capability" and value in GENERIC_SUMMARY_CAPABILITIES:
        return 35.0
    return 20.0


def identity_relevance_factor(value: str, role_family: str, identity: str) -> float:
    score = 30.0
    if ".net" in identity and value in {"c#", ".net framework", "asp.net core", "asp.net mvc", "sql server", "rest apis"}:
        score += 55.0
    if "full stack" in identity and value in {"react", "angular", "javascript", "typescript", "rest apis"}:
        score += 35.0
    if role_family in {".NET Application Development", "Full Stack Development"} and ".net" in identity:
        score += 15.0
    return min(100.0, score)


def generic_capability_penalty(value: str) -> int:
    return 1 if normalize_text(value) in {normalize_text(item) for item in GENERIC_SUMMARY_CAPABILITIES} else 0


def dedupe_score_values(scores: list[SummarySignalScore]) -> list[SummarySignalScore]:
    output: dict[str, SummarySignalScore] = {}
    for score in scores:
        key = normalize_text(score.value)
        if key in output:
            existing = output[key]
            merged_ids = dedupe_text([*existing.evidence_ids, *score.evidence_ids])
            if score.score > existing.score:
                output[key] = score.model_copy(update={"evidence_ids": merged_ids})
            else:
                existing.evidence_ids[:] = merged_ids
        else:
            output[key] = score
    return list(output.values())


def select_scored_values(scores: list[SummarySignalScore], *, limit: int) -> list[str]:
    output: list[str] = []
    for score in scores:
        if score.value == ".NET Framework" and any(item in output for item in ["ASP.NET Core", "ASP.NET MVC"]):
            continue
        if score.value == "Web API" and "REST APIs" in output:
            continue
        output.append(score.value)
        if len(output) >= limit:
            break
    return output


def select_technologies_for_role(scores: list[SummarySignalScore], role_family: str, *, limit: int) -> list[str]:
    selected: list[str] = []
    for preferred_value in role_family_preferred_technologies(role_family):
        match = next((score for score in scores if normalize_text(score.value) == normalize_text(preferred_value)), None)
        if match and match.value not in selected:
            selected.append(match.value)
        if len(selected) >= limit:
            return selected
    for value in select_scored_values(scores, limit=limit):
        if value not in selected:
            selected.append(value)
        if len(selected) >= limit:
            break
    return selected[:limit]


def role_family_preferred_technologies(role_family: str) -> list[str]:
    mapping = {
        "Data Engineering": ["Python", "Azure Data Factory", "Databricks", "Apache Spark", "SQL Server"],
        "AI / Generative AI Engineering": ["Python", "FastAPI", "RAG", "LangChain", "REST APIs"],
        ".NET Application Development": ["C#", "ASP.NET Core", "ASP.NET MVC", "SQL Server", "REST APIs", ".NET Framework"],
        "Production Support / Application Maintenance": ["SQL Server", "C#", ".NET Framework", "REST APIs"],
        "Java Backend Development": ["REST APIs", "SQL Server", "C#", ".NET Framework"],
        "Database Development": ["SQL Server", "Python", "Azure Data Factory"],
        "Cloud / DevOps": ["Azure", "Docker", "Kubernetes"],
    }
    return mapping.get(role_family, [])


def select_capabilities_for_role(scores: list[SummarySignalScore], role_family: str, *, limit: int) -> list[str]:
    selected: list[str] = []
    generic_count = 0
    preferred = role_family_preferred_capabilities(role_family)
    for preferred_value in preferred:
        match = next((score for score in scores if normalize_text(score.value) == normalize_text(preferred_value)), None)
        if match and match.value not in selected:
            selected.append(match.value)
            if len(selected) >= limit:
                return selected
    for score in scores:
        is_generic = normalize_text(score.value) in {normalize_text(item) for item in GENERIC_SUMMARY_CAPABILITIES}
        generic_terms = {normalize_text(g) for g in GENERIC_SUMMARY_CAPABILITIES}
        if is_generic and generic_count >= 1 and any(normalize_text(item) not in generic_terms for item in selected):
            continue
        if score.value not in selected:
            selected.append(score.value)
            generic_count += 1 if is_generic else 0
        if len(selected) >= limit:
            break
    if not selected:
        return role_family_default_capabilities(role_family)
    return selected[:limit]


def role_family_preferred_capabilities(role_family: str) -> list[str]:
    mapping = {
        "Production Support / Application Maintenance": ["production troubleshooting", "debugging and problem solving", "release and deployment support", "database optimization"],
        "Data Engineering": ["database optimization", "technical documentation", "cross-functional collaboration"],
        "AI / Generative AI Engineering": ["solution design", "technical documentation", "cross-functional collaboration"],
        ".NET Application Development": ["solution design", "code reviews", "database optimization"],
        "Java Backend Development": ["solution design", "code reviews", "database optimization"],
    }
    return mapping.get(role_family, [])


def role_family_work_themes(role_family: str, capabilities: list[str], focus: str) -> list[str]:
    mapping = {
        ".NET Application Development": ["enterprise .NET application development"],
        "Java Backend Development": ["backend service and API delivery"],
        "Full Stack Development": ["full-stack feature delivery"],
        "Production Support / Application Maintenance": ["production application maintenance and reliability"],
        "Data Engineering": ["data pipeline and analytics engineering"],
        "AI / Generative AI Engineering": ["AI-enabled application development"],
        "Cloud / DevOps": ["cloud delivery and deployment reliability"],
        "Database Development": ["database development and query optimization"],
    }
    themes = mapping.get(role_family, ["enterprise application delivery"])
    if "application modernization" in {normalize_text(item) for item in capabilities}:
        themes.append("application modernization")
    return themes


def role_family_default_capabilities(role_family: str) -> list[str]:
    mapping = {
        ".NET Application Development": ["solution design", "code reviews", "database optimization"],
        "Java Backend Development": ["REST API design", "database optimization", "code reviews"],
        "Full Stack Development": ["solution design", "cross-functional collaboration", "code reviews"],
        "Production Support / Application Maintenance": ["production troubleshooting", "debugging and problem solving", "release and deployment support"],
        "Data Engineering": ["database optimization", "technical documentation", "cross-functional collaboration"],
        "AI / Generative AI Engineering": ["solution design", "REST API design", "technical documentation"],
        "Cloud / DevOps": ["release and deployment support", "technical documentation", "cross-functional collaboration"],
        "Database Development": ["database optimization", "debugging and problem solving", "technical documentation"],
    }
    return mapping.get(role_family, ["requirements analysis", "cross-functional collaboration", "technical documentation"])


def closing_value_statement(role_family: str, capabilities: list[str]) -> str:
    mapping = {
        ".NET Application Development": "Turns business requirements into scalable .NET features with clear API, database, and UI implementation.",
        "Java Backend Development": "Applies transferable API, database, and service-design experience while keeping unsupported stack-specific claims out of the resume.",
        "Full Stack Development": "Connects backend services, UI changes, and stakeholder feedback into reliable full-stack delivery.",
        "Production Support / Application Maintenance": "Collaborates with product, QA, support, and engineering teams to resolve defects and keep enterprise systems stable.",
        "Data Engineering": "Turns integration and reporting needs into reliable data flows for analytics and downstream teams.",
        "AI / Generative AI Engineering": "Connects API design, retrieval workflows, and model-facing services to deliver practical AI features.",
        "Cloud / DevOps": "Strengthens release readiness through deployment planning, environment awareness, and cross-team coordination.",
        "Database Development": "Improves data reliability by aligning SQL design, query behavior, and application requirements.",
    }
    return mapping.get(role_family, "Translates business requirements into reliable, maintainable software through clear implementation and team communication.")


def selection_reason(value: str, role_family: str, factors: dict[str, float]) -> str:
    return (
        f"Selected {value} for {role_family}: JD relevance {factors['jdRelevance']:.0f}, "
        f"evidence {factors['evidenceStrength']:.0f}, identity {factors['candidateIdentityRelevance']:.0f}."
    )


def target_emphasis_variation_score(emphasis: SummaryTargetEmphasis) -> float:
    signal_count = len(emphasis.top_supported_technologies) + len(emphasis.top_supported_capabilities) + len(emphasis.target_work_themes)
    generic_count = sum(1 for item in emphasis.top_supported_capabilities if normalize_text(item) in {normalize_text(value) for value in GENERIC_SUMMARY_CAPABILITIES})
    return round(max(0.0, min(1.0, (signal_count - generic_count) / 9)), 2)


def baseline_technology_set(planner: SummaryPlanner) -> list[str]:
    return prioritize_technologies(
        [
            *[item.value for item in planner.profile_level_technologies],
            *[item.value for item in planner.experience_level_technologies],
        ],
        limit=4,
    )


def domain_relevant_to_focus(domain: str, focus: str) -> bool:
    normalized = normalize_text(domain)
    if normalized in focus:
        return True
    if normalized == "healthcare" and any(term in focus for term in ["healthcare", "provider", "claims", "authorization", "mcg"]):
        return True
    if normalized == "financial services" and any(term in focus for term in ["finance", "financial", "banking", "payment"]):
        return True
    return False


def jd_focus_text(planner: SummaryPlanner) -> str:
    return normalize_text(
        " ".join(
            [
                planner.candidate_identity.current_title,
                str(planner.constraints.get("jobFocusText", "")),
                *[priority.value for priority in planner.supported_jd_priorities],
                *[priority.category for priority in planner.supported_jd_priorities],
            ]
        )
    )


def payload_focus_text(payload: GenerateResumeRequest) -> str:
    analysis = payload.job_analysis
    requirement_parts: list[str] = []
    if analysis:
        for collection in (
            analysis.normalized_requirements.technical_requirements,
            analysis.normalized_requirements.responsibility_requirements,
            analysis.normalized_requirements.leadership_requirements,
            analysis.normalized_requirements.domain_requirements,
        ):
            for requirement in collection:
                requirement_parts.extend([requirement.canonical_term, requirement.category])
    return normalize_text(" ".join([payload.job_description, payload.target_role, payload.level, *requirement_parts]))


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalize_text(value: str) -> str:
    return clean_text(value).casefold()


def phrase_present(value: str, phrase: str) -> bool:
    return normalize_text(phrase) in normalize_text(value)


def display_technology(value: str) -> str:
    mapping = {
        "c#": "C#",
        ".net": ".NET",
        ".net framework": ".NET Framework",
        "asp.net core": "ASP.NET Core",
        "asp.net mvc": "ASP.NET MVC",
        "sql server": "SQL Server",
        "microsoft sql server": "Microsoft SQL Server",
        "t-sql": "T-SQL",
        "rest api": "REST APIs",
        "restful api": "REST APIs",
        "web api": "Web API",
        "azure": "Azure",
        "aws": "AWS",
        "java": "Java",
        "javascript": "JavaScript",
        "typescript": "TypeScript",
        "python": "Python",
        "fastapi": "FastAPI",
        "rag": "RAG",
        "langchain": "LangChain",
        "azure data factory": "Azure Data Factory",
        "adf": "Azure Data Factory",
        "databricks": "Databricks",
        "spark": "Apache Spark",
        "apache spark": "Apache Spark",
        "react": "React",
        "angular": "Angular",
        "next.js": "Next.js",
        "docker": "Docker",
        "kubernetes": "Kubernetes",
        "spring boot": "Spring Boot",
    }
    return mapping.get(value, value)


def prioritize_terms(values: list[str], *, limit: int) -> list[str]:
    return dedupe_text([clean_display_term(value) for value in values if clean_display_term(value)])[:limit]


def clean_display_term(value: str) -> str:
    return clean_text(value).strip(".,;:")


def planner_evidence_for_terms(planner: SummaryPlanner, terms: list[str]) -> list[str]:
    output: list[str] = []
    normalized_terms = {normalize_text(term) for term in terms}
    for collection in (
        planner.profile_level_technologies,
        planner.experience_level_technologies,
        planner.project_level_technologies,
        planner.verified_capabilities,
        planner.verified_domains,
    ):
        for signal in collection:
            if normalize_text(signal.value) in normalized_terms:
                output.extend(signal.evidence_ids)
    return dedupe_text(output)


def dedupe_signals(signals: list[SummarySignal]) -> list[SummarySignal]:
    by_value: dict[str, SummarySignal] = {}
    for signal in signals:
        key = normalize_text(signal.value)
        if key in by_value:
            by_value[key].evidence_ids[:] = dedupe_text([*by_value[key].evidence_ids, *signal.evidence_ids])
        else:
            by_value[key] = signal
    return list(by_value.values())


def dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = clean_text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def human_join(values: list[str]) -> str:
    values = [value for value in values if value]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def count_sentences(value: str) -> int:
    protected = re.sub(r"(?<=\d)\.(?=\d)", "<DOT>", value)
    protected = re.sub(r"\b([A-Za-z]{1,4})\.(?=[A-Za-z])", lambda match: match.group(0).replace(".", "<DOT>"), protected)
    return len([part for part in re.split(r"[.!?]+(?:\s+|$)", protected) if part.strip()])


def word_count(value: str) -> int:
    return len(re.findall(r"\b[\w#+./-]+\b", value))


def mentions_leadership(value: str) -> bool:
    normalized = normalize_text(value)
    return any(term in normalized for term in LEADERSHIP_TERMS)


def mentions_architecture(value: str) -> bool:
    normalized = normalize_text(value)
    return any(term in normalized for term in ARCHITECTURE_TERMS)


def leadership_or_collaboration_term(value: str) -> bool:
    normalized = normalize_text(value)
    return any(term in normalized for term in [*LEADERSHIP_TERMS, "collaboration", "stakeholder", "qa", "product owner"])


def architecture_term(value: str) -> bool:
    normalized = normalize_text(value)
    return any(term in normalized for term in ARCHITECTURE_TERMS)


def contains_invented_metric(summary: str, planner: SummaryPlanner) -> bool:
    allowed_numbers = {str(int(planner.candidate_identity.years_of_experience))}
    allowed_numbers.add(f"{planner.candidate_identity.years_of_experience:g}")
    for metric in planner.allowed_metrics:
        allowed_numbers.update(re.findall(r"\d+(?:\.\d+)?", metric.value))
    for number in re.findall(r"\d+(?:\.\d+)?", summary):
        if number not in allowed_numbers:
            return True
    return False


def looks_like_keyword_list(summary: str) -> bool:
    if ":" in summary:
        return True
    comma_count = summary.count(",")
    return comma_count >= 11


def has_generic_repetitive_language(summary: str) -> bool:
    normalized = normalize_text(summary)
    banned_phrases = {
        "software delivery while turning business requirements into reliable software solutions",
        "evidence-backed resume claims",
        "grounded in",
    }
    if any(phrase in normalized for phrase in banned_phrases):
        return True
    for sentence in re.split(r"[.!?]+", normalized):
        if not sentence.strip():
            continue
        repeated_terms = sum(sentence.count(term) for term in ["software", "application", "delivery"])
        if repeated_terms >= 4:
            return True
    return False


def theme_present(summary: str, theme: str) -> bool:
    normalized_summary = normalize_text(summary)
    normalized_theme = normalize_text(theme)
    if normalized_theme in normalized_summary:
        return True
    theme_terms = [term for term in re.findall(r"\b[a-z0-9+#.-]{4,}\b", normalized_theme) if term not in {"application", "development", "delivery"}]
    return bool(theme_terms) and any(term in normalized_summary for term in theme_terms[:3])


def is_reused_generic_summary(summary: str) -> bool:
    normalized = normalize_text(summary)
    plain = re.sub(r"[^a-z0-9+#.]+", " ", normalized)
    repeated_shapes = {
        "experienced in requirements analysis debugging and technical documentation across agile delivery teams",
        "translates business requirements into reliable maintainable software through clear implementation and team communication",
        "building and maintaining enterprise applications using sql server azure and sql server",
    }
    return any(shape in plain for shape in repeated_shapes)


def repeated_phrases(summary: str) -> list[str]:
    words = re.findall(r"\b[a-z0-9+#.-]+\b", normalize_text(summary))
    phrases = [" ".join(words[index : index + 3]) for index in range(max(0, len(words) - 2))]
    seen: set[str] = set()
    repeated: list[str] = []
    for phrase in phrases:
        if phrase in seen and phrase not in repeated:
            repeated.append(phrase)
        seen.add(phrase)
    return repeated


def dedupe_codes(values: list[SummaryValidationCode]) -> list[SummaryValidationCode]:
    seen: set[SummaryValidationCode] = set()
    output: list[SummaryValidationCode] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def summary_job_id(payload: GenerateResumeRequest) -> str:
    return recent_job_id(payload.job_description, payload.target_role, payload.target_company)
