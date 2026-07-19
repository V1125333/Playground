import type { SkillCategory } from "../resume/types";
import { clean } from "./profileData";

export type SkillCategoryDefinition = {
  categoryId: string;
  categoryName: string;
  group: "technical" | "professional";
  description: string;
  examples: string[];
  order: number;
};

export const SKILL_CATEGORY_REGISTRY: SkillCategoryDefinition[] = [
  {
    categoryId: "programming-languages",
    categoryName: "Programming Languages",
    group: "technical",
    description: "Programming, scripting, and query languages.",
    examples: ["C#", "Java", "Python", "JavaScript", "SQL"],
    order: 1,
  },
  {
    categoryId: "backend-development",
    categoryName: "Backend Development",
    group: "technical",
    description: "Server-side development technologies and runtime platforms.",
    examples: [".NET", "ASP.NET Core", "Node.js", "Java", "Spring Boot"],
    order: 2,
  },
  {
    categoryId: "frontend-development",
    categoryName: "Frontend Development",
    group: "technical",
    description: "Browser and user-interface technologies.",
    examples: ["React", "Angular", "HTML5", "CSS3"],
    order: 3,
  },
  {
    categoryId: "frameworks-libraries",
    categoryName: "Frameworks & Libraries",
    group: "technical",
    description: "Reusable software frameworks and development libraries.",
    examples: ["Entity Framework", "LINQ", "Next.js", "Redux"],
    order: 4,
  },
  {
    categoryId: "databases",
    categoryName: "Databases",
    group: "technical",
    description: "Relational, NoSQL, query, and database technologies.",
    examples: ["SQL Server", "PostgreSQL", "MongoDB", "Oracle"],
    order: 5,
  },
  {
    categoryId: "cloud-platforms-services",
    categoryName: "Cloud Platforms & Services",
    group: "technical",
    description: "Public cloud platforms and managed cloud services.",
    examples: ["Azure", "AWS", "Google Cloud", "Azure App Service"],
    order: 6,
  },
  {
    categoryId: "devops-cicd-containers",
    categoryName: "DevOps, CI/CD & Containers",
    group: "technical",
    description: "Build, delivery, automation, containerization, and deployment tools.",
    examples: ["Jenkins", "Docker", "Kubernetes", "GitHub Actions"],
    order: 7,
  },
  {
    categoryId: "testing-quality-assurance",
    categoryName: "Testing & Quality Assurance",
    group: "technical",
    description: "Unit testing, automated testing, quality, and code-analysis tools.",
    examples: ["NUnit", "MSTest", "Jest", "SonarQube"],
    order: 8,
  },
  {
    categoryId: "apis-integration",
    categoryName: "APIs & Integration",
    group: "technical",
    description: "API design, documentation, messaging, and system integration.",
    examples: ["REST APIs", "Swagger", "Postman", "GraphQL"],
    order: 9,
  },
  {
    categoryId: "data-engineering-etl",
    categoryName: "Data Engineering & ETL",
    group: "technical",
    description: "Data pipelines, orchestration, transformation, and ETL tools.",
    examples: ["SSIS", "Airflow", "ETL", "Data pipelines"],
    order: 10,
  },
  {
    categoryId: "data-analytics-reporting",
    categoryName: "Data Analytics & Reporting",
    group: "technical",
    description: "Business intelligence, reporting, visualization, and analytics tools.",
    examples: ["SSRS", "Power BI", "Tableau", "Dashboards"],
    order: 11,
  },
  {
    categoryId: "ai-machine-learning-generative-ai",
    categoryName: "AI, Machine Learning & Generative AI",
    group: "technical",
    description: "Machine learning, deep learning, LLM, and AI-development technologies.",
    examples: ["LLMs", "OpenAI API", "TensorFlow", "Python ML"],
    order: 12,
  },
  {
    categoryId: "architecture-system-design",
    categoryName: "Architecture & System Design",
    group: "technical",
    description: "Software architecture, distributed systems, and design practices.",
    examples: ["System design", "Microservices", "Scalability", "OOP"],
    order: 13,
  },
  {
    categoryId: "security-identity",
    categoryName: "Security & Identity",
    group: "technical",
    description: "Application security, authentication, authorization, and identity technologies.",
    examples: ["OAuth", "JWT", "SSO", "Authorization"],
    order: 14,
  },
  {
    categoryId: "tools-development-environments",
    categoryName: "Tools & Development Environments",
    group: "technical",
    description: "IDEs, development utilities, and engineering productivity tools.",
    examples: ["Visual Studio", "Git", "Postman", "Swagger"],
    order: 15,
  },
  {
    categoryId: "software-development-practices",
    categoryName: "Software Development Practices",
    group: "professional",
    description: "Code review, debugging, performance tuning, documentation, and engineering practices.",
    examples: ["Code reviews", "Debugging", "Documentation", "Performance tuning"],
    order: 16,
  },
  {
    categoryId: "methodologies-ways-of-working",
    categoryName: "Methodologies & Ways of Working",
    group: "professional",
    description: "Agile, Scrum, Kanban, DevOps culture, and delivery methodologies.",
    examples: ["Agile", "Scrum", "Kanban", "SDLC"],
    order: 17,
  },
  {
    categoryId: "business-domain-knowledge",
    categoryName: "Business & Domain Knowledge",
    group: "professional",
    description: "Industry-specific or business-process knowledge.",
    examples: ["Healthcare workflows", "Compliance", "Claims", "Finance"],
    order: 18,
  },
  {
    categoryId: "communication-collaboration",
    categoryName: "Communication & Collaboration",
    group: "professional",
    description: "Stakeholder communication, teamwork, facilitation, and collaboration skills.",
    examples: ["Stakeholder communication", "Teamwork", "Facilitation"],
    order: 19,
  },
  {
    categoryId: "leadership-management",
    categoryName: "Leadership & Management",
    group: "professional",
    description: "Mentoring, team leadership, planning, and people-management skills.",
    examples: ["Mentoring", "Planning", "Technical leadership"],
    order: 20,
  },
  {
    categoryId: "languages",
    categoryName: "Languages",
    group: "professional",
    description: "Spoken and written human languages.",
    examples: ["English", "Spanish", "Hindi", "Telugu"],
    order: 21,
  },
  {
    categoryId: "other-specialized-skills",
    categoryName: "Other Specialized Skills",
    group: "professional",
    description: "Relevant specialized skills that do not fit another available category.",
    examples: ["Specialized platforms", "Niche tools", "Domain-specific systems"],
    order: 22,
  },
];

