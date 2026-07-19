from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SkillCategoryDefinition:
    category_id: str
    category_name: str
    group: str
    description: str
    examples: tuple[str, ...]
    order: int


SKILL_CATEGORY_REGISTRY: tuple[SkillCategoryDefinition, ...] = (
    SkillCategoryDefinition("programming-languages", "Programming Languages", "technical", "Programming, scripting, and query languages.", ("C#", "Java", "Python", "JavaScript", "SQL"), 1),
    SkillCategoryDefinition("backend-development", "Backend Development", "technical", "Server-side development technologies and runtime platforms.", (".NET", "ASP.NET Core", "Node.js", "Java", "Spring Boot"), 2),
    SkillCategoryDefinition("frontend-development", "Frontend Development", "technical", "Browser and user-interface technologies.", ("React", "Angular", "HTML5", "CSS3"), 3),
    SkillCategoryDefinition("frameworks-libraries", "Frameworks & Libraries", "technical", "Reusable software frameworks and development libraries.", ("Entity Framework", "LINQ", "Next.js", "Redux"), 4),
    SkillCategoryDefinition("databases", "Databases", "technical", "Relational, NoSQL, query, and database technologies.", ("SQL Server", "PostgreSQL", "MongoDB", "Oracle"), 5),
    SkillCategoryDefinition("cloud-platforms-services", "Cloud Platforms & Services", "technical", "Public cloud platforms and managed cloud services.", ("Azure", "AWS", "Google Cloud", "Azure App Service"), 6),
    SkillCategoryDefinition("devops-cicd-containers", "DevOps, CI/CD & Containers", "technical", "Build, delivery, automation, containerization, and deployment tools.", ("Jenkins", "Docker", "Kubernetes", "GitHub Actions"), 7),
    SkillCategoryDefinition("testing-quality-assurance", "Testing & Quality Assurance", "technical", "Unit testing, automated testing, quality, and code-analysis tools.", ("NUnit", "MSTest", "Jest", "SonarQube"), 8),
    SkillCategoryDefinition("apis-integration", "APIs & Integration", "technical", "API design, documentation, messaging, and system integration.", ("REST APIs", "Swagger", "Postman", "GraphQL"), 9),
    SkillCategoryDefinition("data-engineering-etl", "Data Engineering & ETL", "technical", "Data pipelines, orchestration, transformation, and ETL tools.", ("SSIS", "Airflow", "ETL", "Data pipelines"), 10),
    SkillCategoryDefinition("data-analytics-reporting", "Data Analytics & Reporting", "technical", "Business intelligence, reporting, visualization, and analytics tools.", ("SSRS", "Power BI", "Tableau", "Dashboards"), 11),
    SkillCategoryDefinition("ai-machine-learning-generative-ai", "AI, Machine Learning & Generative AI", "technical", "Machine learning, deep learning, LLM, and AI-development technologies.", ("LLMs", "OpenAI API", "TensorFlow", "Python ML"), 12),
    SkillCategoryDefinition("architecture-system-design", "Architecture & System Design", "technical", "Software architecture, distributed systems, and design practices.", ("System design", "Microservices", "Scalability", "OOP"), 13),
    SkillCategoryDefinition("security-identity", "Security & Identity", "technical", "Application security, authentication, authorization, and identity technologies.", ("OAuth", "JWT", "SSO", "Authorization"), 14),
    SkillCategoryDefinition("tools-development-environments", "Tools & Development Environments", "technical", "IDEs, development utilities, and engineering productivity tools.", ("Visual Studio", "Git", "Postman", "Swagger"), 15),
    SkillCategoryDefinition("software-development-practices", "Software Development Practices", "professional", "Code review, debugging, performance tuning, documentation, and engineering practices.", ("Code reviews", "Debugging", "Documentation", "Performance tuning"), 16),
    SkillCategoryDefinition("methodologies-ways-of-working", "Methodologies & Ways of Working", "professional", "Agile, Scrum, Kanban, DevOps culture, and delivery methodologies.", ("Agile", "Scrum", "Kanban", "SDLC"), 17),
    SkillCategoryDefinition("business-domain-knowledge", "Business & Domain Knowledge", "professional", "Industry-specific or business-process knowledge.", ("Healthcare workflows", "Compliance", "Claims", "Finance"), 18),
    SkillCategoryDefinition("communication-collaboration", "Communication & Collaboration", "professional", "Stakeholder communication, teamwork, facilitation, and collaboration skills.", ("Stakeholder communication", "Teamwork", "Facilitation"), 19),
    SkillCategoryDefinition("leadership-management", "Leadership & Management", "professional", "Mentoring, team leadership, planning, and people-management skills.", ("Mentoring", "Planning", "Technical leadership"), 20),
    SkillCategoryDefinition("languages", "Languages", "professional", "Spoken and written human languages.", ("English", "Spanish", "Hindi", "Telugu"), 21),
    SkillCategoryDefinition("other-specialized-skills", "Other Specialized Skills", "professional", "Relevant specialized skills that do not fit another available category.", ("Specialized platforms", "Niche tools", "Domain-specific systems"), 22),
)

