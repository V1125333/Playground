import re

from app.schemas.resume import ResumeContent

PROHIBITED_MARKERS = [
    "<table",
    "text-box",
    "progress bar",
    "star rating",
    "click here",
]

PROHIBITED_META_PHRASES = [
    "aligned with the target role",
    "target role requirements",
    "job-description technologies",
    "job description technologies",
    "ATS-relevant technology evidence",
    "recruiter-relevant outcomes",
    "recruiter-relevant",
    "across 1 recent role",
    "across 2 recent roles",
    "across 3 recent roles",
    "ats-relevant",
    "resume-writing",
    "keyword matching",
    "job description keywords",
]

CATEGORY_LABELS = [
    "Programming Languages",
    "Frontend",
    "Backend",
    "Cloud",
    "Databases",
    "Testing",
    "DevOps & Tools",
    "Data & Reporting",
    "Methodologies",
    "Security",
    "Technical Skills",
]

ACTION_VERBS = {
    "architected",
    "analyzed",
    "authored",
    "automated",
    "built",
    "collaborated",
    "configured",
    "coordinated",
    "created",
    "delivered",
    "designed",
    "developed",
    "documented",
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
    "rebuilt",
    "reduced",
    "resolved",
    "reviewed",
    "shipped",
    "standardized",
    "strengthened",
    "streamlined",
    "supported",
    "translated",
    "troubleshot",
}


def validate_resume_content(resume: ResumeContent) -> None:
    """Validate content-level rules from resume_prompt.md before layout/export."""
    text = resume.model_dump_json().lower()
    found = [marker for marker in PROHIBITED_MARKERS if marker in text]
    if found:
        raise ValueError(f"Resume contains ATS-prohibited content markers: {', '.join(found)}")
    meta_found = [phrase for phrase in PROHIBITED_META_PHRASES if phrase in text]
    if meta_found:
        raise ValueError(f"Resume contains prohibited meta/process language: {', '.join(meta_found)}")

    if resume.summary:
        if "\n" in resume.summary or resume.summary.strip().startswith(("-", "*", "•")):
            raise ValueError("Summary must be one paragraph, not bullets.")
        if resume.title and resume.title.lower() in resume.summary.lower():
            raise ValueError("Summary must not repeat the header title.")
        leaked_labels = labels_in_text(resume.summary)
        if leaked_labels:
            raise ValueError(f"Summary contains leaked section/category labels: {', '.join(leaked_labels)}")
        sentence_count = count_sentences(resume.summary)
        if sentence_count != 3:
            raise ValueError("Summary must be exactly 3 sentences.")
        word_count = len(resume.summary.split())
        if word_count < 35 or word_count > 85:
            raise ValueError("Summary should stay near the requested 40-70 word range.")

    validate_skills(resume)

    seen_patterns: dict[str, str] = {}
    for experience in resume.experience:
        bullet_count = len(experience.bullets)
        if bullet_count < 4 or bullet_count > 6:
            raise ValueError(f"{experience.company} must have 4-6 experience bullets.")

        normalized_bullets = {normalize_sentence(bullet) for bullet in experience.bullets}
        if len(normalized_bullets) != bullet_count:
            raise ValueError(f"{experience.company} contains repeated bullets.")

        metric_count = 0
        for bullet in experience.bullets:
            words = bullet.split()
            if not words:
                raise ValueError("Experience bullets cannot be empty.")
            if words[0].strip(".,:;").lower() not in ACTION_VERBS:
                raise ValueError(f'Bullet should start with a strong action verb: "{bullet}"')
            leaked_labels = labels_in_text(bullet)
            if leaked_labels:
                raise ValueError(f"Experience bullet contains leaked labels: {', '.join(leaked_labels)}")
            if has_metric(bullet):
                metric_count += 1
            pattern = sentence_pattern(bullet)
            previous_company = seen_patterns.get(pattern)
            if previous_company and previous_company != experience.company:
                raise ValueError(
                    f'Repeated bullet sentence pattern appears in both {previous_company} and {experience.company}: "{pattern}"'
                )
            seen_patterns[pattern] = experience.company

        if metric_count > 3:
            raise ValueError(f"{experience.company} has too many quantified bullets.")


def normalize_sentence(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def validate_skills(resume: ResumeContent) -> None:
    seen_items: set[str] = set()
    normalized_labels = {label.lower() for label in CATEGORY_LABELS}
    for group in resume.skills:
        for item in group.items:
            normalized_item = item.strip().lower()
            if not normalized_item:
                raise ValueError(f"{group.category} contains an empty skill item.")
            if normalized_item in normalized_labels:
                raise ValueError(f"Skill item equals a category label: {item}")
            leaked = [label for label in CATEGORY_LABELS if skill_item_has_label_leak(item, label)]
            if leaked:
                raise ValueError(f"Skill item contains category label text: {item}")
            if normalized_item in seen_items:
                raise ValueError(f"Skill item is duplicated across categories: {item}")
            seen_items.add(normalized_item)


def skill_item_has_label_leak(item: str, label: str) -> bool:
    """Catch labels baked into values while allowing real skills like Google Cloud."""
    normalized_item = item.strip().lower()
    normalized_label = label.strip().lower()
    if normalized_item == normalized_label:
        return True
    return re.match(rf"^{re.escape(normalized_label)}\s*[:/|-]\s*\S+", normalized_item) is not None


def labels_in_text(value: str) -> list[str]:
    lowered = value.lower()
    return [label for label in CATEGORY_LABELS if f"{label.lower()}:" in lowered]


def sentence_pattern(value: str) -> str:
    normalized = normalize_sentence(value)
    normalized = re.sub(r"\b\d+[%+]?\b", "#", normalized)
    normalized = re.sub(r"\b(at|for)\s+[a-z0-9&.,' -]{2,40}\b", r"\1 <org>", normalized)
    words = [word for word in re.findall(r"[a-z#]+", normalized) if word not in {"the", "a", "an"}]
    return " ".join(words[:8])


def count_sentences(value: str) -> int:
    sanitized = (
        value.replace(".NET", "DOTNET")
        .replace("ASP.NET", "ASPNET")
        .replace("Node.js", "Nodejs")
        .replace("React.js", "Reactjs")
    )
    return len([item for item in re.split(r"[.!?]+", sanitized) if item.strip()])


def has_metric(value: str) -> bool:
    return bool(
        re.search(
            r"(\d+(?:\.\d+)?\s*[%+]|\$[0-9]|[0-9]+\s*(users|teams|hours|days|weeks|months|years|sprints|release cycles|releases|records|tickets|queries|defects|incidents|modules|applications|apis|services|revenue))",
            value.lower(),
        )
    )
