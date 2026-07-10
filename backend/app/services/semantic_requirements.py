import re
from dataclasses import dataclass

from app.schemas.resume import (
    AtsKeywordPlanItem,
    CandidateEvidenceMatch,
    CandidateProfile,
    SemanticKeywordItem,
    SemanticRequirementGroup,
    SemanticRequirementPlan,
)


@dataclass(frozen=True)
class SemanticTaxonomyEntry:
    name: str
    category: str
    priority: str
    triggers: tuple[str, ...]
    exact_terms: tuple[str, ...]
    related_terms: tuple[str, ...]
    resume_sections: tuple[str, ...]
    guidance: str


DIRECT_EVIDENCE_ALIASES: dict[str, tuple[str, ...]] = {
    ".NET": (".NET", "dotnet", "dot net", "C#/.NET", "C# / .NET"),
    "C#": ("C#", "C#/.NET", "C# / .NET", "c sharp"),
    "CI/CD": ("CI/CD", "CI CD", "continuous integration", "continuous delivery", "continuous deployment"),
    "Code Review": ("code review", "code reviews", "peer code review", "peer code reviews"),
    "Testing Best Practices": ("testing best practices", "testing", "test practices"),
    "Unit Testing": ("unit testing", "unit tests"),
    "Integration Testing": ("integration testing", "integration tests"),
    "Regression Testing": ("regression testing", "regression tests"),
    "Test Automation": ("test automation", "automated testing"),
    "Cloud Platforms": ("cloud platforms", "cloud platform", "cloud services", "cloud environment", "cloud environments"),
    "Modern Web Technologies": ("modern web technologies", "web technologies"),
    "Application Frameworks": ("application frameworks", "application framework", "modern development frameworks", "modern development framework"),
    "Databases": ("databases", "database platforms", "database systems"),
    "Version Control": ("version control", "source control"),
    "Deployment Practices": ("deployment practices", "deployment best practices"),
    "Object-Oriented Development": ("object-oriented development", "object oriented development", "object-oriented programming", "object oriented programming", "object-oriented design", "object oriented design"),
    "Stakeholder Collaboration": ("stakeholder collaboration", "stakeholders", "business stakeholders"),
    "Requirements Gathering": ("gather requirements", "requirements gathering"),
    "Technical Leadership": ("technical leadership", "engineering leadership", "guidance to developers", "guide junior developers"),
    "Communication Skills": ("communication skills", "effective communication", "communicate effectively"),
    "Knowledge Sharing": ("knowledge sharing", "knowledge transfer"),
    "Financial Services": ("financial services", "investment environments"),
    "Trading": ("trading", "trading activities"),
    "Valuation": ("valuation", "valuation activities"),
    "Troubleshooting": ("troubleshooting", "technical investigation"),
    "Problem Solving": ("problem-solving", "problem solving"),
    "Workflow Analysis": ("analyze existing workflows", "workflow analysis"),
    "Operational Efficiency": ("operational efficiency", "improve operational efficiency"),
    "Quality Improvement": ("quality improvements", "quality improvement"),
    "System Documentation": ("document system designs", "system documentation", "document system design"),
    "Bachelor's Degree": ("bachelor's degree", "bachelors degree", "bachelor degree"),
    "Scalable Enterprise Applications": ("scalable enterprise applications", "build scalable enterprise applications"),
    "High-Performance Software": ("high-performing software", "high-performance software"),
    "Reliable Software Design": ("reliable software", "reliable software design"),
    "Front-Office Applications": ("front-office applications", "front office applications"),
    "Research Applications": ("research activities", "research applications"),
}