export const STANDARD_SKILL_CATEGORIES = SKILL_CATEGORY_REGISTRY.map((category) => category.categoryName);

const CATEGORY_ALIASES: Record<string, string | null> = {
  "backend / .net": "backend-development",
  "backend /.net": "backend-development",
  ".net backend": "backend-development",
  backend: "backend-development",
  "frontend": "frontend-development",
  "ui development": "frontend-development",
  cloud: "cloud-platforms-services",
  "cloud technologies": "cloud-platforms-services",
  "devops & tools": "devops-cicd-containers",
  devops: "devops-cicd-containers",
  "ci/cd": "devops-cicd-containers",
  testing: "testing-quality-assurance",
  "unit testing": "testing-quality-assurance",
  "data & reporting": "data-analytics-reporting",
  reporting: "data-analytics-reporting",
  methodologies: "methodologies-ways-of-working",
  "agile methodologies": "methodologies-ways-of-working",
  "node / javascript": null,
  "node / js": null,
  "node.js": null,
};

const CANONICAL_SKILLS: Record<string, string> = {
  "ms-test": "MSTest",
  "ms test": "MSTest",
  "mstest": "MSTest",
  "ms sql server": "Microsoft SQL Server",
  "microsoft sql server": "Microsoft SQL Server",
  "asp net core": "ASP.NET Core",
  "asp.net core": "ASP.NET Core",
  "node js": "Node.js",
  "node.js": "Node.js",
};

