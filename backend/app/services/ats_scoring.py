import re
from dataclasses import dataclass

from app.schemas.resume import AtsBreakdown, GenerateResumeRequest, ResumeContent, ResumeSuggestion
from app.services.semantic_requirements import semantic_aliases_for_keyword, semantic_terms_for_job


STOPWORDS = {
    "a",
    "about",
    "across",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "all",
    "of",
    "on",
    "or",
    "other",
    "our",
    "that",
    "the",
    "their",
    "this",
    "to",
    "using",
    "with",
    "you",
    "your",
}

JOB_POSTING_NOISE = {
    "ability",
    "applicant",
    "candidate",
    "company",
    "develop",
    "developed",
    "build",
    "ensure",
    "degree",
    "description",
    "duties",
    "employee",
    "employment",
    "environment",
    "excellent",
    "expert",
    "expertise",
    "experience",
    "framework",
    "frameworks",
    "highly",
    "including",
    "job",
    "knowledge",
    "maintain",
    "mastery",
    "minimum",
    "more",
    "must",
    "need",
    "preferred",
    "proficiency",
    "qualification",
    "qualifications",
    "requiring",
    "required",
    "requirement",
    "requirements",
    "responsible",
    "responsibilities",
    "responsibility",
    "role",
    "skills",
    "team",
    "work",
    "years",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
}

GENERIC_KEYWORD_PHRASES = {
    "all the audit",
    "computer engineering",
    "computer engineering fundamentals",
    "data development",
    "delivery dates",
    "existing code",
    "software development",
    "application development",
    "database sql",
    "data engineer",
    "ensure compliance",
    "technical skills",
    "problem solving",
    "communication skills",
    "team player",
    "good judgment",
    "fast-paced environment",
    "perform other duties",
}

LEADING_TERM_NOISE = (
    "expert-level",
    "expert level",
    "advanced",
    "highly advanced",
    "thorough",
    "strong",
    "solid",
    "basic to",
    "knowledge of",
    "knowledge in",
    "experience with",
    "experience in",
    "understanding of",
    "proficiency of",
    "proficiency in",
)

FORCED_COVERAGE_TERMS = (
    ("SDLC", ("sdlc", "software development life cycle"), 3.6),
    ("code review", ("code review", "code reviews", "review code", "peer review", "pull request review"), 3.6),
    ("design review", ("design review", "design reviews", "review design"), 3.6),
    ("testing", ("testing", "test plans", "unit testing", "regression testing", "automated testing"), 3.0),
    ("technical documentation", ("technical documentation", "technical documents", "document technical", "documentation"), 3.6),
    ("technical specifications", ("technical specifications", "technical specification", "specifications"), 3.6),
    ("CI/CD", ("ci/cd", "ci cd", "continuous integration", "continuous delivery", "continuous deployment"), 3.2),
    ("release management", ("release management", "release planning", "deployment planning", "release readiness"), 3.2),
    ("Agile/Scrum", ("agile", "scrum", "agile/scrum"), 3.2),
    ("security", ("security", "secure", "secure application", "application security"), 3.2),
    ("audit", ("audit", "audits"), 3.1),
    ("regulatory compliance", ("regulatory compliance", "industry compliance", "compliance"), 3.6),
    ("engineering leadership", ("engineering leadership", "technical leadership"), 3.6),
    ("mentorship", ("mentorship", "mentoring", "mentor"), 3.4),
    ("lead delivery", ("lead delivery", "delivery lead", "leading delivery"), 3.4),
    ("collaborate with architects", ("collaborate with architects", "collaboration with architects", "architects"), 3.2),
    ("subject matter expert", ("subject matter expert", "sme"), 3.4),
)

HIGH_VALUE_STANDALONE_TERMS = {
    "security",
    "audit",
    "sdlc",
    "testing",
    "mentorship",
    "architecture",
}

TITLE_EQUIVALENTS = {
    "engineer": {"engineer", "engineering", "developer", "development"},
    "developer": {"developer", "development", "engineer", "engineering"},
    "software": {"software", "application", "applications", "system", "systems"},
    "full": {"full", "full-stack", "fullstack"},
    "stack": {"stack", "full-stack", "fullstack"},
    "senior": {"senior", "lead", "principal", "iv"},
}