DIRECT_SEMANTIC_KEYWORDS: tuple[tuple[str, str, str], ...] = (
    ("Cloud Platforms", "Cloud", "important"),
    ("Testing Best Practices", "Quality", "important"),
    ("Unit Testing", "Quality", "important"),
    ("Integration Testing", "Quality", "important"),
    ("Regression Testing", "Quality", "important"),
    ("Test Automation", "Quality", "important"),
    ("Modern Web Technologies", "Web", "important"),
    ("Application Frameworks", "Frameworks", "important"),
    ("Databases", "Databases", "important"),
    ("Version Control", "DevOps", "important"),
    ("Code Review", "Review", "important"),
    ("Object-Oriented Development", "Architecture", "important"),
    ("Financial Services", "Domain", "important"),
    ("Trading", "Domain", "important"),
    ("Valuation", "Domain", "important"),
    ("Research Applications", "Domain", "important"),
    ("Front-Office Applications", "Domain", "important"),
    ("Technical Leadership", "Leadership", "important"),
    ("Knowledge Sharing", "Leadership", "important"),
    ("Stakeholder Collaboration", "Collaboration", "important"),
    ("Requirements Gathering", "Collaboration", "important"),
    ("Communication Skills", "Collaboration", "important"),
    ("Troubleshooting", "Support", "important"),
    ("Problem Solving", "Support", "important"),
    ("Workflow Analysis", "Problem Solving", "important"),
    ("Operational Efficiency", "Problem Solving", "important"),
    ("Quality Improvement", "Engineering Practices", "important"),
    ("System Documentation", "Engineering Practices", "important"),
    ("Bachelor's Degree", "Experience and Education", "critical"),
    ("Scalable Enterprise Applications", "Architecture", "critical"),
    ("High-Performance Software", "Architecture", "important"),
    ("Reliable Software Design", "Architecture", "important"),
)


SEMANTIC_TAXONOMY: tuple[SemanticTaxonomyEntry, ...] = (
    SemanticTaxonomyEntry(
        name="Developer Productivity",
        category="Developer Experience",
        priority="critical",
        triggers=("developer productivity", "developer experience", "efficient development", "frictionless development", "development workflows", "build tooling"),
        exact_terms=("developer productivity", "developer experience", "build tooling"),
        related_terms=("internal tools", "faster releases", "code quality", "local dev setup"),
        resume_sections=("Summary", "Skills", "Experience"),
        guidance="Show tooling, automation, CI validation, release speed, or workflow improvements that helped engineers ship faster.",
    ),
    SemanticTaxonomyEntry(
        name="Frontend Architecture",
        category="Frontend",
        priority="critical",
        triggers=("frontend architecture", "front-end architecture", "frontend frameworks", "front-end frameworks", "rich react application", "react applications"),
        exact_terms=("frontend architecture", "frontend frameworks"),
        related_terms=("reusable components", "state management", "routing", "design systems", "performance optimization", "bundle splitting", "component libraries"),
        resume_sections=("Summary", "Skills", "Experience"),
        guidance="Prioritize supported React, component architecture, UI performance, routing, design-system, or reusable frontend patterns.",
    ),
    SemanticTaxonomyEntry(
        name="End-to-End Ownership",
        category="Ownership",
        priority="critical",
        triggers=("own features end-to-end", "end-to-end", "initial design", "large-scale rollout", "from design to deployment", "own delivery"),
        exact_terms=("end-to-end ownership", "large-scale rollout"),
        related_terms=("design", "implementation", "monitoring", "rollout", "stakeholder feedback", "release planning", "SDLC"),
        resume_sections=("Summary", "Experience"),
        guidance="Frame bullets around design through rollout ownership, validation, release planning, and stakeholder feedback loops.",
    ),
    SemanticTaxonomyEntry(
        name="Product-First Engineering",
        category="Product Collaboration",
        priority="important",
        triggers=("product-first", "product managers", "designers", "customer pain", "user impact", "delightful", "feedback"),
        exact_terms=("product-first approach", "product collaboration"),
        related_terms=("user impact", "business outcome", "customer pain points", "feedback iteration", "product managers", "designers", "product design", "product feedback loops", "cross-functional collaboration"),
        resume_sections=("Summary", "Experience"),
        guidance="Connect engineering decisions to user impact, product/design collaboration, and measurable business outcomes.",
    ),
    SemanticTaxonomyEntry(
        name="API Requirements",
        category="API",
        priority="important",
        triggers=("api", "apis", "backend services", "integrations", "service integrations", "rest"),
        exact_terms=("API", "API requirements", "backend services", "integrations"),
        related_terms=("backend services", "integrations", "authentication", "authorization"),
        resume_sections=("Skills", "Experience"),
        guidance="Use API design, service integration, authentication, Swagger/Postman, and backend service evidence when supported.",
    ),
    SemanticTaxonomyEntry(
        name="Cloud Requirements",
        category="Cloud",
        priority="important",
        triggers=("cloud", "cloud platforms", "cloud platform", "cloud services", "cloud environment"),
        exact_terms=("Cloud Platforms",),
        related_terms=(),
        resume_sections=("Skills", "Experience"),
        guidance="Include cloud platform, deployment, container, pipeline, and monitoring evidence only when present in the profile.",
    ),
    SemanticTaxonomyEntry(
        name="Quality Engineering",
        category="Quality",
        priority="important",
        triggers=("quality engineering", "testing", "quality", "test automation", "feedback loops", "ci validation"),
        exact_terms=("quality engineering", "Testing Best Practices"),
        related_terms=("code reviews",),
        resume_sections=("Skills", "Experience"),
        guidance="Show test automation, CI validation, regression testing, code reviews, and quality gates when supported.",
    ),
    SemanticTaxonomyEntry(
        name="Cross-Functional Collaboration",
        category="Collaboration",
        priority="important",
        triggers=("work closely with", "product managers", "designers", "peers in engineering", "cross-functional", "stakeholders"),
        exact_terms=("cross-functional collaboration", "product and design collaboration"),
        related_terms=("product managers", "designers", "product design", "engineering peers", "stakeholders", "stakeholder collaboration", "QA", "business users", "feedback iteration", "product feedback loops"),
        resume_sections=("Summary", "Experience"),
        guidance="Use collaboration with product, design, QA, architects, business users, and engineering peers to show operating maturity.",
    ),
    SemanticTaxonomyEntry(
        name="Engineering Process and Scaling",
        category="Engineering Process",
        priority="important",
        triggers=("scale our product and team", "mature our tooling", "best practices", "engineering processes", "hiring"),
        exact_terms=("engineering processes", "best practices", "scaling engineering"),
        related_terms=("engineering process", "best practices", "standards", "mentoring", "code reviews", "documentation", "release management", "team scaling"),
        resume_sections=("Summary", "Experience"),
        guidance="Represent process maturity through standards, reviews, documentation, mentoring, release management, and repeatable delivery practices.",
    ),
    SemanticTaxonomyEntry(
        name="Modern Web Technologies",
        category="Web",
        priority="important",
        triggers=("modern web technologies", "web technologies"),
        exact_terms=("Modern Web Technologies",),
        related_terms=(),
        resume_sections=("Skills", "Experience"),
        guidance="Keep broad web-technology requirements broad unless the JD names a specific framework or language.",
    ),
    SemanticTaxonomyEntry(
        name="Application Frameworks",
        category="Frameworks",
        priority="important",
        triggers=("application frameworks", "modern development frameworks"),
        exact_terms=("Application Frameworks",),
        related_terms=(),
        resume_sections=("Skills", "Experience"),
        guidance="Keep framework requirements broad unless the JD names a specific framework.",
    ),
    SemanticTaxonomyEntry(
        name="Database Requirements",
        category="Databases",
        priority="important",
        triggers=("databases", "database platforms", "database systems"),
        exact_terms=("Databases",),
        related_terms=(),
        resume_sections=("Skills", "Experience"),
        guidance="Keep database requirements broad unless the JD names a specific database product.",
    ),
    SemanticTaxonomyEntry(
        name="Version Control",
        category="DevOps",
        priority="important",
        triggers=("version control", "source control"),
        exact_terms=("Version Control",),
        related_terms=(),
        resume_sections=("Skills", "Experience"),
        guidance="Keep version-control requirements broad unless the JD names a specific tool.",
    ),
)


