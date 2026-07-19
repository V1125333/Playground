from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SKILL_REGISTRY_CATEGORIES: tuple[str, ...] = (
    "Languages",
    "Frameworks",
    "Frontend",
    "Cloud Platforms",
    "Data Engineering",
    "Databases",
    "APIs & Integration",
    "DevOps & CI/CD",
    "Testing",
    "Architecture & Practices",
    "AI & Machine Learning",
    "Tools",
)
SKILL_REGISTRY_VERSION = "skill-registry-v1"

SkillNormalizationMatchType = Literal["exact", "alias", "normalized", "unknown"]
SkillMatchType = Literal["exact", "alias", "broader", "narrower", "related", "no_match"]
SkillMatchStrength = Literal["exact", "strong", "partial", "weak", "none"]


class SkillDefinition(BaseModel):
    """Canonical skill identity.

    Aliases identify the same skill. Parent, broader/narrower, and related
    concepts describe vocabulary relationships only; they do not prove a
    candidate used the related technology without later evidence checks.
    """

    canonical_name: str = Field(alias="canonicalName")
    normalized_value: str = Field(alias="normalizedValue")
    aliases: list[str] = Field(default_factory=list)
    category: str
    parent_concepts: list[str] = Field(default_factory=list, alias="parentConcepts")
    related_concepts: list[str] = Field(default_factory=list, alias="relatedConcepts")
    broader_than: list[str] = Field(default_factory=list, alias="broaderThan")
    narrower_than: list[str] = Field(default_factory=list, alias="narrowerThan")
    display_order: int = Field(alias="displayOrder")
    active: bool = True

    model_config = ConfigDict(populate_by_name=True)


class SkillNormalizationResult(BaseModel):
    original_value: str = Field(alias="originalValue")
    canonical_name: str | None = Field(default=None, alias="canonicalName")
    normalized_value: str = Field(alias="normalizedValue")
    match_type: SkillNormalizationMatchType = Field(alias="matchType")
    category: str | None = None
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class SkillMatchResult(BaseModel):
    candidate_skill: str = Field(alias="candidateSkill")
    requirement_skill: str = Field(alias="requirementSkill")
    candidate_canonical_name: str | None = Field(default=None, alias="candidateCanonicalName")
    requirement_canonical_name: str | None = Field(default=None, alias="requirementCanonicalName")
    match_type: SkillMatchType = Field(alias="matchType")
    strength: SkillMatchStrength
    allowed_for_evidence_support: bool = Field(alias="allowedForEvidenceSupport")
    reason: str

    model_config = ConfigDict(populate_by_name=True)


def skill_lookup_key(value: str) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"\(([^)]{1,24})\)", r" \1 ", text)
    text = text.replace("#", " sharp ")
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _skill(
    canonical_name: str,
    category: str,
    *,
    aliases: tuple[str, ...] = (),
    parent_concepts: tuple[str, ...] = (),
    related_concepts: tuple[str, ...] = (),
    broader_than: tuple[str, ...] = (),
    narrower_than: tuple[str, ...] = (),
    display_order: int,
    active: bool = True,
) -> SkillDefinition:
    return SkillDefinition(
        canonicalName=canonical_name,
        normalizedValue=skill_lookup_key(canonical_name),
        aliases=list(aliases),
        category=category,
        parentConcepts=list(parent_concepts),
        relatedConcepts=list(related_concepts),
        broaderThan=list(broader_than),
        narrowerThan=list(narrower_than),
        displayOrder=display_order,
        active=active,
    )


