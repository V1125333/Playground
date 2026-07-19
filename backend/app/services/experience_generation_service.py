from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Protocol

from pydantic import BaseModel, Field

from app.core.config import settings
from app.schemas.resume import (
    ExperienceBulletGenerationResult,
    ExperienceBulletModelResponse,
    ExperienceBulletValidationIssue,
    ExperienceBulletValidationResult,
    ExperienceGeneratedBullet,
    ExperienceIntelligencePlan,
    ExperiencePromptInput,
    ExperienceRoleIntelligence,
)
from app.services.ai_usage import AICompletionResult, get_ai_service, stable_hash
from app.services.structured_bullets import stable_bullet_id


EXPERIENCE_WRITER_SYSTEM_PROMPT = (
    "You are an expert technical resume bullet writer.\n\n"
    "Write professional resume bullets using only the approved facts in the supplied ExperiencePromptInput.\n\n"
    "The application has already selected the evidence, technologies, capabilities, metrics, projects, themes, "
    "and requirements.\n\n"
    "Do not introduce any fact that is not explicitly approved.\n\n"
    "Do not invent technologies, metrics, leadership, architecture ownership, team size, budget, performance "
    "percentages, business impact, cloud platforms, domain claims, or responsibilities.\n\n"
    "Do not use excluded terms.\n\n"
    "Every bullet must begin with a strong action verb, use concise professional language, remain within the "
    "configured word limit, avoid first-person language, avoid repetitive openings, avoid generic filler, and "
    "be traceable to supplied evidence IDs.\n\n"
    "Return valid JSON only."
)

EXPERIENCE_INVALID_EVIDENCE_ID = "EXPERIENCE_INVALID_EVIDENCE_ID"
EXPERIENCE_INVALID_REQUIREMENT_ID = "EXPERIENCE_INVALID_REQUIREMENT_ID"
EXPERIENCE_WRONG_ROLE = "EXPERIENCE_WRONG_ROLE"
EXPERIENCE_UNSUPPORTED_TECHNOLOGY = "EXPERIENCE_UNSUPPORTED_TECHNOLOGY"
EXPERIENCE_UNSUPPORTED_METRIC = "EXPERIENCE_UNSUPPORTED_METRIC"
EXPERIENCE_UNSUPPORTED_LEADERSHIP = "EXPERIENCE_UNSUPPORTED_LEADERSHIP"
EXPERIENCE_UNSUPPORTED_ARCHITECTURE = "EXPERIENCE_UNSUPPORTED_ARCHITECTURE"
EXPERIENCE_METADATA_LEAKAGE = "EXPERIENCE_METADATA_LEAKAGE"
EXPERIENCE_EXCLUDED_TERM = "EXPERIENCE_EXCLUDED_TERM"
EXPERIENCE_TOO_LONG = "EXPERIENCE_TOO_LONG"
EXPERIENCE_DUPLICATE_BULLET = "EXPERIENCE_DUPLICATE_BULLET"
EXPERIENCE_REPEATED_OPENING = "EXPERIENCE_REPEATED_OPENING"
EXPERIENCE_GENERIC_FILLER = "EXPERIENCE_GENERIC_FILLER"
EXPERIENCE_INSUFFICIENT_SUPPORT = "EXPERIENCE_INSUFFICIENT_SUPPORT"
EXPERIENCE_BULLET_COUNT_MISMATCH = "EXPERIENCE_BULLET_COUNT_MISMATCH"

ACTION_VERBS = {
    "analyzed",
    "authored",
    "built",
    "collaborated",
    "configured",
    "coordinated",
    "created",
    "delivered",
    "designed",
    "developed",
    "documented",
    "implemented",
    "improved",
    "integrated",
    "led",
    "maintained",
    "optimized",
    "reviewed",
    "resolved",
    "supported",
    "troubleshot",
}

GENERIC_FILLER = {
    "responsible for",
    "worked on",
    "helped with",
    "various tasks",
    "as needed",
    "other duties",
    "utilized skills",
}

KNOWN_TECHNOLOGIES = {
    "java",
    "spring boot",
    "aws",
    "azure",
    "kubernetes",
    "docker",
    "python",
    "fastapi",
    "rag",
    "langchain",
    "spark",
    "databricks",
    "adf",
    "azure data factory",
    "c#",
    ".net",
    "asp.net core",
    "asp.net mvc",
    "sql server",
    "t-sql",
    "react",
    "angular",
    "rest api",
    "rest apis",
}

