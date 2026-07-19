import { describe, expect, it } from "vitest";
import {
  categoryDuplicateWarnings,
  hasCategoryPrefix,
  normalizeSkillCategories,
  normalizeSkillName,
  repairCategoryLabelSkills,
  resolveSkillCategoryDefinition,
  SKILL_CATEGORY_REGISTRY,
  splitSkillValues,
} from "./skillsData";

describe("skillsData", () => {
  it("exposes the approved controlled category registry only", () => {
    expect(SKILL_CATEGORY_REGISTRY.map((category) => category.categoryName)).toEqual([
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
    ]);
    expect(resolveSkillCategoryDefinition("C#")).toBeUndefined();
  });

  it("normalizes approved canonical spellings only", () => {
    expect(normalizeSkillName("MS-Test")).toBe("MSTest");
    expect(normalizeSkillName("MS SQL Server")).toBe("Microsoft SQL Server");
    expect(normalizeSkillName("ASP Net Core")).toBe("ASP.NET Core");
    expect(normalizeSkillName("Node JS")).toBe("Node.js");
    expect(normalizeSkillName("Angular")).toBe("Angular");
  });

  it("splits commas while preserving commas inside parentheses", () => {
    expect(splitSkillValues("Microsoft Azure (App Service, Azure SQL), C#, Node JS")).toEqual([
      "Microsoft Azure (App Service, Azure SQL)",
      "C#",
      "Node.js",
    ]);
  });

  it("migrates categorized legacy text into separate skill categories", () => {
    const result = normalizeSkillCategories(
      "Programming Languages: C#, JavaScript, SQL/T-SQL, Backend / .NET: ASP Net Core, Web API, Cloud: Microsoft Azure (App Service, Azure SQL)",
    );

    expect(result.requiresReview).toBe(false);
    expect(result.categories).toMatchObject([
      {
        categoryId: "programming-languages",
        categoryName: "Programming Languages",
        items: ["C#", "JavaScript", "SQL/T-SQL"],
      },
      {
        categoryId: "backend-development",
        categoryName: "Backend Development",
        items: ["ASP.NET Core", "Web API"],
      },
      {
        categoryId: "cloud-platforms-services",
        categoryName: "Cloud Platforms & Services",
        items: ["Microsoft Azure (App Service, Azure SQL)"],
      },
    ]);
  });

  it("keeps unknown structured categories and normalization idempotent", () => {
    const first = normalizeSkillCategories([{ category: "Observability", items: ["Splunk", "Splunk", "Node JS"] }]);
    const second = normalizeSkillCategories(first.categories);

    expect(first.categories[0]).toMatchObject({
      categoryId: "observability",
      categoryName: "Observability",
      items: ["Splunk", "Node.js"],
      migrationReviewRequired: true,
    });
    expect(second.categories).toEqual(first.categories);
  });

  it("preserves unknown legacy category headings as custom categories", () => {
    const result = normalizeSkillCategories("Observability: Splunk, App Insights");

    expect(result.categories[0]).toMatchObject({
      categoryId: "observability",
      categoryName: "Observability",
      items: ["Splunk", "App Insights"],
      migrationReviewRequired: true,
    });
  });

  it("maps clear legacy aliases and preserves ambiguous aliases for review", () => {
    const result = normalizeSkillCategories([
      { category: "Backend /.NET", items: ["ASP.NET Core"] },
      { category: "DevOps & Tools", items: ["Jenkins"] },
      { category: "Node / JavaScript", items: ["Node.js"] },
    ]);

    expect(result.categories).toMatchObject([
      { categoryId: "backend-development", categoryName: "Backend Development", items: ["ASP.NET Core"] },
      { categoryId: "devops-cicd-containers", categoryName: "DevOps, CI/CD & Containers", items: ["Jenkins"] },
      { categoryId: "node-javascript", categoryName: "Node / JavaScript", items: ["Node.js"], migrationReviewRequired: true },
    ]);
  });

  it("preserves ambiguous unstructured legacy text for review", () => {
    const result = normalizeSkillCategories("C#, SQL Server, Microsoft Azure (App Service, Azure SQL)");

    expect(result.requiresReview).toBe(true);
    expect(result.legacyUnparsed).toBe("C#, SQL Server, Microsoft Azure (App Service, Azure SQL)");
    expect(result.categories[0]).toMatchObject({
      categoryName: "Technical Skills",
      items: ["C#", "SQL Server", "Microsoft Azure (App Service, Azure SQL)"],
      migrationReviewRequired: true,
    });
  });

  it("detects category prefix leakage and exact cross-category duplicates", () => {
    expect(hasCategoryPrefix("Frontend: React")).toBe(true);
    expect(categoryDuplicateWarnings([
      { category: "Frontend", categoryId: "frontend", categoryName: "Frontend", order: 0, items: ["Next.js"] },
      { category: "Node / JavaScript", categoryId: "node-javascript", categoryName: "Node / JavaScript", order: 1, items: ["Next.js"] },
    ])).toEqual(["Next.js"]);
  });

  it("repairs label-prefixed skills into separate categories and stitches split parentheses", () => {
    const repaired = repairCategoryLabelSkills([
      {
        category: "Technical Skills",
        categoryId: "technical-skills",
        categoryName: "Technical Skills",
        order: 0,
        items: [
          "Programming Languages: C#",
          "JavaScript",
          "Backend /.NET: ASP.NET Core",
          "Frontend: React",
          "Cloud: Microsoft Azure (App Service",
          "Azure SQL)",
          "Databases: MS SQL Server",
        ],
      },
    ]);

    expect(repaired).toMatchObject([
      { categoryName: "Programming Languages", items: ["C#", "JavaScript"] },
      { categoryName: "Backend Development", items: ["ASP.NET Core"] },
      { categoryName: "Frontend Development", items: ["React"] },
      { categoryName: "Cloud Platforms & Services", items: ["Microsoft Azure (App Service, Azure SQL)"] },
      { categoryName: "Databases", items: ["Microsoft SQL Server"] },
    ]);
  });
});