TECH_ALIASES = {
    ".net": [".net", "dotnet", "dot net"],
    "accessibility": ["accessibility", "accessible", "wcag"],
    "agile scrum": ["agile scrum", "agile", "scrum"],
    "angular": ["angular", "angular.js", "angularjs"],
    "api development": ["api development", "api design", "api integration"],
    "asp.net identity": ["asp.net identity", "asp net identity", "aspnet identity"],
    "asp.net core": ["asp.net core", "asp net core", "aspnet core"],
    "asp.net mvc": ["asp.net mvc", "asp net mvc", "aspnet mvc"],
    "airflow": ["airflow", "apache airflow"],
    "aws": ["aws", "amazon web services"],
    "aws glue": ["aws glue", "glue"],
    "azure": ["azure", "microsoft azure"],
    "azure devops": ["azure devops", "azure pipelines"],
    "ci/cd": ["ci/cd", "ci cd", "continuous integration", "continuous delivery", "continuous deployment"],
    "c#": ["c#", "c sharp"],
    "computer engineering": [
        "computer engineering",
        "computer engineering fundamentals",
        "software engineering fundamentals",
        "object-oriented design",
        "object oriented design",
        "data structures",
        "algorithms",
        "scalable application design",
    ],
    "css": ["css", "css3"],
    "cybersecurity": ["cybersecurity", "cyber security"],
    "data warehousing": ["data warehousing", "data warehouse"],
    "dbt": ["dbt"],
    "design patterns": ["design patterns"],
    "docker": ["docker"],
    "entity framework": ["entity framework", "ef core"],
    "etl": ["etl", "etl pipelines"],
    "git": ["git"],
    "github": ["github"],
    "github actions": ["github actions"],
    "gitlab": ["gitlab", "git lab"],
    "google cloud": ["google cloud", "gcp"],
    "graphql": ["graphql", "graph ql"],
    "html": ["html", "html5"],
    "javascript": ["javascript", "java script", "js"],
    "jasmine": ["jasmine"],
    "jenkins": ["jenkins"],
    "jest": ["jest"],
    "jquery": ["jquery", "j query"],
    "kubernetes": ["kubernetes", "k8s"],
    "linq": ["linq"],
    "microservices": ["microservices", "micro services"],
    "mongodb": ["mongodb", "mongo db"],
    "mvc": ["mvc"],
    "ms-test": ["ms-test", "mstest", "ms test"],
    "ms sql server": ["ms sql server", "sql server", "mssql", "t-sql", "tsql"],
    "mysql": ["mysql", "my sql"],
    "next.js": ["next.js", "next js", "nextjs"],
    "node.js": ["node.js", "node js", "node"],
    "nunit": ["nunit", "n unit"],
    "object-oriented design": ["object-oriented design", "object oriented design", "oop", "object oriented programming"],
    "oauth": ["oauth", "oauth 2.0"],
    "oracle": ["oracle"],
    "postgresql": ["postgresql", "postgres"],
    "postman": ["postman"],
    "python": ["python"],
    "react": ["react", "react.js", "reactjs"],
    "rest api": ["rest api", "restful api", "restful"],
    "software development": ["software development", "application development", "software engineering", "enterprise application development"],
    "ssis": ["ssis", "sql server integration services"],
    "ssrs": ["ssrs", "sql server reporting services"],
    "sonarqube": ["sonarqube", "sonar qube"],
    "snowflake": ["snowflake"],
    "spark": ["spark", "apache spark"],
    "storybook": ["storybook"],
    "swagger": ["swagger", "openapi", "open api"],
    "system design": ["system design", "systems design"],
    "tfs": ["tfs", "team foundation server"],
    "typescript": ["typescript", "type script", "ts"],
    "unit testing": ["unit testing", "unit tests", "automated testing"],
    "visual studio": ["visual studio", "vs code", "visual studio code"],
    "wcag": ["wcag", "accessibility", "accessible"],
}

ACTION_VERBS = {
    "architected",
    "authored",
    "automated",
    "built",
    "configured",
    "created",
    "delivered",
    "designed",
    "developed",
    "enhanced",
    "established",
    "implemented",
    "improved",
    "integrated",
    "led",
    "maintained",
    "managed",
    "mentored",
    "optimized",
    "partnered",
    "reduced",
    "resolved",
    "reviewed",
    "streamlined",
    "troubleshot",
}


@dataclass(frozen=True)
class KeywordMatch:
    keyword: str
    weight: float
    matched: bool


@dataclass(frozen=True)
class RoleInference:
    role_type: str
    seniority: str
    core_stack: tuple[str, ...]
    domain: str | None = None


@dataclass(frozen=True)
class AtsScoreResult:
    score: int
    breakdown: AtsBreakdown
    suggestions: list[ResumeSuggestion]


def score_resume(resume: ResumeContent, payload: GenerateResumeRequest) -> AtsScoreResult:
    job_text = payload.job_description or ""
    resume_text = resume_to_text(resume)
    keyword_matches = score_keywords(job_text, resume_text)
    keyword_score = weighted_keyword_score(keyword_matches)
    formatting_score = score_formatting(resume)
    readability_score = score_readability(resume)
    title_score = score_title_match(resume, payload.target_role, job_text)
    skills_score = score_skill_coverage(resume, keyword_matches)

    overall = round(
        keyword_score * 0.42
        + title_score * 0.16
        + skills_score * 0.14
        + formatting_score * 0.16
        + readability_score * 0.12
    )
    overall = clamp(overall)

    matched_keywords = [item.keyword for item in keyword_matches if item.matched][:24]
    missing_keywords = [item.keyword for item in keyword_matches if not item.matched][:16]

    return AtsScoreResult(
        score=overall,
        breakdown=AtsBreakdown(
            keywordMatch=keyword_score,
            formatting=formatting_score,
            readability=readability_score,
            matchedKeywords=matched_keywords,
            missingKeywords=missing_keywords,
        ),
        suggestions=build_suggestions(
            resume=resume,
            payload=payload,
            keyword_score=keyword_score,
            formatting_score=formatting_score,
            readability_score=readability_score,
            title_score=title_score,
            missing_keywords=missing_keywords,
        ),
    )


def score_keywords(job_description: str, resume_text: str) -> list[KeywordMatch]:
    normalized_resume = normalize_text(resume_text)
    keywords = extract_job_keywords(job_description)

    matches: list[KeywordMatch] = []
    for keyword, weight in keywords:
        aliases = keyword_match_aliases(keyword)
        matched = any(contains_phrase(normalized_resume, alias) for alias in aliases)
        matches.append(KeywordMatch(keyword=display_keyword(keyword), weight=weight, matched=matched))

    return matches


def extract_job_keywords(job_description: str) -> list[tuple[str, float]]:
    if not job_description.strip():
        return []

    role_inference = infer_role_context(job_description)
    candidates: dict[str, tuple[str, float]] = {}
    raw_sentences = split_requirement_sentences(job_description)
    normalized_document = normalize_text(job_description)

    for sentence in raw_sentences:
        sentence_terms = extract_terms_from_sentence(sentence)
        for term in sentence_terms:
            cleaned = clean_extracted_term(term)
            if not cleaned:
                continue
            key = normalize_keyword_key(cleaned)
            if not key or is_generic_keyword(cleaned):
                continue
            weight = score_extracted_term(cleaned, sentence, normalized_document, role_inference)
            previous = candidates.get(key)
            if not previous or weight > previous[1]:
                candidates[key] = (cleaned, weight)

    add_core_stack_terms(candidates, role_inference, normalized_document)
    add_forced_coverage_terms(candidates, normalized_document)
    add_semantic_terms(candidates, job_description)
    ordered = prune_extracted_keywords(list(candidates.values()))
    ordered = ensure_forced_terms_survive_cap(ordered, normalized_document)
    return ordered[:28]