LEADERSHIP_TERMS = {"led", "mentored", "coached", "guided", "owned", "ownership", "technical leadership"}
ARCHITECTURE_TERMS = {"architecture", "architected", "solution design", "system design", "technical design"}


class ExperienceAIService(Protocol):
    def model_for(self, model_key: str) -> str:
        ...

    async def responses_json(self, **kwargs) -> AICompletionResult:
        ...


class ExperienceGenerationError(Exception):
    pass


class ExperienceGenerationRun(BaseModel):
    plan: ExperienceIntelligencePlan
    role_results: list[ExperienceBulletGenerationResult] = Field(default_factory=list, alias="roleResults")

    model_config = {"populate_by_name": True}


async def generate_experience_intelligence(
    plan: ExperienceIntelligencePlan,
    *,
    ai_service: ExperienceAIService | None = None,
    max_retries: int = 1,
) -> ExperienceIntelligencePlan:
    prompts = [prompt for prompt in plan.experience_prompt_inputs if prompt.validation_result.is_valid]
    skipped_prompt_ids = [
        prompt.experience_id
        for prompt in plan.experience_prompt_inputs
        if not prompt.validation_result.is_valid
    ]
    max_calls = max(0, int(settings.ai_experience_max_role_calls or 0))
    prompts = prompts[:max_calls] if max_calls else prompts
    service = ai_service or get_ai_service()
    model = service.model_for("experience_generation")
    config_hash = experience_model_configuration_hash(model)
    concurrency = max(1, int(settings.ai_experience_concurrency or 1))
    semaphore = asyncio.Semaphore(concurrency)

    async def run_one(prompt: ExperiencePromptInput) -> ExperienceBulletGenerationResult:
        async with semaphore:
            return await generate_experience_bullets(prompt, service=service, max_retries=max_retries)

    results = await asyncio.gather(*(run_one(prompt) for prompt in prompts))
    roles = [role_result_to_intelligence(result) for result in results]
    invalid_results = [result for result in results if not result.validation_result.is_valid]
    validation_status = "invalid" if invalid_results or skipped_prompt_ids else "valid"
    if validation_status == "valid" and any(result.generation_method == "deterministic_fallback" or result.validation_result.warnings for result in results):
        validation_status = "valid_with_warnings"
    warnings = [*plan.warnings]
    warnings.extend(f"{experience_id}: prompt skipped because validation failed" for experience_id in skipped_prompt_ids)
    for result in results:
        warnings.extend(f"{result.experience_id}: {issue.code}" for issue in result.validation_result.issues)
        warnings.extend(f"{result.experience_id}: {warning}" for warning in result.validation_result.warnings)
    return plan.model_copy(
        update={
            "role_intelligence": roles,
            "writer_prompt_version": settings.experience_writer_prompt_version,
            "writer_model": model,
            "model_configuration_hash": config_hash,
            "overall_validation_status": validation_status,
            "validation_status": validation_status,
            "warnings": dedupe(warnings),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


async def generate_experience_bullets(
    prompt_input: ExperiencePromptInput,
    *,
    service: ExperienceAIService | None = None,
    max_retries: int = 1,
) -> ExperienceBulletGenerationResult:
    service = service or get_ai_service()
    model = service.model_for("experience_generation")
    should_use_openai = bool(settings.openai_api_key and settings.ai_experience_generation_enabled)
    validation_messages: list[str] = []
    if should_use_openai:
        for attempt in range(max_retries + 1):
            try:
                response = await call_experience_model(
                    prompt_input,
                    service=service,
                    previous_errors=validation_messages,
                )
                validation = validate_experience_bullets(prompt_input, response)
                if validation.is_valid:
                    return model_response_to_generation(
                        prompt_input,
                        response,
                        validation,
                        model=model,
                        method="openai" if attempt == 0 else "retry",
                        retry_count=attempt,
                    )
                validation_messages = [issue.code for issue in validation.issues]
            except Exception as exc:
                validation_messages = [f"Experience OpenAI generation failed: {exc}"]
                if attempt >= max_retries:
                    break

    fallback = deterministic_fallback_response(prompt_input)
    validation = validate_experience_bullets(prompt_input, fallback)
    return model_response_to_generation(
        prompt_input,
        fallback,
        validation,
        model=model,
        method="deterministic_fallback",
        retry_count=max(0, len(validation_messages)),
    )


async def call_experience_model(
    prompt_input: ExperiencePromptInput,
    *,
    service: ExperienceAIService,
    previous_errors: list[str] | None = None,
) -> ExperienceBulletModelResponse:
    payload = {
        "experiencePromptInput": prompt_input.model_dump(mode="json", by_alias=True),
        "previousValidationErrors": previous_errors or [],
    }
    result = await service.responses_json(
        feature="experience_generation",
        purpose="Experience Bullet Generation",
        model_key="experience_generation",
        system_prompt=EXPERIENCE_WRITER_SYSTEM_PROMPT,
        user_payload=payload,
        json_schema=ExperienceBulletModelResponse.model_json_schema(by_alias=True),
        max_output_tokens=settings.openai_experience_max_output_tokens,
        timeout_seconds=settings.openai_experience_timeout_seconds,
        cache_parts={
            "promptVersion": settings.experience_writer_prompt_version,
            "experiencePromptInput": prompt_input.model_dump(mode="json", by_alias=True),
        },
        job_id=stable_hash(
            {
                "experienceId": prompt_input.experience_id,
                "targetRole": prompt_input.target_context.target_role,
                "targetCompany": prompt_input.target_context.target_company,
            }
        )[:16],
    )
    return ExperienceBulletModelResponse.model_validate_json(result.content)


def validate_experience_bullets(
    prompt_input: ExperiencePromptInput,
    model_response: ExperienceBulletModelResponse,
) -> ExperienceBulletValidationResult:
    issues: list[ExperienceBulletValidationIssue] = []
    warnings: list[str] = []
    valid_evidence_ids = {item.evidence_id for item in prompt_input.approved_evidence}
    valid_requirement_ids = set(prompt_input.supported_requirement_ids)
    approved_tech = approved_technology_terms(prompt_input)
    approved_metric_text = normalized(" ".join([metric.value for metric in prompt_input.approved_metrics]))
    approved_capability_text = normalized(" ".join([capability.name for capability in prompt_input.approved_capabilities]))
    approved_project_ids = {project.project_id for project in prompt_input.linked_projects}
    approved_project_names = {normalized(project.project_name) for project in prompt_input.linked_projects}

    if model_response.experience_id != prompt_input.experience_id:
        issues.append(issue(EXPERIENCE_WRONG_ROLE, "Model response experienceId does not match the prompt."))
    if len(model_response.bullets) != prompt_input.writing_rules.bullet_count:
        issues.append(issue(EXPERIENCE_BULLET_COUNT_MISMATCH, "Bullet count does not match the requested count."))
    if len(model_response.bullets) > prompt_input.writing_rules.bullet_count:
        issues.append(issue(EXPERIENCE_BULLET_COUNT_MISMATCH, "Bullet count exceeds the requested count."))

    normalized_bullets: list[str] = []
    openings: list[str] = []
    for index, bullet in enumerate(model_response.bullets):
        text = clean_sentence(bullet.generated_text)
        normalized_text = normalized(text)
        normalized_bullets.append(normalized_text)
        first_word = first_token(text)
        if first_word:
            openings.append(first_word)
        if not text:
            issues.append(issue(EXPERIENCE_INSUFFICIENT_SUPPORT, "Bullet text is empty.", index))
        if first_word not in ACTION_VERBS:
            issues.append(issue(EXPERIENCE_GENERIC_FILLER, "Bullet does not start with a strong action verb.", index))
        if contains_first_person(text):
            issues.append(issue(EXPERIENCE_GENERIC_FILLER, "Bullet uses first-person language.", index))
        if word_count(text) > prompt_input.writing_rules.maximum_words_per_bullet:
            issues.append(issue(EXPERIENCE_TOO_LONG, "Bullet exceeds the configured word limit.", index))
        if any(term in normalized_text for term in GENERIC_FILLER):
            issues.append(issue(EXPERIENCE_GENERIC_FILLER, "Bullet contains generic filler.", index))
        if any(normalized(term) and normalized(term) in normalized_text for term in prompt_input.excluded_terms):
            issues.append(issue(EXPERIENCE_EXCLUDED_TERM, "Bullet mentions an excluded term.", index))
        if metadata_leakage(text, prompt_input):
            issues.append(issue(EXPERIENCE_METADATA_LEAKAGE, "Bullet includes company, client, or location metadata.", index))
        invalid_evidence = [evidence_id for evidence_id in bullet.supporting_evidence_ids if evidence_id not in valid_evidence_ids]
        if invalid_evidence:
            issues.append(issue(EXPERIENCE_INVALID_EVIDENCE_ID, "Bullet cites evidence outside the prompt.", index, invalid_evidence))
        if not bullet.supporting_evidence_ids:
            issues.append(issue(EXPERIENCE_INSUFFICIENT_SUPPORT, "Bullet has no supporting evidence IDs.", index))
        invalid_requirements = [requirement_id for requirement_id in bullet.supported_requirement_ids if requirement_id not in valid_requirement_ids]
        if invalid_requirements:
            issues.append(issue(EXPERIENCE_INVALID_REQUIREMENT_ID, "Bullet cites unsupported requirement IDs.", index))
        unsupported_tech = unsupported_technology_terms(text, approved_tech)
        if unsupported_tech:
            issues.append(issue(EXPERIENCE_UNSUPPORTED_TECHNOLOGY, f"Bullet mentions unsupported technology: {', '.join(unsupported_tech)}.", index))
        if unsupported_metric(text, approved_metric_text):
            issues.append(issue(EXPERIENCE_UNSUPPORTED_METRIC, "Bullet includes a metric not approved in the prompt.", index))
        if unsupported_leadership(text, approved_capability_text):
            issues.append(issue(EXPERIENCE_UNSUPPORTED_LEADERSHIP, "Bullet includes unsupported leadership claim.", index))
        if unsupported_architecture(text, approved_capability_text):
            issues.append(issue(EXPERIENCE_UNSUPPORTED_ARCHITECTURE, "Bullet includes unsupported architecture ownership claim.", index))
        if invented_project_attribution(text, approved_project_ids, approved_project_names, prompt_input):
            issues.append(issue(EXPERIENCE_INVALID_EVIDENCE_ID, "Bullet attributes work to an unapproved project.", index))
        if not substantively_supported(text, bullet.supporting_evidence_ids, prompt_input):
            issues.append(issue(EXPERIENCE_INSUFFICIENT_SUPPORT, "Bullet text is not substantively supported by cited evidence.", index))

    if len(set(normalized_bullets)) != len([item for item in normalized_bullets if item]):
        issues.append(issue(EXPERIENCE_DUPLICATE_BULLET, "Duplicate or near-duplicate bullets were returned."))
    if repeated_opening(openings):
        issues.append(issue(EXPERIENCE_REPEATED_OPENING, "Too many bullets start with the same action verb."))
    return ExperienceBulletValidationResult(isValid=not issues, issues=dedupe_issues(issues), warnings=dedupe(warnings))


def deterministic_fallback_response(prompt_input: ExperiencePromptInput) -> ExperienceBulletModelResponse:
    bullets = []
    evidence = prompt_input.approved_evidence[: prompt_input.writing_rules.bullet_count]
    technologies = [item.name for item in prompt_input.approved_technologies]
    capabilities = [item.name for item in prompt_input.approved_capabilities]
    metric_by_evidence = {
        evidence_id: metric.value
        for metric in prompt_input.approved_metrics
        for evidence_id in metric.evidence_ids
    }
    verbs = ["Delivered", "Implemented", "Improved", "Supported", "Documented", "Reviewed"]
    for index, item in enumerate(evidence):
        tech = technologies[index % len(technologies)] if technologies else ""
        capability = capabilities[index % len(capabilities)] if capabilities else "application delivery"
        metric = metric_by_evidence.get(item.evidence_id, "")
        parts = [verbs[index % len(verbs)], capability]
        if tech:
            parts.append(f"using {tech}")
        parts.append("for enterprise application work")
        if metric:
            parts.append(f"with {metric}")
        text = clean_sentence(" ".join(parts))
        bullets.append(
            {
                "generatedText": trim_words(text, prompt_input.writing_rules.maximum_words_per_bullet),
                "supportingEvidenceIds": [item.evidence_id],
                "supportedRequirementIds": prompt_input.supported_requirement_ids[:2],
            }
        )
    return ExperienceBulletModelResponse.model_validate({"experienceId": prompt_input.experience_id, "bullets": bullets})


def model_response_to_generation(
    prompt_input: ExperiencePromptInput,
    response: ExperienceBulletModelResponse,
    validation: ExperienceBulletValidationResult,
    *,
    model: str,
    method: str,
    retry_count: int,
) -> ExperienceBulletGenerationResult:
    issue_codes = [item.code for item in validation.issues]
    bullets = [
        ExperienceGeneratedBullet(
            bulletId=stable_bullet_id(prompt_input.prompt_version, prompt_input.experience_id, index + 1, item.generated_text),
            order=index + 1,
            generatedText=clean_sentence(item.generated_text),
            currentText=clean_sentence(item.generated_text),
            userEdited=False,
            supportingEvidenceIds=item.supporting_evidence_ids,
            supportedRequirementIds=item.supported_requirement_ids,
            validationStatus="validated" if validation.is_valid else ("fallback" if method == "deterministic_fallback" else "invalid"),
            warnings=issue_codes,
            generationMethod=method,
            model=model,
            promptVersion=settings.experience_writer_prompt_version,
        )
        for index, item in enumerate(response.bullets)
    ]
    return ExperienceBulletGenerationResult(
        experienceId=prompt_input.experience_id,
        bullets=bullets,
        generationMethod=method,
        model=model,
        promptVersion=settings.experience_writer_prompt_version,
        validationResult=validation,
        retryCount=retry_count,
    )


def role_result_to_intelligence(result: ExperienceBulletGenerationResult) -> ExperienceRoleIntelligence:
    warnings = [issue.code for issue in result.validation_result.issues]
    warnings.extend(result.validation_result.warnings)
    config_hash = experience_model_configuration_hash(result.model)
    return ExperienceRoleIntelligence(
        experienceId=result.experience_id,
        bullets=result.bullets,
        generationMode=result.generation_method,
        model=result.model,
        promptVersion=result.prompt_version,
        validationStatus="valid" if result.validation_result.is_valid else "invalid",
        warnings=dedupe(warnings),
        modelConfigurationHash=config_hash,
    )


def experience_model_configuration_hash(model: str | None = None) -> str:
    return stable_hash(
        {
            "model": model or settings.openai_experience_model,
            "maxOutputTokens": settings.openai_experience_max_output_tokens,
            "timeoutSeconds": settings.openai_experience_timeout_seconds,
            "promptVersion": settings.experience_writer_prompt_version,
            "maxRoleCalls": settings.ai_experience_max_role_calls,
            "concurrency": settings.ai_experience_concurrency,
        }
    )


def issue(code: str, message: str, bullet_index: int | None = None, evidence_ids: list[str] | None = None) -> ExperienceBulletValidationIssue:
    return ExperienceBulletValidationIssue(code=code, message=message, bulletIndex=bullet_index, evidenceIds=evidence_ids or [])


def clean_sentence(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip(" -*\t\r\n"))
    return text.rstrip(".") + "." if text else ""


def first_token(text: str) -> str:
    match = re.match(r"([A-Za-z]+)", text.strip())
    return (match.group(1).casefold() if match else "")


def contains_first_person(text: str) -> bool:
    return bool(re.search(r"(?i)\b(i|me|my|mine|we|our|ours)\b", text))


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w+#./-]+\b", text))


def normalized(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def unsupported_technology_terms(text: str, approved_tech: set[str]) -> list[str]:
    value = normalized(text)
    unsupported = []
    for tech in KNOWN_TECHNOLOGIES:
        if term_present(value, tech) and normalized(tech) not in approved_tech:
            unsupported.append(tech)
    return dedupe(unsupported)


def approved_technology_terms(prompt: ExperiencePromptInput) -> set[str]:
    terms = {normalized(item.name) for item in prompt.approved_technologies}
    capability_text = normalized(" ".join(item.name for item in prompt.approved_capabilities))
    if "api" in capability_text:
        terms.update({"api", "rest api", "rest apis"})
    if ".net" in capability_text:
        terms.update({".net", "asp.net core", "asp.net mvc"})
    if "sql" in capability_text:
        terms.update({"sql server", "t-sql"})
    for term in list(terms):
        if term == "rest api":
            terms.add("rest apis")
        if term == "rest apis":
            terms.add("rest api")
        if term in {"microsoft sql server", "ms sql server"}:
            terms.add("sql server")
    return terms


def term_present(text: str, term: str) -> bool:
    key = re.escape(normalized(term))
    if not key:
        return False
    return bool(re.search(rf"(?<![a-z0-9+#.]){key}(?![a-z0-9+#.])", text))


def unsupported_metric(text: str, approved_metric_text: str) -> bool:
    metrics = re.findall(r"\b\d+(?:\.\d+)?\s*%|\b\d+(?:\.\d+)?x\b|\b\d+(?:\.\d+)?\s*(?:users|hours|days|minutes|records|defects)\b", text, flags=re.I)
    return any(normalized(metric) not in approved_metric_text for metric in metrics)


def unsupported_leadership(text: str, approved_capability_text: str) -> bool:
    value = normalized(text)
    return any(term in value for term in LEADERSHIP_TERMS) and not any(term in approved_capability_text for term in LEADERSHIP_TERMS)


def unsupported_architecture(text: str, approved_capability_text: str) -> bool:
    value = normalized(text)
    return any(term in value for term in ARCHITECTURE_TERMS) and not any(term in approved_capability_text for term in ARCHITECTURE_TERMS)


def metadata_leakage(text: str, prompt: ExperiencePromptInput) -> bool:
    value = normalized(text)
    metadata_values = {
        normalized(prompt.role_context.company_name),
        normalized(prompt.role_context.client_name or ""),
    }
    return any(item and item in value for item in metadata_values)


def invented_project_attribution(
    text: str,
    approved_project_ids: set[str],
    approved_project_names: set[str],
    prompt: ExperiencePromptInput,
) -> bool:
    _ = approved_project_ids
    value = normalized(text)
    if not prompt.linked_projects and "project" in value:
        return True
    return any(name and name in value for name in approved_project_names if name not in {""}) and not prompt.linked_projects


def substantively_supported(text: str, evidence_ids: list[str], prompt: ExperiencePromptInput) -> bool:
    if not evidence_ids:
        return False
    evidence_text = normalized(" ".join(item.text for item in prompt.approved_evidence if item.evidence_id in evidence_ids))
    value = normalized(text)
    terms = [term for term in re.findall(r"[a-zA-Z][a-zA-Z+#.]{2,}", value) if term not in {"using", "with", "and", "for", "the"}]
    approved_terms = approved_technology_terms(prompt) | {normalized(item.name) for item in prompt.approved_capabilities}
    return bool(set(terms) & set(re.findall(r"[a-zA-Z][a-zA-Z+#.]{2,}", evidence_text))) or any(
        term in normalized(text) for term in approved_terms if len(term) > 1
    )


def repeated_opening(openings: list[str]) -> bool:
    return any(openings.count(opening) > 1 for opening in set(openings) if opening)


def trim_words(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text
    return " ".join(words[:limit]).rstrip(",.;") + "."


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = normalized(value)
        if key and key not in seen:
            seen.add(key)
            output.append(value)
    return output


def dedupe_issues(issues: list[ExperienceBulletValidationIssue]) -> list[ExperienceBulletValidationIssue]:
    seen: set[tuple[str, int | None]] = set()
    output: list[ExperienceBulletValidationIssue] = []
    for item in issues:
        key = (item.code, item.bullet_index)
        if key not in seen:
            seen.add(key)
            output.append(item)
    return output


__all__ = [
    "EXPERIENCE_WRITER_SYSTEM_PROMPT",
    "EXPERIENCE_INVALID_EVIDENCE_ID",
    "EXPERIENCE_INVALID_REQUIREMENT_ID",
    "EXPERIENCE_WRONG_ROLE",
    "EXPERIENCE_UNSUPPORTED_TECHNOLOGY",
    "EXPERIENCE_UNSUPPORTED_METRIC",
    "EXPERIENCE_UNSUPPORTED_LEADERSHIP",
    "EXPERIENCE_UNSUPPORTED_ARCHITECTURE",
    "EXPERIENCE_METADATA_LEAKAGE",
    "EXPERIENCE_EXCLUDED_TERM",
    "EXPERIENCE_TOO_LONG",
    "EXPERIENCE_DUPLICATE_BULLET",
    "EXPERIENCE_REPEATED_OPENING",
    "EXPERIENCE_GENERIC_FILLER",
    "EXPERIENCE_INSUFFICIENT_SUPPORT",
    "EXPERIENCE_BULLET_COUNT_MISMATCH",
    "call_experience_model",
    "experience_model_configuration_hash",
    "generate_experience_bullets",
    "generate_experience_intelligence",
    "validate_experience_bullets",
]