STANDARD_SKILL_CATEGORIES = [category.category_name for category in SKILL_CATEGORY_REGISTRY]

CATEGORY_ALIASES: dict[str, str | None] = {
    "backend / .net": "backend-development",
    "backend /.net": "backend-development",
    ".net backend": "backend-development",
    "backend": "backend-development",
    "frontend": "frontend-development",
    "ui development": "frontend-development",
    "cloud": "cloud-platforms-services",
    "cloud technologies": "cloud-platforms-services",
    "devops & tools": "devops-cicd-containers",
    "devops": "devops-cicd-containers",
    "ci/cd": "devops-cicd-containers",
    "testing": "testing-quality-assurance",
    "unit testing": "testing-quality-assurance",
    "data & reporting": "data-analytics-reporting",
    "reporting": "data-analytics-reporting",
    "methodologies": "methodologies-ways-of-working",
    "agile methodologies": "methodologies-ways-of-working",
    "node / javascript": None,
    "node / js": None,
    "node.js": None,
}

CANONICAL_SKILLS = {
    "ms-test": "MSTest",
    "ms test": "MSTest",
    "mstest": "MSTest",
    "ms sql server": "Microsoft SQL Server",
    "microsoft sql server": "Microsoft SQL Server",
    "asp net core": "ASP.NET Core",
    "asp.net core": "ASP.NET Core",
    "node js": "Node.js",
    "node.js": "Node.js",
}


@dataclass(frozen=True)
class ParsedSkillCategory:
    category_id: str
    category_name: str
    order: int
    items: list[str]
    migration_review_required: bool = False
    legacy_unparsed: str = ""


@dataclass(frozen=True)
class ParsedSkills:
    categories: list[ParsedSkillCategory]
    requires_review: bool = False
    legacy_unparsed: str = ""


CATEGORY_BY_ID = {category.category_id: category for category in SKILL_CATEGORY_REGISTRY}
CATEGORY_BY_NAME = {category.category_name.casefold(): category for category in SKILL_CATEGORY_REGISTRY}
PREFIX_CATEGORY_NAMES = tuple([*STANDARD_SKILL_CATEGORIES, *CATEGORY_ALIASES.keys()])


def normalize_skill_name(value: str) -> str:
    cleaned = " ".join(str(value).strip().split())
    cleaned = re.sub(r"\s+/\s+", " / ", cleaned)
    return CANONICAL_SKILLS.get(cleaned.casefold(), cleaned)


def skill_category_id(category_name: str) -> str:
    definition = resolve_skill_category_definition(category_name)
    if definition:
        return definition.category_id
    slug = re.sub(r"[^a-z0-9]+", "-", category_name.strip().casefold()).strip("-")
    return slug or "skill-category"


