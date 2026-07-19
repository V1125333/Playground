import pytest
from pydantic import ValidationError

from app.schemas.resume import GenerateResumeRequest, SkillCategory
from app.services.skill_normalization import (
    SKILL_CATEGORY_REGISTRY,
    normalize_skill_name,
    parse_legacy_skill_text,
    resolve_skill_category_definition,
    split_skill_values,
)
from tests.test_generate_resume_request_contract import canonical_payload


def test_structured_skill_category_validation_and_normalization():
    category = SkillCategory(category="Testing", categoryId="testing", categoryName="Testing", order=0, items=["MS-Test"])

    assert category.items == ["MSTest"]
    assert category.category_id == "testing-quality-assurance"
    assert category.category_name == "Testing & Quality Assurance"


def test_approved_category_registry_is_controlled():
    assert [category.category_name for category in SKILL_CATEGORY_REGISTRY] == [
        "Programming Languages",
        "Backend Development",
        "Frontend Development",
        "Frameworks & Libraries",
        "Databases",
        "Cloud Platforms & Services",
        "DevOps, CI/CD & Containers",
        "Testing & Quality Assurance",
        "APIs & Integration",
        "Data Engineering & ETL",
        "Data Analytics & Reporting",
        "AI, Machine Learning & Generative AI",
        "Architecture & System Design",
        "Security & Identity",
        "Tools & Development Environments",
        "Software Development Practices",
        "Methodologies & Ways of Working",
        "Business & Domain Knowledge",
        "Communication & Collaboration",
        "Leadership & Management",
        "Languages",
        "Other Specialized Skills",
    ]
    assert resolve_skill_category_definition("C#") is None


def test_duplicate_skills_inside_category_are_rejected():
    with pytest.raises(ValidationError, match="Duplicate skills inside one category"):
        SkillCategory(category="Languages", categoryId="languages", categoryName="Languages", order=0, items=["C#", "c#"])


def test_category_prefix_inside_skill_item_is_rejected():
    with pytest.raises(ValidationError, match="category labels"):
        SkillCategory(category="Frontend", categoryId="frontend", categoryName="Frontend", order=0, items=["Frontend: React"])


def test_legacy_parser_preserves_parentheses_commas_and_known_categories():
    parsed = parse_legacy_skill_text(
        "Programming Languages: C#, JavaScript, Backend / .NET: ASP Net Core, Cloud: Microsoft Azure (App Service, Azure SQL)"
    )

    assert parsed.requires_review is True
    assert parsed.categories[0].category_name == "Programming Languages"
    assert parsed.categories[1].items == ["ASP.NET Core"]
    assert parsed.categories[1].category_id == "backend-development"
    assert parsed.categories[2].items == ["Microsoft Azure (App Service, Azure SQL)"]
    assert parsed.categories[2].category_name == "Cloud Platforms & Services"


def test_split_skill_values_keeps_parenthesized_comma_together():
    assert split_skill_values("Microsoft Azure (App Service, Azure SQL), Node JS") == [
        "Microsoft Azure (App Service, Azure SQL)",
        "Node.js",
    ]


def test_canonical_skill_names_are_controlled_not_semantic_expansion():
    assert normalize_skill_name("MS SQL Server") == "Microsoft SQL Server"
    assert normalize_skill_name("Node JS") == "Node.js"
    assert normalize_skill_name("Angular") == "Angular"


def test_unknown_category_is_preserved_as_custom_structured_category():
    category = SkillCategory(category="Observability", items=["Splunk"])

    assert category.category == "Observability"
    assert category.category_name == "Observability"
    assert category.category_id == "observability"
    assert category.migration_review_required is True


def test_unknown_legacy_category_is_preserved_as_custom_category():
    parsed = parse_legacy_skill_text("Observability: Splunk, App Insights")

    assert parsed.categories[0].category_id == "observability"
    assert parsed.categories[0].category_name == "Observability"
    assert parsed.categories[0].items == ["Splunk", "App Insights"]
    assert parsed.categories[0].migration_review_required is True


def test_known_aliases_map_and_ambiguous_aliases_preserve_content_for_review():
    mapped = parse_legacy_skill_text("DevOps & Tools: Jenkins, Docker")
    assert mapped.categories[0].category_id == "devops-cicd-containers"
    assert mapped.categories[0].category_name == "DevOps, CI/CD & Containers"
    assert mapped.categories[0].items == ["Jenkins", "Docker"]

    ambiguous = parse_legacy_skill_text("Node / JavaScript: Node.js")
    assert ambiguous.categories[0].category_id == "node-javascript"
    assert ambiguous.categories[0].category_name == "Node / JavaScript"
    assert ambiguous.categories[0].items == ["Node.js"]
    assert ambiguous.categories[0].migration_review_required is True


def test_ambiguous_legacy_content_is_preserved_for_review():
    parsed = parse_legacy_skill_text("C#, SQL Server")

    assert parsed.requires_review is True
    assert parsed.legacy_unparsed == "C#, SQL Server"
    assert parsed.categories[0].migration_review_required is True


def test_legacy_normalization_is_idempotent():
    first = parse_legacy_skill_text("Testing: MS-Test, NUnit")
    second = [SkillCategory(category=item.category_name, categoryId=item.category_id, categoryName=item.category_name, order=item.order, items=item.items) for item in first.categories]

    assert second[0].items == ["MSTest", "NUnit"]


def test_generate_resume_request_accepts_structured_categories_and_cross_category_duplicates():
    payload = canonical_payload()
    payload["skills"].append({"categoryId": "databases", "categoryName": "Databases", "order": 2, "items": ["SQL"]})
    request = GenerateResumeRequest.model_validate(payload)

    assert request.skills[0].category_id == "programming-languages"
    assert request.skills[2].items == ["SQL"]


def test_generate_resume_request_rejects_duplicate_category_ids_and_label_leaks():
    duplicate_id = canonical_payload()
    duplicate_id["skills"][1]["categoryId"] = "programming-languages"
    duplicate_id["skills"][1]["categoryName"] = "Programming Languages"
    with pytest.raises(ValidationError, match="Duplicate skill category IDs"):
      GenerateResumeRequest.model_validate(duplicate_id)

    label_leak = canonical_payload()
    label_leak["skills"][0]["items"] = ["Programming Languages: C#"]
    with pytest.raises(ValidationError, match="category labels"):
      GenerateResumeRequest.model_validate(label_leak)


def test_generate_resume_request_rejects_unknown_new_category_ids():
    payload = canonical_payload()
    payload["skills"][0] = {"categoryId": "frameworks", "categoryName": "Frameworks", "order": 0, "items": ["React"]}

    with pytest.raises(ValidationError, match="Unknown skill categoryId"):
        GenerateResumeRequest.model_validate(payload)