const CATEGORY_BY_ID = new Map(SKILL_CATEGORY_REGISTRY.map((category) => [category.categoryId, category]));
const CATEGORY_BY_NAME = new Map(SKILL_CATEGORY_REGISTRY.map((category) => [category.categoryName.toLowerCase(), category]));
const PREFIX_CATEGORY_NAMES = [
  ...STANDARD_SKILL_CATEGORIES,
  ...Object.keys(CATEGORY_ALIASES).map((alias) => canonicalDisplayAlias(alias)),
];

export type SkillCategoryMigrationResult = {
  categories: SkillCategory[];
  requiresReview: boolean;
  legacyUnparsed?: string;
};

export function normalizeSkillName(value: string): string {
  const trimmed = clean(value).replace(/\s+\/\s+/g, " / ");
  return CANONICAL_SKILLS[trimmed.toLowerCase()] ?? trimmed;
}

export function skillCategoryId(categoryName: string): string {
  return (resolveSkillCategoryDefinition(categoryName)?.categoryId ?? slugify(categoryName)) || `skill-category-${Date.now()}`;
}

export function approvedSkillCategoryDefinition(categoryId: string): SkillCategoryDefinition | undefined {
  return CATEGORY_BY_ID.get(categoryId.trim().toLowerCase());
}

export function resolveSkillCategoryDefinition(value: string): SkillCategoryDefinition | undefined {
  const normalized = normalizeCategoryKey(value);
  const byName = CATEGORY_BY_NAME.get(normalized);
  if (byName) return byName;
  const byId = CATEGORY_BY_ID.get(normalized);
  if (byId) return byId;
  const aliasTarget = CATEGORY_ALIASES[normalized];
  return aliasTarget ? CATEGORY_BY_ID.get(aliasTarget) : undefined;
}

export function isAmbiguousSkillCategoryAlias(value: string): boolean {
  return CATEGORY_ALIASES[normalizeCategoryKey(value)] === null;
}

export function splitSkillValues(value: string): string[] {
  const output: string[] = [];
  let current = "";
  let depth = 0;
  for (const character of value) {
    if (character === "(") depth += 1;
    if (character === ")" && depth > 0) depth -= 1;
    if (character === "," && depth === 0) {
      output.push(current);
      current = "";
      continue;
    }
    current += character;
  }
  output.push(current);
  return output.map(normalizeSkillName).filter(Boolean);
}

export function createSkillCategory(categoryName = "Other Specialized Skills", items: string[] = [], order = 0): SkillCategory {
  const definition = resolveSkillCategoryDefinition(categoryName);
  const canonicalCategory = definition?.categoryName ?? clean(categoryName);
  return {
    category: canonicalCategory,
    categoryId: definition?.categoryId ?? skillCategoryId(canonicalCategory),
    categoryName: canonicalCategory,
    order,
    items: dedupeSkills(items),
    migrationReviewRequired: !definition && Boolean(canonicalCategory),
  };
}

export function createApprovedSkillCategory(categoryId: string, order = 0): SkillCategory {
  const definition = approvedSkillCategoryDefinition(categoryId);
  if (!definition) {
    throw new Error(`Unknown approved skill category ID: ${categoryId}`);
  }
  return {
    category: definition.categoryName,
    categoryId: definition.categoryId,
    categoryName: definition.categoryName,
    order,
    items: [],
    migrationReviewRequired: false,
  };
}

export function normalizeSkillCategories(value: unknown): SkillCategoryMigrationResult {
  if (Array.isArray(value)) {
    return normalizeStructuredCategories(value);
  }
  if (typeof value === "string") {
    return parseLegacySkillText(value);
  }
  return { categories: [], requiresReview: false };
}