def weighted_keyword_score(matches: list[KeywordMatch]) -> int:
    if not matches:
        return 0

    total = sum(item.weight for item in matches)
    matched = sum(item.weight for item in matches if item.matched)
    return clamp(round((matched / total) * 100))


def infer_role_context(job_description: str) -> RoleInference:
    text = normalize_text(job_description)
    titleish = infer_role_phrase(job_description)
    seniority = infer_seniority(text, titleish)
    core_stack = tuple(infer_core_stack(job_description, titleish))
    role_type = build_role_type(titleish, core_stack, text)
    domain = infer_domain_from_jd(text)
    return RoleInference(role_type=role_type, seniority=seniority, core_stack=core_stack, domain=domain)


def infer_role_phrase(job_description: str) -> str:
    lines = [line.strip(" -:") for line in job_description.splitlines() if line.strip()]
    for line in lines[:4]:
        if re.search(r"(?i)\b(engineer|developer|architect|manager|analyst|specialist|consultant|administrator|nurse|product)\b", line):
            return clean_role_phrase(line)
    match = re.search(
        r"(?i)\b(?:role|position|title|opening|hiring)\s*(?:is|:|for)?\s*(?:a|an)?\s*([A-Za-z0-9+#./() -]{4,90})",
        job_description,
    )
    if match:
        return clean_role_phrase(match.group(1))
    match = re.search(
        r"(?i)\b([A-Za-z0-9+#./() -]{0,50}(?:engineer|developer|architect|manager|analyst|specialist|consultant|administrator|nurse)[A-Za-z0-9+#./() -]{0,40})",
        job_description,
    )
    return clean_role_phrase(match.group(1)) if match else ""


def clean_role_phrase(value: str) -> str:
    cleaned = re.sub(r"(?i)\b(?:job description|summary|requirements|responsibilities)\b.*$", "", value)
    cleaned = re.sub(r"(?i)\b(?:responsible for|must|will|should|requires|required)\b.*$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;-")
    return cleaned[:90]


def infer_seniority(text: str, role_phrase: str = "") -> str:
    role_text = normalize_text(role_phrase)
    if any(term in role_text for term in ("director", "head of", "manager", "management", "people manager")):
        return "management"
    if any(
        term in text
        for term in (
            "senior",
            "lead",
            "principal",
            "staff",
            "expert-level",
            "expert level",
            "subject matter expert",
            "mentor",
            "mentorship",
            "architects",
            "level iv",
            "engineer iv",
            "ten years",
            "10 years",
        )
    ):
        return "senior_lead"
    if any(term in text for term in ("junior", "entry level", "entry-level", "associate", "intern")):
        return "junior"
    return "mid"


def infer_core_stack(job_description: str, role_phrase: str) -> list[str]:
    source = f"{role_phrase}\n{job_description}"
    terms: list[str] = []
    normalized_source = normalize_text(source)

    for canonical, aliases in TECH_ALIASES.items():
        if canonical in {"computer engineering", "software development", "object-oriented design"}:
            continue
        if not any(contains_phrase(normalized_source, alias) for alias in aliases):
            continue
        display = display_keyword(canonical)
        if clean_core_stack_term(display) and not is_generic_keyword(display):
            terms.append(display)

    for raw_term in extract_title_stack_terms(role_phrase):
        cleaned = clean_extracted_term(raw_term)
        if cleaned and is_core_stack_term(cleaned) and role_core_term_present(cleaned, source):
            terms.append(cleaned)

    for term in extract_requirement_clause_terms(source) + extract_compound_terms(source):
        cleaned = clean_extracted_term(term)
        if cleaned and is_core_stack_term(cleaned) and role_core_term_present(cleaned, source):
            terms.append(cleaned)

    normalized_terms = {normalize_keyword_key(term) for term in terms}
    if ".net" in normalized_terms and "c#" not in normalized_terms and re.search(r"(?i)\b(engineer|developer|software|full[- ]stack)\b", source):
        terms.append("C#")

    return dedupe_terms([term for term in terms if clean_core_stack_term(term)])


def extract_title_stack_terms(role_phrase: str) -> list[str]:
    terms: list[str] = []
    for parenthetical in re.findall(r"\(([^)]+)\)", role_phrase):
        terms.extend(split_term_list(parenthetical))
    terms.extend(re.findall(r"(?i)\bfull[- ]stack\b|\bfront[- ]end\b|\bback[- ]end\b|\.net|c#|c\+\+|f#", role_phrase))
    return terms


def role_core_term_present(term: str, source: str) -> bool:
    normalized_source = normalize_text(source)
    return any(contains_phrase(normalized_source, alias) for alias in keyword_match_aliases(term))


def is_core_stack_term(term: str) -> bool:
    key = normalize_keyword_key(term)
    if is_generic_keyword(term) or is_rejected_fragment(term):
        return False
    if not clean_core_stack_term(term):
        return False
    if re.search(r"[+#./-]|[A-Z]{2,}", term):
        return True
    return any(
        signal in key
        for signal in (
            "full-stack",
            "front-end",
            "back-end",
            "api",
            "cloud",
            "database",
            "sql",
            "data structures",
            "algorithms",
            "architecture",
        )
    )