def build_semantic_requirement_plan(
    job_description: str,
    target_role: str = "",
    candidate_profile: CandidateProfile | None = None,
) -> SemanticRequirementPlan:
    jd_text = normalize_semantic_text(f"{target_role} {job_description}")
    matched_entries = [entry for entry in SEMANTIC_TAXONOMY if taxonomy_entry_matches(entry, jd_text)]
    exact_keywords: list[SemanticKeywordItem] = []
    semantic_keywords: list[SemanticKeywordItem] = []
    requirement_groups: list[SemanticRequirementGroup] = []
    evidence_map: list[CandidateEvidenceMatch] = []
    ats_plan: list[AtsKeywordPlanItem] = []

    profile_text = profile_to_semantic_text(candidate_profile) if candidate_profile else ""
    exact_keywords.extend(direct_semantic_keywords(f"{target_role}\n{job_description}"))
    for entry in matched_entries:
        exact = dedupe_terms(
            [
                term
                for term in entry.exact_terms
                if has_direct_jd_evidence(term, f"{target_role}\n{job_description}")
            ]
        )
        related = dedupe_terms(entry.related_terms)
        exact_keywords.extend(
            SemanticKeywordItem(term=term, category=entry.category, priority=entry.priority, source="exact")
            for term in exact
        )
        semantic_keywords.extend(
            SemanticKeywordItem(term=term, category=entry.category, priority=entry.priority, source=entry.name)
            for term in related
        )
        requirement_groups.append(
            SemanticRequirementGroup(
                name=entry.name,
                category=entry.category,
                priority=entry.priority,
                exactKeywords=exact,
                semanticKeywords=related,
                relatedConcepts=related,
            )
        )
        evidence = map_entry_to_candidate(entry, profile_text)
        evidence_map.append(evidence)
        ats_plan.extend(
            AtsKeywordPlanItem(
                keyword=term,
                priority=entry.priority,
                targetSections=list(entry.resume_sections),
                confidence=evidence.confidence,
                guidance=entry.guidance,
            )
            for term in dedupe_terms([*exact, *related])
            if evidence.confidence != "missing" or term in exact
        )

    return SemanticRequirementPlan(
        exactKeywords=dedupe_keyword_items(exact_keywords),
        semanticKeywords=dedupe_keyword_items(semantic_keywords),
        requirementGroups=requirement_groups,
        candidateEvidenceMap=evidence_map,
        missingRequirements=[item.requirement for item in evidence_map if item.confidence == "missing"],
        weakRequirements=[item.requirement for item in evidence_map if item.confidence == "partial"],
        atsKeywordPlan=dedupe_ats_plan(ats_plan),
    )