export function categoryDuplicateWarnings(categories: SkillCategory[]): string[] {
  const ownership = new Map<string, string>();
  const duplicates = new Set<string>();
  for (const category of categories) {
    for (const item of category.items) {
      const key = normalizeSkillName(item).toLowerCase();
      if (ownership.has(key) && ownership.get(key) !== category.categoryName) {
        duplicates.add(normalizeSkillName(item));
      } else {
        ownership.set(key, category.categoryName ?? category.category);
      }
    }
  }
  return [...duplicates].sort((left, right) => left.localeCompare(right));
}

export function hasCategoryPrefix(value: string, categories = PREFIX_CATEGORY_NAMES): boolean {
  return Boolean(extractCategoryPrefix(value, categories));
}

export function categoryLabelIssueCount(categories: SkillCategory[]): number {
  return categories.reduce((count, category) => count + category.items.filter((item) => extractCategoryPrefix(item)).length, 0);
}

export function repairCategoryLabelSkills(categories: SkillCategory[]): SkillCategory[] {
  const repaired = new Map<string, SkillCategory>();
  let activeCategoryName = "";

  const appendSkill = (categoryName: string, skill: string) => {
    const normalizedSkill = normalizeSkillName(skill);
    if (!categoryName || !normalizedSkill) return;
    const category = createSkillCategory(categoryName, [], repaired.size);
    const id = category.categoryId ?? skillCategoryId(category.categoryName ?? category.category);
    const existing = repaired.get(id) ?? category;
    const itemKeys = new Set(existing.items.map((item) => item.toLowerCase()));
    if (!itemKeys.has(normalizedSkill.toLowerCase())) {
      existing.items = [...existing.items, normalizedSkill];
    }
    repaired.set(id, existing);
  };

  for (const category of categories) {
    const fallbackCategory = category.categoryName ?? category.category;
    activeCategoryName = fallbackCategory;
    for (let index = 0; index < category.items.length; index += 1) {
      const item = category.items[index];
      const prefixed = extractCategoryPrefix(item);
      if (prefixed) {
        activeCategoryName = prefixed.categoryName;
        let value = prefixed.value;
        while (hasOpenParenthesis(value) && index + 1 < category.items.length && !extractCategoryPrefix(category.items[index + 1])) {
          index += 1;
          value = `${value}, ${category.items[index]}`;
        }
        appendSkill(activeCategoryName, value);
      } else {
        appendSkill(activeCategoryName, item);
      }
    }
  }

  return [...repaired.values()].map((category, index) => ({
    ...category,
    order: index,
    migrationReviewRequired: false,
    legacyUnparsed: undefined,
  }));
}

function normalizeStructuredCategories(value: unknown[]): SkillCategoryMigrationResult {
  const merged = new Map<string, SkillCategory>();
  let requiresReview = false;
  let legacyUnparsed = "";

  value.forEach((raw, index) => {
    const source = raw as Partial<SkillCategory> & { categoryName?: string; categoryId?: string };
    const originalName = clean(source.categoryName ?? source.category ?? "");
    const originalId = clean(source.categoryId ?? "");
    const definition = approvedSkillCategoryDefinition(originalId) ?? resolveSkillCategoryDefinition(originalName);
    const ambiguous = !definition && isAmbiguousSkillCategoryAlias(originalName);
    const unknown = !definition && Boolean(originalName);
    const categoryName = definition?.categoryName ?? originalName;
    const categoryId = (definition?.categoryId ?? originalId) || skillCategoryId(categoryName);
    const items = dedupeSkills(source.items ?? []);
    const migrationReviewRequired = Boolean(
      source.migrationReviewRequired
      || items.some((item) => hasCategoryPrefix(item))
      || ambiguous
      || unknown
      || (definition && originalName && originalName.toLowerCase() !== definition.categoryName.toLowerCase()),
    );
    if (migrationReviewRequired) requiresReview = true;
    if (source.legacyUnparsed && !legacyUnparsed) legacyUnparsed = source.legacyUnparsed;
    if (!categoryName) return;

    const existing = merged.get(categoryId);
    if (existing) {
      merged.set(categoryId, {
        ...existing,
        items: dedupeSkills([...existing.items, ...items]),
        migrationReviewRequired: Boolean(existing.migrationReviewRequired || migrationReviewRequired),
        legacyUnparsed: existing.legacyUnparsed || source.legacyUnparsed,
      });
      return;
    }

    merged.set(categoryId, {
      category: categoryName,
      categoryId,
      categoryName,
      order: Number.isInteger(source.order) ? Number(source.order) : index,
      items,
      migrationReviewRequired,
      legacyUnparsed: source.legacyUnparsed,
    });
  });

  const categories = [...merged.values()]
    .sort((left, right) => (left.order ?? 0) - (right.order ?? 0))
    .map((category, index) => ({ ...category, order: index }));

  return {
    categories,
    requiresReview: requiresReview || categories.some((category) => Boolean(category.migrationReviewRequired)),
    legacyUnparsed: legacyUnparsed || undefined,
  };
}