def clean_core_stack_term(term: str) -> bool:
    key = normalize_keyword_key(term)
    if not key:
        return False
    if "." in key and key not in {".net", "asp.net", "asp.net core", "asp.net mvc", "node.js", "next.js"}:
        return False
    if key in {"iv", "i", "ii", "iii", "v", "engineer", "developer", "software engineer", "data engineer", "engineer iv", "software engineer iv"}:
        return False
    if any(role_word in key for role_word in (" engineer", " developer", " manager", " analyst", " specialist")):
        return False
    if any(noise in key for noise in ("expert", "thorough", "responsibil", "statement", "matter expert", "languages.")):
        return False
    return True


def build_role_type(role_phrase: str, core_stack: tuple[str, ...], text: str) -> str:
    role = normalize_text(role_phrase)
    if not role:
        if "data engineer" in text or ("pipeline" in text and "data" in text):
            role = "data engineer"
        elif "product manager" in text:
            role = "product manager"
        elif "engineer" in text:
            role = "software engineer"
        elif "developer" in text:
            role = "software developer"
        else:
            role = "target role"
    if role:
        return role
    stack = " ".join(core_stack[:3])
    return " ".join(part for part in (stack, role) if part).strip()


def infer_domain_from_jd(text: str) -> str | None:
    domain_markers = {
        "healthcare": ("healthcare", "provider", "payer", "claims", "clinical"),
        "financial/compliance": ("fintech", "banking", "financial", "aml", "audit", "regulatory compliance"),
        "data/analytics": ("analytics", "data warehouse", "lineage", "data quality"),
        "security/compliance": ("security", "cybersecurity", "compliance", "risk"),
    }
    for domain, markers in domain_markers.items():
        if any(marker in text for marker in markers):
            return domain
    return None


def add_core_stack_terms(
    candidates: dict[str, tuple[str, float]],
    role_inference: RoleInference,
    normalized_document: str,
) -> None:
    for term in role_inference.core_stack:
        if not is_term_grounded_in_jd(term, normalized_document, role_inference):
            continue
        cleaned = clean_extracted_term(term)
        if not cleaned:
            continue
        key = normalize_keyword_key(cleaned)
        previous = candidates.get(key)
        if not previous or 4.0 >= previous[1]:
            candidates[key] = (cleaned, 4.0)


def is_term_grounded_in_jd(term: str, normalized_document: str, role_inference: RoleInference) -> bool:
    if any(contains_phrase(normalized_document, alias) for alias in keyword_match_aliases(term)):
        return True
    key = normalize_keyword_key(term)
    if key == "c#" and any(contains_phrase(normalized_document, alias) for alias in keyword_match_aliases(".NET")):
        return True
    return False


def dedupe_terms(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized_item = normalize_term_display(item)
        key = normalize_keyword_key(normalized_item)
        if key and key not in seen:
            seen.add(key)
            result.append(normalized_item)
    return result


def add_forced_coverage_terms(
    candidates: dict[str, tuple[str, float]],
    normalized_document: str,
) -> None:
    for term, aliases, weight in FORCED_COVERAGE_TERMS:
        if not any(contains_phrase(normalized_document, alias) for alias in aliases):
            continue
        cleaned = clean_extracted_term(term)
        if not cleaned:
            continue
        key = normalize_keyword_key(cleaned)
        previous = candidates.get(key)
        if not previous or weight > previous[1]:
            candidates[key] = (cleaned, weight)


def ensure_forced_terms_survive_cap(
    ordered: list[tuple[str, float]],
    normalized_document: str,
) -> list[tuple[str, float]]:
    result = list(ordered)
    present = {normalize_keyword_key(term) for term, _weight in result}
    priority_terms = [
        item
        for item in FORCED_COVERAGE_TERMS
        if normalize_keyword_key(item[0])
        in {
            "security",
            "regulatory compliance",
            "technical specifications",
            "code review",
            "sdlc",
            "mentorship",
            "subject matter expert",
        }
    ]
    remaining_terms = [item for item in FORCED_COVERAGE_TERMS if item not in priority_terms]
    priority_keys = {normalize_keyword_key(item[0]) for item in priority_terms}
    for term, aliases, weight in [*priority_terms, *remaining_terms]:
        key = normalize_keyword_key(term)
        if key in present:
            continue
        if not any(contains_phrase(normalized_document, alias) for alias in aliases):
            continue
        if len(result) < 28:
            result.append((term, weight))
            present.add(key)
            continue
        removable_index = next(
            (
                index
                for index in range(len(result) - 1, -1, -1)
                if normalize_keyword_key(result[index][0]) not in HIGH_VALUE_STANDALONE_TERMS
                and normalize_keyword_key(result[index][0]) not in {normalize_keyword_key(item[0]) for item in FORCED_COVERAGE_TERMS}
            ),
            -1,
        )
        if removable_index >= 0:
            result[removable_index] = (term, weight)
            present.add(key)
    return sorted(
        result,
        key=lambda item: (
            0 if normalize_keyword_key(item[0]) in priority_keys else 1,
            -item[1],
            item[0].lower(),
        ),
    )


def add_semantic_terms(candidates: dict[str, tuple[str, float]], job_description: str) -> None:
    for term, weight in semantic_terms_for_job(job_description):
        cleaned = clean_extracted_term(term)
        if not cleaned or is_generic_keyword(cleaned):
            continue
        key = normalize_keyword_key(cleaned)
        previous = candidates.get(key)
        if not previous or weight > previous[1]:
            candidates[key] = (cleaned, weight)


def split_requirement_sentences(job_description: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"[\n.;]+", job_description)
        if len(sentence.strip()) >= 4
    ]


def extract_terms_from_sentence(sentence: str) -> list[str]:
    terms: list[str] = []
    terms.extend(extract_requirement_clause_terms(sentence))
    terms.extend(extract_symbol_and_acronym_terms(sentence))
    terms.extend(extract_compound_terms(sentence))
    return terms