def split_skill_values(value: str) -> list[str]:
    output: list[str] = []
    current: list[str] = []
    depth = 0
    for character in value:
        if character == "(":
            depth += 1
        elif character == ")" and depth > 0:
            depth -= 1
        if character == "," and depth == 0:
            output.append("".join(current))
            current = []
            continue
        current.append(character)
    output.append("".join(current))
    return dedupe_skills(output)


def has_category_prefix(value: str) -> bool:
    text = value.strip().casefold()
    return any(text.startswith(f"{category.casefold()}:") for category in PREFIX_CATEGORY_NAMES)


def parse_legacy_skill_text(value: str) -> ParsedSkills:
    raw = value.strip()
    if not raw:
        return ParsedSkills([])
    pattern = re.compile(r"(^|\n|,)\s*([^,\n:]{2,64})\s*:", re.IGNORECASE)
    matches = list(pattern.finditer(raw))
    if not matches:
        items = dedupe_skills(split_skill_values(raw))
        return ParsedSkills(
            [ParsedSkillCategory("technical-skills", "Technical Skills", 0, items, True, raw)] if items else [],
            requires_review=bool(raw),
            legacy_unparsed=raw,
        )
    legacy_unparsed = raw[: matches[0].start()].strip()
    categories: list[ParsedSkillCategory] = []
    for index, match in enumerate(matches):
        next_match = matches[index + 1] if index + 1 < len(matches) else None
        original_category = " ".join(match.group(2).strip().split())
        category_name = canonical_category_name(original_category)
        definition = resolve_skill_category_definition(original_category)
        needs_review = bool(
            legacy_unparsed
            or is_ambiguous_skill_category_alias(original_category)
            or not definition
            or original_category.casefold() != category_name.casefold()
        )
        content = raw[match.end() : next_match.start() if next_match else len(raw)].strip(" ,\n")
        items = [item for item in dedupe_skills(split_skill_values(content)) if not has_category_prefix(item)]
        if items:
            categories.append(
                ParsedSkillCategory(
                    category_id=skill_category_id(category_name),
                    category_name=category_name,
                    order=len(categories),
                    items=items,
                    migration_review_required=needs_review,
                    legacy_unparsed=legacy_unparsed,
                )
            )
    return ParsedSkills(categories, requires_review=bool(legacy_unparsed or any(category.migration_review_required for category in categories)), legacy_unparsed=legacy_unparsed)


def dedupe_skills(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        skill = normalize_skill_name(value)
        key = skill.casefold()
        if skill and key not in seen:
            output.append(skill)
            seen.add(key)
    return output


def canonical_category_name(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    definition = resolve_skill_category_definition(cleaned)
    if definition:
        return definition.category_name
    return cleaned


def normalize_category_key(value: str) -> str:
    return re.sub(r"\s+/\s+", " / ", " ".join(str(value).strip().split())).casefold()


def resolve_skill_category_definition(value: str) -> SkillCategoryDefinition | None:
    key = normalize_category_key(value)
    if key in CATEGORY_BY_ID:
        return CATEGORY_BY_ID[key]
    if key in CATEGORY_BY_NAME:
        return CATEGORY_BY_NAME[key]
    alias = CATEGORY_ALIASES.get(key)
    return CATEGORY_BY_ID.get(alias) if alias else None


def is_ambiguous_skill_category_alias(value: str) -> bool:
    return CATEGORY_ALIASES.get(normalize_category_key(value)) is None and normalize_category_key(value) in CATEGORY_ALIASES


def approved_skill_category_name(category_id: str) -> str | None:
    return CATEGORY_BY_ID.get(category_id.strip().casefold()).category_name if category_id.strip().casefold() in CATEGORY_BY_ID else None


def is_approved_skill_category_id(category_id: str) -> bool:
    return category_id.strip().casefold() in CATEGORY_BY_ID