function parseLegacySkillText(value: string): SkillCategoryMigrationResult {
  const raw = value.trim();
  if (!raw) return { categories: [], requiresReview: false };
  const categoryPattern = /(^|\n|,)\s*([^,\n:]{2,64})\s*:/gi;
  const matches = [...raw.matchAll(categoryPattern)];
  if (!matches.length) {
    const items = dedupeSkills(splitSkillValues(raw));
    return {
      categories: items.length ? [{ ...createSkillCategory("Technical Skills", items, 0), migrationReviewRequired: true, legacyUnparsed: raw }] : [],
      requiresReview: Boolean(raw),
      legacyUnparsed: raw,
    };
  }

  const categories: SkillCategory[] = [];
  let unparsed = raw.slice(0, matches[0].index ?? 0).trim();
  for (let index = 0; index < matches.length; index += 1) {
    const match = matches[index];
    const next = matches[index + 1];
    const categoryName = clean(match[2]);
    const contentStart = (match.index ?? 0) + match[0].length;
    const contentEnd = next?.index ?? raw.length;
    const content = raw.slice(contentStart, contentEnd).replace(/^[,\s]+|[,\s]+$/g, "");
    const category = createSkillCategory(categoryName, splitSkillValues(content).filter((item) => !hasCategoryPrefix(item)), categories.length);
    if (category.items.length) categories.push(category);
  }
  return normalizeSkillCategories(categories.map((category) => ({
    ...category,
    migrationReviewRequired: category.migrationReviewRequired || Boolean(unparsed),
    legacyUnparsed: unparsed || category.legacyUnparsed,
  })));
}

function extractCategoryPrefix(value: string, categories = PREFIX_CATEGORY_NAMES): { categoryName: string; value: string } | null {
  const normalized = value.trim();
  for (const category of categories) {
    const escaped = category
      .split("/")
      .map((part) => part.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+"))
      .join("\\s*/\\s*");
    const match = normalized.match(new RegExp(`^${escaped}\\s*:\\s*(.+)$`, "i"));
    if (match?.[1]) {
      return { categoryName: resolveSkillCategoryDefinition(category)?.categoryName ?? category, value: match[1] };
    }
  }
  return null;
}

function hasOpenParenthesis(value: string): boolean {
  return (value.match(/\(/g)?.length ?? 0) > (value.match(/\)/g)?.length ?? 0);
}

function dedupeSkills(items: string[]): string[] {
  const seen = new Set<string>();
  const output: string[] = [];
  for (const item of items.map(normalizeSkillName)) {
    const key = item.toLowerCase();
    if (item && !seen.has(key)) {
      seen.add(key);
      output.push(item);
    }
  }
  return output;
}

function normalizeCategoryKey(value: string): string {
  return clean(value).replace(/\s+\/\s+/g, " / ").toLowerCase();
}

function canonicalDisplayAlias(value: string): string {
  return value
    .split(" ")
    .map((part) => part ? `${part[0].toUpperCase()}${part.slice(1)}` : part)
    .join(" ");
}

function slugify(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}