def extract_requirement_clause_terms(sentence: str) -> list[str]:
    terms: list[str] = []
    pattern = re.compile(
        r"(?i)\b(?:proficiency|experience|knowledge|understanding|skills?|expertise|ability)\b"
        r"(?:\s+(?:of|in|with|to|for))?\s+([^.;:]+)"
    )
    for match in pattern.finditer(sentence):
        clause = match.group(1)
        clause = re.sub(r"(?i)\b(?:according to|consistent with|including)\b.*$", "", clause).strip()
        terms.extend(split_term_list(clause))
    for match in re.finditer(r"(?i)\b(?:with|using)\s+([^.;:]+)", sentence):
        terms.extend(split_term_list(match.group(1)))
    return terms


def extract_symbol_and_acronym_terms(sentence: str) -> list[str]:
    terms: list[str] = []
    for match in re.finditer(r"(?<!\w)([A-Za-z]+(?:[+#]|\.[A-Za-z0-9]+)+|[A-Z]{2,}(?:/[A-Z]{2,})?)", sentence):
        terms.append(match.group(1))
    for match in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b", sentence):
        value = match.group(1)
        if is_requirement_context(tokenize(normalize_text(sentence)), 0) or re.search(r"(?i)\bpreferred|required|cloud|platform|tool\b", sentence):
            terms.append(value)
    return terms


def extract_compound_terms(sentence: str) -> list[str]:
    terms: list[str] = []
    text = sentence.strip()
    for match in re.finditer(r"\b([A-Za-z]+(?:-[A-Za-z]+)+(?:\s+[A-Za-z]+){0,2})\b", text):
        terms.append(match.group(1))
    for chunk in split_term_list(text):
        tokens = re.findall(r"[A-Za-z0-9+#./-]+", chunk)
        for size in (3, 2):
            for index in range(0, max(0, len(tokens) - size + 1)):
                phrase_tokens = tokens[index : index + size]
                if not valid_ngram_tokens(phrase_tokens):
                    continue
                phrase = " ".join(phrase_tokens)
                cleaned = clean_extracted_term(phrase)
                if cleaned and phrase_has_signal(cleaned):
                    terms.append(cleaned)
    return terms


def split_term_list(value: str) -> list[str]:
    normalized = re.sub(r"(?i)\b(?:and|or)\b", ",", value)
    return [item.strip() for item in re.split(r"[,/]", normalized) if item.strip()]


def clean_extracted_term(value: str) -> str:
    cleaned = " ".join(value.replace("â€™", "'").split()).strip(" ,:-")
    if not cleaned:
        return ""
    cleaned = re.sub(r"(?i)^(?:and|or|with|for|in|of|to|must)\s+", "", cleaned).strip()
    cleaned = re.sub(r"(?i)\s+(?:and|or|with|for|in|of|to)$", "", cleaned).strip()
    cleaned = normalize_fragment_phrase(cleaned)
    cleaned = re.sub(r"(?i)^(?:mentor|review|document|partner|build|building|create|creation|modify|write|ensure|ensures|ensuring|own|operate)\s+", "", cleaned).strip()
    cleaned = re.sub(r"(?i)\b(?:two|three|four|five|\d+)\s+or\s+more\s+", "", cleaned)
    cleaned = re.sub(r"(?i)^more\s+", "", cleaned).strip()
    cleaned = re.sub(r"(?i)\b(?:basic\s+to\s+)?highly\s+advanced\s+", "", cleaned)
    cleaned = re.sub(r"(?i)\s+highly\s+preferred$", "", cleaned).strip()
    cleaned = re.sub(r"(?i)\s+preferred$", "", cleaned).strip()
    cleaned = re.sub(r"(?i)\s+responsibilities$", "", cleaned).strip()
    cleaned = re.sub(r"(?i)^coding\s+in\s+a\s+", "", cleaned).strip()
    for prefix in LEADING_TERM_NOISE:
        cleaned = re.sub(rf"(?i)^{re.escape(prefix)}\s+", "", cleaned).strip()
    cleaned = re.sub(r"(?i)\s+(?:according to|consistent with|as assigned).*$", "", cleaned).strip()
    cleaned = re.sub(r"(?i)\b(?:best practices|standards)\b$", "", cleaned).strip(" ,:-")
    if not cleaned:
        return ""
    cleaned = normalize_term_display(cleaned)
    words = tokenize(normalize_text(cleaned))
    if len(words) > 5:
        return ""
    if not words or all(word in STOPWORDS or word in JOB_POSTING_NOISE for word in words):
        return ""
    if is_rejected_fragment(cleaned):
        return ""
    return cleaned


def normalize_fragment_phrase(value: str) -> str:
    key = normalize_keyword_key(value)
    replacements = {
        "all the audit": "audit",
        "all audit": "audit",
        "ensure compliance": "compliance",
        "ensures compliance": "compliance",
        "maintain compliance": "compliance",
        "modify existing code": "code maintenance",
        "existing code": "",
        "delivery dates": "",
        "data development": "data architecture",
        "data development architecture": "data architecture",
        "data development and architecture": "data architecture",
    }
    return replacements.get(key, value)


def is_rejected_fragment(value: str) -> bool:
    key = normalize_keyword_key(value)
    words = tokenize(key)
    if not words:
        return True
    number_words = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"}
    bare_verbs = {"ensure", "build", "develop", "maintain", "modify", "write", "review", "document", "own", "operate"}
    bare_nouns = {"skills", "skill", "mastery", "expertise", "proficiency", "knowledge", "responsibilities", "engineers"}
    if len(words) == 1 and (
        words[0].isdigit() or words[0] in number_words or words[0] in bare_verbs or words[0] in bare_nouns
    ):
        return True
    if key.startswith(("all the ", "all ")):
        return True
    if key in GENERIC_KEYWORD_PHRASES:
        return True
    return False