REGISTERED_SKILLS: tuple[SkillDefinition, ...] = (
    _skill("C#", "Languages", aliases=("c sharp", "c-sharp"), display_order=10),
    _skill("Python", "Languages", display_order=20),
    _skill("JavaScript", "Languages", aliases=("js", "ecmascript"), broader_than=("TypeScript",), display_order=30),
    _skill("TypeScript", "Languages", aliases=("ts",), narrower_than=("JavaScript",), display_order=40),
    _skill("Java", "Languages", display_order=50),
    _skill("SQL", "Languages", broader_than=("SQL Server", "PostgreSQL", "MySQL"), display_order=60),
    _skill(".NET", "Frameworks", aliases=("dotnet", "dot net", ".net core", "dotnet core"), broader_than=("ASP.NET Core", "ASP.NET MVC"), related_concepts=("C#",), display_order=100),
    _skill("ASP.NET Core", "Frameworks", aliases=("asp net core", "asp.net core web api"), parent_concepts=(".NET",), related_concepts=("REST APIs", "Web APIs"), narrower_than=(".NET",), display_order=110),
    _skill("ASP.NET MVC", "Frameworks", aliases=("asp net mvc", "mvc"), parent_concepts=(".NET",), narrower_than=(".NET",), display_order=120),
    _skill("FastAPI", "Frameworks", parent_concepts=("Python",), related_concepts=("REST APIs",), narrower_than=("Python",), display_order=130),
    _skill("Entity Framework", "Frameworks", aliases=("entity framework core", "ef core"), parent_concepts=(".NET",), display_order=140),
    _skill("LINQ", "Frameworks", parent_concepts=(".NET",), display_order=150),
    _skill("Spring Boot", "Frameworks", parent_concepts=("Java",), display_order=160),
    _skill("React", "Frontend", aliases=("react.js", "reactjs"), related_concepts=("JavaScript", "TypeScript"), display_order=200),
    _skill("Angular", "Frontend", display_order=210),
    _skill("Next.js", "Frontend", aliases=("nextjs", "next js"), related_concepts=("React",), display_order=220),
    _skill("HTML5", "Frontend", aliases=("html",), display_order=230),
    _skill("CSS3", "Frontend", aliases=("css",), display_order=240),
    _skill("Azure", "Cloud Platforms", aliases=("microsoft azure",), broader_than=("Azure Data Factory", "Azure Databricks", "Azure Data Lake", "Azure Synapse Analytics"), display_order=300),
    _skill("AWS", "Cloud Platforms", aliases=("amazon web services",), display_order=310),
    _skill("Google Cloud", "Cloud Platforms", aliases=("gcp",), display_order=320),
    _skill("Azure Data Factory", "Data Engineering", aliases=("adf", "azure datafactory", "azure data factory (adf)"), parent_concepts=("Azure", "ETL", "Data Pipelines"), narrower_than=("Azure", "ETL", "Data Pipelines"), display_order=400),
    _skill("Azure Databricks", "Data Engineering", aliases=("databricks",), parent_concepts=("Azure", "Apache Spark"), narrower_than=("Azure", "Apache Spark"), display_order=410),
    _skill("Apache Spark", "Data Engineering", aliases=("spark", "pyspark"), related_concepts=("Data Pipelines",), broader_than=("Azure Databricks",), display_order=420),
    _skill("ETL", "Data Engineering", broader_than=("Azure Data Factory", "Data Pipelines"), display_order=430),
    _skill("Data Pipelines", "Data Engineering", aliases=("data pipeline", "data pipelines"), related_concepts=("ETL",), display_order=440),
    _skill("Azure Data Lake", "Data Engineering", parent_concepts=("Azure",), narrower_than=("Azure",), display_order=450),
    _skill("Azure Synapse Analytics", "Data Engineering", aliases=("azure synapse", "synapse analytics"), parent_concepts=("Azure",), narrower_than=("Azure",), display_order=460),
    _skill("SSIS", "Data Engineering", display_order=470),
    _skill("SQL Server", "Databases", aliases=("microsoft sql server", "mssql", "ms sql server"), parent_concepts=("SQL",), narrower_than=("SQL",), display_order=500),
    _skill("PostgreSQL", "Databases", aliases=("postgres", "postgresql database"), parent_concepts=("SQL",), narrower_than=("SQL",), display_order=510),
    _skill("MySQL", "Databases", parent_concepts=("SQL",), narrower_than=("SQL",), display_order=520),
    _skill("MongoDB", "Databases", display_order=530),
    _skill("Oracle", "Databases", parent_concepts=("SQL",), narrower_than=("SQL",), display_order=540),
    _skill("REST APIs", "APIs & Integration", aliases=("restful api", "restful apis", "rest api", "rest services", "restful web api"), related_concepts=("Web APIs",), display_order=600),
    _skill("Web APIs", "APIs & Integration", aliases=("web api",), related_concepts=("REST APIs",), display_order=610),
    _skill("EDI", "APIs & Integration", display_order=620),
    _skill("Swagger", "APIs & Integration", aliases=("openapi", "open api"), related_concepts=("REST APIs",), display_order=630),
    _skill("Postman", "Tools", related_concepts=("REST APIs",), display_order=640),
    _skill("Azure DevOps", "DevOps & CI/CD", aliases=("ado", "azure pipelines"), parent_concepts=("CI/CD", "Azure"), display_order=700),
    _skill("Git", "DevOps & CI/CD", display_order=710),
    _skill("GitHub", "DevOps & CI/CD", aliases=("github",), parent_concepts=("Git",), display_order=720),
    _skill("Docker", "DevOps & CI/CD", display_order=730),
    _skill("Kubernetes", "DevOps & CI/CD", aliases=("k8s",), display_order=740),
    _skill("CI/CD", "DevOps & CI/CD", aliases=("continuous integration", "continuous delivery", "continuous deployment", "ci cd", "ci-cd"), broader_than=("Azure DevOps",), display_order=750),
    _skill("Jenkins", "DevOps & CI/CD", related_concepts=("CI/CD",), display_order=760),
    _skill("Unit Testing", "Testing", aliases=("unit tests",), display_order=800),
    _skill("Integration Testing", "Testing", aliases=("integration tests",), display_order=810),
    _skill("NUnit", "Testing", parent_concepts=("Unit Testing",), narrower_than=("Unit Testing",), display_order=820),
    _skill("MSTest", "Testing", aliases=("ms test", "ms-test"), parent_concepts=("Unit Testing",), narrower_than=("Unit Testing",), display_order=830),
    _skill("Jest", "Testing", parent_concepts=("Unit Testing",), narrower_than=("Unit Testing",), display_order=840),
    _skill("Jasmine", "Testing", parent_concepts=("Unit Testing",), narrower_than=("Unit Testing",), display_order=850),
    _skill("Object-Oriented Programming", "Architecture & Practices", aliases=("oop", "object oriented programming", "object-oriented design", "object oriented design"), display_order=900),
    _skill("SOLID", "Architecture & Practices", display_order=910),
    _skill("Microservices", "Architecture & Practices", aliases=("microservices architecture",), display_order=920),
    _skill("Agile", "Architecture & Practices", display_order=930),
    _skill("Scrum", "Architecture & Practices", parent_concepts=("Agile",), narrower_than=("Agile",), display_order=940),
    _skill("Software Development Life Cycle", "Architecture & Practices", aliases=("sdlc", "software development lifecycle"), display_order=950),
    _skill("Code Review", "Architecture & Practices", aliases=("code reviews", "peer code review", "peer code reviews"), display_order=960),
    _skill("Technical Leadership", "Architecture & Practices", aliases=("engineering leadership", "technical guidance"), display_order=970),
    _skill("Generative AI", "AI & Machine Learning", aliases=("gen ai", "genai"), display_order=1000),
    _skill("Large Language Models", "AI & Machine Learning", aliases=("llm", "llms", "large language model"), related_concepts=("Generative AI",), display_order=1010),
    _skill("Retrieval-Augmented Generation", "AI & Machine Learning", aliases=("rag", "retrieval augmented generation"), related_concepts=("Large Language Models", "LangChain"), display_order=1020),
    _skill("LangChain", "AI & Machine Learning", related_concepts=("Large Language Models", "Retrieval-Augmented Generation"), display_order=1030),
    _skill("Prompt Engineering", "AI & Machine Learning", related_concepts=("Large Language Models",), display_order=1040),
    _skill("AI Agents", "AI & Machine Learning", related_concepts=("Generative AI", "Large Language Models"), display_order=1050),
    _skill("Visual Studio", "Tools", display_order=1100),
    _skill("DBeaver", "Tools", display_order=1110),
    _skill("SonarQube", "Tools", display_order=1120),
    _skill("SSRS", "Tools", display_order=1130),
)