def direct_semantic_keywords(job_description: str) -> list[SemanticKeywordItem]:
    return [
        SemanticKeywordItem(term=term, category=category, priority=priority, source="direct")
        for term, category, priority in DIRECT_SEMANTIC_KEYWORDS
        if has_direct_jd_evidence(term, job_description)
    ]


def semantic_terms_for_job(job_description: str, target_role: str = "") -> list[tuple[str, float]]:
    plan = build_semantic_requirement_plan(job_description, target_role)
    weighted: list[tuple[str, float]] = []
    for item in plan.exact_keywords:
        weight = {"critical": 4.2, "important": 3.2, "preferred": 2.0}.get(item.priority, 2.5)
        weighted.append((item.term, weight))
    return dedupe_weighted_terms(weighted)


def semantic_aliases_for_keyword(keyword: str) -> list[str]:
    key = normalize_semantic_text(keyword)
    aliases: list[str] = []
    for entry in SEMANTIC_TAXONOMY:
        all_terms = [entry.name, *entry.exact_terms, *entry.related_terms]
        if any(normalize_semantic_text(term) == key for term in all_terms):
            aliases.extend([entry.name, *entry.exact_terms, *entry.related_terms])
    return dedupe_terms(aliases)


def taxonomy_entry_matches(entry: SemanticTaxonomyEntry, jd_text: str) -> bool:
    return any(phrase_in_text(trigger, jd_text) for trigger in entry.triggers)


def has_direct_jd_evidence(
    term: str,
    job_description: str,
    aliases: list[str] | tuple[str, ...] | None = None,
) -> bool:
    return find_direct_jd_evidence(term, job_description, aliases) is not None


def find_direct_jd_evidence(
    term: str,
    job_description: str,
    aliases: list[str] | tuple[str, ...] | None = None,
) -> str | None:
    if not term.strip() or not job_description.strip():
        return None
    sentences = split_evidence_sentences(job_description)
    search_terms = dedupe_terms([term, *(aliases or direct_evidence_aliases(term))])
    for sentence in sentences:
        normalized_sentence = normalize_semantic_text(sentence)
        if direct_special_case_matches(term, normalized_sentence):
            return sentence
        for alias in search_terms:
            if phrase_in_text(alias, normalized_sentence):
                return sentence
    return None


def direct_special_case_matches(term: str, normalized_sentence: str) -> bool:
    key = normalize_semantic_text(term)
    years_match = re.search(r"\b(\d+\+?) years of experience\b", key)
    if years_match:
        return re.search(rf"\b{re.escape(years_match.group(1))}\s+years?\b", normalized_sentence) is not None
    if key == "testing best practices":
        return "testing" in normalized_sentence and "best practices" in normalized_sentence
    if key == "cloud platforms":
        return "cloud" in normalized_sentence and any(word in normalized_sentence for word in ("platform", "platforms", "services", "environment", "environments"))
    return False