def valid_ngram_tokens(tokens: list[str]) -> bool:
    if not tokens:
        return False
    normalized = [normalize_text(token).strip(".,:;") for token in tokens]
    if normalized[0] in STOPWORDS or normalized[-1] in STOPWORDS:
        return False
    if normalized[0] in JOB_POSTING_NOISE or normalized[-1] in JOB_POSTING_NOISE:
        return False
    if normalized[0] in {"build", "built", "develop", "ensure", "maintain", "modify", "operate", "own", "write"}:
        return False
    if any(token in {"and", "or", "must", "with", "for", "including"} for token in normalized):
        return False
    return True


def normalize_term_display(value: str) -> str:
    text = value.strip()
    lower = normalize_text(text)
    replacements = {
        "c sharp": "C#",
        "net": ".NET",
        ".net": ".NET",
        "dot net": ".NET",
        "front end": "front-end",
        "back end": "back-end",
        "full stack": "full-stack",
        "restful api": "RESTful API",
        "rest api": "REST API",
        "api": "API",
        "sql": "SQL",
        "sdlc": "SDLC",
        "agile scrum": "Agile/Scrum",
        "aws glue": "AWS Glue",
        "dbt": "dbt",
        "apache spark": "Apache Spark",
        "spark": "Apache Spark",
        "full-stack engineer": "full-stack",
        "cloud environment": "cloud",
        "architect collaboration": "collaborate with architects",
    }
    if lower in replacements:
        return replacements[lower]
    if text.isupper() or re.search(r"[+#./-]", text):
        return text
    return text[0].upper() + text[1:] if len(text) <= 4 and text.lower() not in STOPWORDS else text


def normalize_keyword_key(value: str) -> str:
    key = normalize_text(value)
    if key == "net":
        key = ".net"
    key = key.replace("restful api", "rest api")
    key = key.replace("apache spark", "spark")
    key = key.replace("front end", "front-end").replace("back end", "back-end").replace("full stack", "full-stack")
    key = key.replace("architect collaboration", "collaborate with architects")
    key = key.strip(" ,:-")
    return key


def is_generic_keyword(value: str) -> bool:
    key = normalize_keyword_key(value)
    words = tokenize(key)
    if key in GENERIC_KEYWORD_PHRASES:
        return True
    if key in {"i", "ii", "iii", "iv", "v"}:
        return True
    if key in {"engineer iv", "software engineer iv"}:
        return True
    if any(role_word in key for role_word in (" engineer", " developer", " manager", " analyst", " specialist")) and len(words) <= 3:
        return True
    if not words:
        return True
    if len(words) == 1 and words[0] in {
        "advanced",
        "design",
        "development",
        "testing",
        "coding",
        "engineering",
        "full",
        "fundamentals",
        "scripts",
        "environment",
        "delivery",
    }:
        return True
    if "fundamentals" in key:
        return True
    if key in {"python data"}:
        return True
    if key in {"object-oriented design", "object oriented design"}:
        return True
    return False


def phrase_has_signal(value: str) -> bool:
    key = normalize_keyword_key(value)
    words = tokenize(key)
    if len(words) < 2:
        return re.search(r"[A-Z]{2,}|[+#./-]", value) is not None
    if is_generic_keyword(value):
        return False
    return any(
        re.search(pattern, value)
        for pattern in (
            r"[A-Z]{2,}",
            r"[+#./-]",
            r"(?i)\b(api|sql|cloud|database|data|front-end|back-end|full-stack|architecture|architects|review|documentation|specifications|security|audit|regulatory|compliance|mentorship|leadership|delivery|structures|algorithms|methodology|sdlc)\b",
        )
    )


def score_extracted_term(
    term: str,
    sentence: str,
    normalized_document: str,
    role_inference: RoleInference,
) -> float:
    key = normalize_keyword_key(term)
    if key in {normalize_keyword_key(item) for item in role_inference.core_stack}:
        return 4.0
    weight = 2.0
    sentence_text = normalize_text(sentence)
    if any(marker in sentence_text for marker in ("required", "must", "expert", "advanced", "thorough", "responsibilities", "expectations")):
        weight += 1.1
    if any(marker in sentence_text for marker in ("preferred", "nice to have", "plus")):
        weight -= 0.5
    if normalized_document.count(key) > 1:
        weight += 0.6
    if phrase_has_signal(term):
        weight += 0.5
    return max(1.0, min(4.0, weight))


def prune_extracted_keywords(candidates: list[tuple[str, float]]) -> list[tuple[str, float]]:
    ordered = sorted(candidates, key=lambda item: (-item[1], item[0].lower()))
    selected: list[tuple[str, float]] = []
    for term, weight in ordered:
        key = normalize_keyword_key(term)
        key_words = set(tokenize(key))
        if not key_words:
            continue
        duplicate = False
        for existing, existing_weight in selected:
            existing_key = normalize_keyword_key(existing)
            existing_words = set(tokenize(existing_key))
            if key == existing_key:
                duplicate = True
                break
            if len(key_words) >= 3 and existing_words and existing_words.issubset(key_words) and existing_weight >= weight:
                duplicate = True
                break
            if key not in HIGH_VALUE_STANDALONE_TERMS and len(existing_words) >= 3 and key_words.issubset(existing_words):
                duplicate = True
                break
        if not duplicate:
            selected.append((term, weight))
    return selected