def normalize_skill_name(value: str) -> SkillNormalizationResult:
    original = str(value) if value is not None else ""
    normalized = skill_lookup_key(original)
    if not normalized:
        return SkillNormalizationResult(
            originalValue=original,
            canonicalName=None,
            normalizedValue="",
            matchType="unknown",
            category=None,
            warnings=["blank_skill"],
        )
    registry = _registry_maps()
    canonical = registry["canonical_by_key"].get(normalized)
    if canonical:
        definition = registry["definition_by_name"][canonical]
        match_type: SkillNormalizationMatchType = "exact" if " ".join(original.strip().split()).casefold() == definition.canonical_name.casefold() else "normalized"
        return SkillNormalizationResult(
            originalValue=original,
            canonicalName=definition.canonical_name,
            normalizedValue=normalized,
            matchType=match_type,
            category=definition.category,
            warnings=[],
        )
    alias = registry["alias_by_key"].get(normalized)
    if alias:
        definition = registry["definition_by_name"][alias]
        return SkillNormalizationResult(
            originalValue=original,
            canonicalName=definition.canonical_name,
            normalizedValue=normalized,
            matchType="alias",
            category=definition.category,
            warnings=[],
        )
    return SkillNormalizationResult(
        originalValue=original,
        canonicalName=None,
        normalizedValue=normalized,
        matchType="unknown",
        category=None,
        warnings=["unknown_skill"],
    )