def split_evidence_sentences(text: str) -> list[str]:
    protected = (
        text.replace(".NET", "__DOT_NET__")
        .replace(".Net", "__DOT_NET__")
        .replace(".net", "__DOT_NET__")
        .replace("ASP.NET", "ASP__DOT__NET")
        .replace("Node.js", "Node__DOT__js")
        .replace("Next.js", "Next__DOT__js")
    )
    return [
        sentence.strip()
        .replace("__DOT_NET__", ".NET")
        .replace("ASP__DOT__NET", "ASP.NET")
        .replace("Node__DOT__js", "Node.js")
        .replace("Next__DOT__js", "Next.js")
        for sentence in re.split(r"[\n.;]+", protected)
        if sentence.strip()
    ]


def direct_evidence_aliases(term: str) -> tuple[str, ...]:
    key = normalize_semantic_text(term)
    for alias_term, aliases in DIRECT_EVIDENCE_ALIASES.items():
        if normalize_semantic_text(alias_term) == key:
            return aliases
    return ()


def map_entry_to_candidate(entry: SemanticTaxonomyEntry, profile_text: str) -> CandidateEvidenceMatch:
    supported = [term for term in entry.related_terms if phrase_in_text(term, profile_text)]
    exact_supported = [term for term in entry.exact_terms if phrase_in_text(term, profile_text)]
    confidence = "missing"
    if exact_supported or len(supported) >= 2:
        confidence = "strong"
    elif supported:
        confidence = "partial"
    return CandidateEvidenceMatch(
        requirement=entry.name,
        confidence=confidence,
        evidence=build_evidence_snippets(profile_text, [*exact_supported, *supported]),
        supportedKeywords=dedupe_terms([*exact_supported, *supported]),
        missingKeywords=[term for term in entry.related_terms if term not in supported][:8],
        suggestedResumeUse=list(entry.resume_sections),
    )


def build_evidence_snippets(profile_text: str, terms: list[str]) -> list[str]:
    snippets = []
    for term in terms[:8]:
        normalized = normalize_semantic_text(term)
        if normalized and normalized in profile_text:
            snippets.append(term)
    return dedupe_terms(snippets)


def profile_to_semantic_text(profile: CandidateProfile | None) -> str:
    if not profile:
        return ""
    parts = [
        profile.title,
        profile.summary,
        " ".join(skill for group in profile.skills for skill in group.items),
        " ".join(
            " ".join([exp.company, exp.role, exp.location, exp.raw_notes, *exp.bullets, *exp.metric_flags])
            for exp in profile.experience
        ),
        " ".join(" ".join([project.name, project.org, *project.technologies, *project.bullets]) for project in profile.projects),
    ]
    return normalize_semantic_text(" ".join(parts))


def normalize_semantic_text(value: str) -> str:
    text = value.lower().replace("&", " and ")
    text = re.sub(r"(?<=\w)[./](?=\w)", " ", text)
    text = re.sub(r"[^a-z0-9+#.\-/ ]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def phrase_in_text(phrase: str, text: str) -> bool:
    normalized = normalize_semantic_text(phrase)
    if not normalized:
        return False
    return bool(re.search(rf"(?<![a-z0-9+#]){re.escape(normalized)}(?![a-z0-9+#])", text))


def dedupe_terms(items) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item).strip()
        key = normalize_semantic_text(value)
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def dedupe_keyword_items(items: list[SemanticKeywordItem]) -> list[SemanticKeywordItem]:
    seen: set[str] = set()
    result: list[SemanticKeywordItem] = []
    for item in items:
        key = normalize_semantic_text(item.term)
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def dedupe_ats_plan(items: list[AtsKeywordPlanItem]) -> list[AtsKeywordPlanItem]:
    seen: set[str] = set()
    result: list[AtsKeywordPlanItem] = []
    for item in items:
        key = normalize_semantic_text(item.keyword)
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result[:40]


def dedupe_weighted_terms(items: list[tuple[str, float]]) -> list[tuple[str, float]]:
    best: dict[str, tuple[str, float]] = {}
    for term, weight in items:
        key = normalize_semantic_text(term)
        if key and (key not in best or weight > best[key][1]):
            best[key] = (term, weight)
    return sorted(best.values(), key=lambda item: (-item[1], item[0]))[:36]