def keyword_match_aliases(keyword: str) -> list[str]:
    key = canonical_keyword(keyword)
    aliases = TECH_ALIASES.get(key)
    if aliases:
        return [*aliases, *semantic_aliases_for_keyword(keyword)]
    normalized = normalize_keyword_key(keyword)
    variants = {
        normalized,
        normalized.replace("-", " "),
        normalized.replace("/", " "),
    }
    if "api" in normalized and "rest" not in normalized:
        variants.update({"api", "apis"})
    if normalized == "database sql statements":
        variants.update({"sql", "sql statements", "database sql"})
    variants.update(semantic_aliases_for_keyword(keyword))
    return [variant for variant in variants if variant]


def score_formatting(resume: ResumeContent) -> int:
    score = 100
    dump = resume.model_dump_json().lower()
    if any(marker in dump for marker in ("<table", "text-box", "progress bar", "star rating", "click here")):
        score -= 35
    if not resume.contact.email:
        score -= 8
    if not resume.contact.phone:
        score -= 8
    if not resume.contact.location:
        score -= 4
    if not resume.summary:
        score -= 10
    if not resume.skills:
        score -= 12
    if not resume.experience:
        score -= 18
    if any(not item.start_date or not item.end_date for item in resume.experience):
        score -= 8
    if len(resume_to_text(resume).split()) > 900:
        score -= 6
    return clamp(score)


def score_readability(resume: ResumeContent) -> int:
    bullets = [bullet for item in resume.experience for bullet in item.bullets]
    if not bullets:
        return 55

    score = 82
    action_rate = sum(starts_with_action_verb(bullet) for bullet in bullets) / len(bullets)
    metric_rate = sum(has_metric(bullet) for bullet in bullets) / len(bullets)
    avg_words = sum(len(bullet.split()) for bullet in bullets) / len(bullets)

    score += round(action_rate * 10)
    score += round(metric_rate * 10)
    if 13 <= avg_words <= 28:
        score += 6
    elif avg_words > 36:
        score -= 8

    summary_words = len((resume.summary or "").split())
    if resume.summary and 35 <= summary_words <= 85:
        score += 4
    elif resume.summary:
        score -= 5

    return clamp(score)


def score_title_match(resume: ResumeContent, target_role: str, job_description: str) -> int:
    desired = normalize_text(target_role or infer_title_from_job(job_description))
    if not desired:
        return 70

    summary = normalize_text(resume.summary or "")
    roles = " ".join(normalize_text(item.role) for item in resume.experience)
    skills = " ".join(normalize_text(skill) for group in resume.skills for skill in group.items)
    bullets = " ".join(normalize_text(bullet) for item in resume.experience for bullet in item.bullets)
    desired_words = [word for word in tokenize(desired) if useful_word(word)]
    if not desired_words:
        return 70

    content_tokens = tokenize(" ".join([resume.title, summary, roles, skills, bullets]))
    content_overlap = title_concept_overlap(desired_words, content_tokens)
    return clamp(round(content_overlap * 100))


def score_skill_coverage(resume: ResumeContent, keyword_matches: list[KeywordMatch]) -> int:
    if not keyword_matches:
        return 0

    skills_text = normalize_text(" ".join(skill for group in resume.skills for skill in group.items))
    important = keyword_matches[:14]
    if not important:
        return 0

    covered = 0.0
    total = 0.0
    for item in important:
        total += item.weight
        canonical = canonical_keyword(item.keyword)
        aliases = TECH_ALIASES.get(canonical, [canonical])
        if any(contains_phrase(skills_text, alias) for alias in aliases):
            covered += item.weight
        elif item.matched:
            covered += item.weight * 0.45

    return clamp(round((covered / total) * 100)) if total else 0


def build_suggestions(
    resume: ResumeContent,
    payload: GenerateResumeRequest,
    keyword_score: int,
    formatting_score: int,
    readability_score: int,
    title_score: int,
    missing_keywords: list[str],
) -> list[ResumeSuggestion]:
    suggestions: list[ResumeSuggestion] = []

    if missing_keywords:
        top_keywords = ", ".join(f'"{keyword}"' for keyword in missing_keywords[:3])
        suggestions.append(
            ResumeSuggestion(
                text=f"Add truthful evidence for missing job-description keywords: {top_keywords}.",
                points=score_gap_points(keyword_score, 10),
            )
        )

    if title_score < 75 and payload.target_role:
        suggestions.append(
            ResumeSuggestion(
                text=f'Naturally cover the important concepts from "{payload.target_role}" in skills or experience when accurate.',
                points=score_gap_points(title_score, 7),
            )
        )

    bullets = [bullet for item in resume.experience for bullet in item.bullets]
    if bullets and sum(has_metric(bullet) for bullet in bullets) / len(bullets) < 0.35:
        suggestions.append(
            ResumeSuggestion(
                text="Quantify more experience bullets with supported metrics such as %, time saved, users, revenue, or defect reduction.",
                points=6,
            )
        )

    if formatting_score < 95:
        missing_contact = []
        if not resume.contact.email:
            missing_contact.append("email")
        if not resume.contact.phone:
            missing_contact.append("phone")
        if not resume.contact.location:
            missing_contact.append("location")
        if missing_contact:
            suggestions.append(
                ResumeSuggestion(
                    text=f"Add missing contact fields in plain body text: {', '.join(missing_contact)}.",
                    points=5,
                )
            )

    if readability_score < 88:
        suggestions.append(
            ResumeSuggestion(
                text="Keep bullets concise, start with action verbs, and place keywords in natural achievement statements.",
                points=4,
            )
        )

    return suggestions[:6]