def get_skill_definition(canonical_name: str) -> SkillDefinition | None:
    canonical = normalize_skill_name(canonical_name).canonical_name
    return _registry_maps()["definition_by_name"].get(canonical or "")


def get_skill_category(canonical_name: str) -> str | None:
    definition = get_skill_definition(canonical_name)
    return definition.category if definition else None


def resolve_skill_alias(value: str) -> str | None:
    result = normalize_skill_name(value)
    return result.canonical_name if result.match_type in {"alias", "exact", "normalized"} else None


def get_parent_concepts(canonical_name: str) -> list[str]:
    definition = get_skill_definition(canonical_name)
    return list(definition.parent_concepts) if definition else []


def get_related_concepts(canonical_name: str) -> list[str]:
    definition = get_skill_definition(canonical_name)
    return list(definition.related_concepts) if definition else []


def is_supported_directional_match(candidate_skill: str, requirement_skill: str) -> bool:
    return match_skills(candidate_skill, requirement_skill).allowed_for_evidence_support


def match_skills(candidate_skill: str, requirement_skill: str) -> SkillMatchResult:
    candidate = normalize_skill_name(candidate_skill)
    requirement = normalize_skill_name(requirement_skill)
    candidate_name = candidate.canonical_name
    requirement_name = requirement.canonical_name
    if not candidate_name or not requirement_name:
        return SkillMatchResult(
            candidateSkill=candidate_skill,
            requirementSkill=requirement_skill,
            candidateCanonicalName=candidate_name,
            requirementCanonicalName=requirement_name,
            matchType="no_match",
            strength="none",
            allowedForEvidenceSupport=False,
            reason="One or both skills are unknown to the canonical registry.",
        )
    if candidate_name == requirement_name:
        match_type: SkillMatchType = "exact" if candidate.match_type == "exact" and requirement.match_type == "exact" else "alias"
        return SkillMatchResult(
            candidateSkill=candidate_skill,
            requirementSkill=requirement_skill,
            candidateCanonicalName=candidate_name,
            requirementCanonicalName=requirement_name,
            matchType=match_type,
            strength="exact",
            allowedForEvidenceSupport=True,
            reason="Candidate skill and requirement resolve to the same canonical skill.",
        )
    candidate_definition = get_skill_definition(candidate_name)
    requirement_definition = get_skill_definition(requirement_name)
    assert candidate_definition is not None and requirement_definition is not None
    if requirement_name in candidate_definition.narrower_than or candidate_name in requirement_definition.broader_than:
        return SkillMatchResult(
            candidateSkill=candidate_skill,
            requirementSkill=requirement_skill,
            candidateCanonicalName=candidate_name,
            requirementCanonicalName=requirement_name,
            matchType="narrower",
            strength="strong",
            allowedForEvidenceSupport=True,
            reason=f"{candidate_name} is a narrower, more specific skill that can support the broader {requirement_name} requirement.",
        )
    if requirement_name in candidate_definition.broader_than or candidate_name in requirement_definition.narrower_than:
        return SkillMatchResult(
            candidateSkill=candidate_skill,
            requirementSkill=requirement_skill,
            candidateCanonicalName=candidate_name,
            requirementCanonicalName=requirement_name,
            matchType="broader",
            strength="partial",
            allowedForEvidenceSupport=False,
            reason=f"{candidate_name} is broader than {requirement_name}; it cannot prove the specific requirement by itself.",
        )
    if requirement_name in candidate_definition.related_concepts or candidate_name in requirement_definition.related_concepts:
        return SkillMatchResult(
            candidateSkill=candidate_skill,
            requirementSkill=requirement_skill,
            candidateCanonicalName=candidate_name,
            requirementCanonicalName=requirement_name,
            matchType="related",
            strength="weak",
            allowedForEvidenceSupport=False,
            reason="The skills are related vocabulary, but the relationship alone is not evidence support.",
        )
    return SkillMatchResult(
        candidateSkill=candidate_skill,
        requirementSkill=requirement_skill,
        candidateCanonicalName=candidate_name,
        requirementCanonicalName=requirement_name,
        matchType="no_match",
        strength="none",
        allowedForEvidenceSupport=False,
        reason="No registered exact, alias, hierarchy, or related relationship exists.",
    )


def list_registered_skills() -> list[SkillDefinition]:
    return sorted((item for item in REGISTERED_SKILLS if item.active), key=lambda item: (item.display_order, item.canonical_name))