def resume_to_text(resume: ResumeContent) -> str:
    parts: list[str] = [
        resume.name,
        resume.title,
        resume.contact.email,
        resume.contact.phone,
        resume.contact.location,
        resume.contact.linkedin,
        resume.contact.github,
        resume.contact.portfolio,
        resume.summary or "",
    ]

    for group in resume.skills:
        parts.append(group.category)
        parts.extend(group.items)
    for item in resume.experience:
        parts.extend([item.company, item.role, item.location, item.start_date, item.end_date])
        parts.extend(item.bullets)
    for project in resume.projects:
        parts.extend([project.name, project.org, project.link])
        parts.extend(project.technologies)
        parts.extend(project.bullets)
    for education in resume.education:
        parts.extend([education.degree, education.institution, education.location, education.grad_year, education.gpa])
    for cert in resume.certifications:
        parts.extend([cert.name, cert.issuer])

    return " ".join(part for part in parts if part)


def infer_title_from_job(job_description: str) -> str:
    match = re.search(r"(?:hiring|role|position|title)\s+(?:a|an|for|:)?\s*([A-Z][A-Za-z0-9 /\-+.]{3,80})", job_description)
    return match.group(1).strip(" .,:;") if match else ""


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("’", "'").lower()).strip()


def tokenize(text: str) -> list[str]:
    return [token.strip(".,:;()[]{}") for token in re.findall(r"[a-z0-9][a-z0-9+#./-]*", text.lower()) if token.strip(".,:;()[]{}")]


def useful_word(word: str) -> bool:
    clean = word.strip(".,:;()[]{}")
    return (
        len(clean) >= 3
        and clean not in STOPWORDS
        and clean not in JOB_POSTING_NOISE
        and not clean.isdigit()
    )


def contains_phrase(text: str, phrase: str) -> bool:
    normalized = normalize_text(phrase)
    if not normalized:
        return False
    if re.search(r"[+#./-]", normalized):
        return normalized in text
    return re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text) is not None


def is_requirement_context(words: list[str], index: int) -> bool:
    window = words[max(0, index - 8) : index + 8]
    return any(word in {"must", "required", "requirements", "preferred", "proficiency", "expertise"} for word in window)


def is_alias_in_requirement_context(text: str, alias: str) -> bool:
    normalized_alias = normalize_text(alias)
    alias_index = text.find(normalized_alias)
    if alias_index < 0:
        return False
    window = text[max(0, alias_index - 80) : alias_index + len(normalized_alias) + 80]
    return any(
        phrase in window
        for phrase in (
            "required",
            "requirements",
            "preferred",
            "must have",
            "must-have",
            "experience with",
            "proficiency",
            "expertise",
            "hands-on",
        )
    )


def overlap_ratio(needle_words: list[str], haystack_words: list[str]) -> float:
    haystack = set(haystack_words)
    if not needle_words:
        return 0
    return sum(1 for word in needle_words if word in haystack) / len(set(needle_words))


def title_concept_overlap(needle_words: list[str], haystack_words: list[str]) -> float:
    if not needle_words:
        return 0
    haystack = set(haystack_words)
    matches = 0
    for word in set(needle_words):
        equivalents = TITLE_EQUIVALENTS.get(word, {word})
        if haystack.intersection(equivalents):
            matches += 1
    return matches / len(set(needle_words))


def starts_with_action_verb(bullet: str) -> bool:
    first = bullet.split(" ", 1)[0].strip(".,:;").lower()
    return first in ACTION_VERBS


def has_metric(text: str) -> bool:
    return bool(
        re.search(
            r"(\d+(?:\.\d+)?\s*[%+]|\$[0-9]|[0-9]+\s*(users|teams|hours|days|weeks|months|years|sprints|release cycles|releases|records|tickets|queries|defects|incidents|modules|applications|apis|services|revenue))",
            text.lower(),
        )
    )


def display_keyword(keyword: str) -> str:
    display = {
        ".net": ".NET",
        "agile scrum": "Agile/Scrum",
        "api development": "API Development",
        "asp.net identity": "ASP.NET Identity",
        "asp.net core": "ASP.NET Core",
        "asp.net mvc": "ASP.NET MVC",
        "aws": "AWS",
        "azure": "Azure",
        "azure devops": "Azure DevOps",
        "ci/cd": "CI/CD",
        "c#": "C#",
        "css": "CSS",
        "git": "Git",
        "github": "GitHub",
        "github actions": "GitHub Actions",
        "gitlab": "GitLab",
        "google cloud": "Google Cloud",
        "graphql": "GraphQL",
        "html": "HTML",
        "jasmine": "Jasmine",
        "jenkins": "Jenkins",
        "javascript": "JavaScript",
        "jquery": "jQuery",
        "mongodb": "MongoDB",
        "mvc": "MVC",
        "ms-test": "MS-Test",
        "ms sql server": "MS SQL Server",
        "mysql": "MySQL",
        "next.js": "Next.js",
        "node.js": "Node.js",
        "nunit": "NUnit",
        "object-oriented design": "Object-Oriented Design",
        "oauth": "OAuth",
        "oracle": "Oracle",
        "postgresql": "PostgreSQL",
        "react": "React",
        "rest api": "REST API",
        "ssis": "SSIS",
        "ssrs": "SSRS",
        "sonarqube": "SonarQube",
        "tfs": "TFS",
        "typescript": "TypeScript",
        "visual studio": "Visual Studio",
        "wcag": "WCAG",
    }
    if keyword in display:
        return display[keyword]
    if re.search(r"[A-Z]{2,}|[+#./-]", keyword):
        return keyword
    return keyword[0].upper() + keyword[1:] if keyword else keyword


def canonical_keyword(display_value: str) -> str:
    normalized = normalize_text(display_value).replace("/", " ")
    for canonical in TECH_ALIASES:
        if normalized in {canonical, normalize_text(display_keyword(canonical)).replace("/", " ")}:
            return canonical
    return normalize_text(display_value)


def score_gap_points(score: int, max_points: int) -> int:
    return max(2, min(max_points, round((100 - score) / 10)))


def clamp(value: int) -> int:
    return max(0, min(100, value))