def validate_skill_registry() -> list[str]:
    errors: list[str] = []
    canonical_keys: dict[str, str] = {}
    aliases: dict[str, str] = {}
    names = {definition.canonical_name for definition in REGISTERED_SKILLS}
    orders: list[int] = []
    for definition in REGISTERED_SKILLS:
        if definition.active and not definition.canonical_name.strip():
            errors.append("Active registry entries must have nonblank canonical names.")
        if definition.category not in SKILL_REGISTRY_CATEGORIES:
            errors.append(f"{definition.canonical_name} uses invalid category {definition.category}.")
        key = skill_lookup_key(definition.canonical_name)
        if key in canonical_keys:
            errors.append(f"Duplicate canonical normalized value {key}: {definition.canonical_name} and {canonical_keys[key]}.")
        canonical_keys[key] = definition.canonical_name
        if definition.normalized_value != key:
            errors.append(f"{definition.canonical_name} has incorrect normalizedValue {definition.normalized_value}.")
        orders.append(definition.display_order)
        for alias in definition.aliases:
            alias_key = skill_lookup_key(alias)
            if not alias_key:
                errors.append(f"{definition.canonical_name} has blank alias.")
                continue
            existing = aliases.get(alias_key)
            if existing and existing != definition.canonical_name:
                errors.append(f"Alias {alias} maps to both {existing} and {definition.canonical_name}.")
            aliases[alias_key] = definition.canonical_name
            canonical_owner = canonical_keys.get(alias_key)
            if canonical_owner and canonical_owner != definition.canonical_name:
                errors.append(f"Alias {alias} for {definition.canonical_name} conflicts with canonical skill {canonical_owner}.")
        relationships = [*definition.parent_concepts, *definition.related_concepts, *definition.broader_than, *definition.narrower_than]
        for relationship in relationships:
            if relationship not in names:
                errors.append(f"{definition.canonical_name} references unknown skill {relationship}.")
        overlap = set(definition.broader_than) & set(definition.narrower_than)
        if overlap:
            errors.append(f"{definition.canonical_name} has conflicting broader/narrower relationships: {', '.join(sorted(overlap))}.")
    if len({definition.canonical_name for definition in REGISTERED_SKILLS}) != len(REGISTERED_SKILLS):
        errors.append("Duplicate canonical names are not allowed.")
    if orders != sorted(orders) or len(set(orders)) != len(orders):
        errors.append("Display order must be unique and deterministic.")
    errors.extend(_cycle_errors("broaderThan", {definition.canonical_name: definition.broader_than for definition in REGISTERED_SKILLS}))
    errors.extend(_cycle_errors("narrowerThan", {definition.canonical_name: definition.narrower_than for definition in REGISTERED_SKILLS}))
    return errors


@lru_cache(maxsize=1)
def _registry_maps() -> dict[str, dict[str, str] | dict[str, SkillDefinition]]:
    errors = validate_skill_registry()
    if errors:
        raise RuntimeError("Invalid skill registry: " + "; ".join(errors))
    definition_by_name = {definition.canonical_name: definition for definition in REGISTERED_SKILLS}
    canonical_by_key = {definition.normalized_value: definition.canonical_name for definition in REGISTERED_SKILLS}
    alias_by_key: dict[str, str] = {}
    for definition in REGISTERED_SKILLS:
        for alias in definition.aliases:
            alias_by_key[skill_lookup_key(alias)] = definition.canonical_name
    return {
        "definition_by_name": definition_by_name,
        "canonical_by_key": canonical_by_key,
        "alias_by_key": alias_by_key,
    }


def _cycle_errors(label: str, graph: dict[str, list[str]]) -> list[str]:
    errors: list[str] = []

    def visit(node: str, path: tuple[str, ...]) -> None:
        if node in path:
            errors.append(f"Circular {label} relationship: {' -> '.join([*path, node])}.")
            return
        for child in graph.get(node, []):
            visit(child, (*path, node))

    for name in graph:
        visit(name, ())
    return sorted(set(errors))


__all__ = [
    "SKILL_REGISTRY_VERSION",
    "SKILL_REGISTRY_CATEGORIES",
    "SkillDefinition",
    "SkillNormalizationResult",
    "SkillMatchResult",
    "normalize_skill_name",
    "get_skill_definition",
    "get_skill_category",
    "resolve_skill_alias",
    "get_parent_concepts",
    "get_related_concepts",
    "is_supported_directional_match",
    "match_skills",
    "list_registered_skills",
    "validate_skill_registry",
    "skill_lookup_key",
]
