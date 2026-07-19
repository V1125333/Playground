import type { ProfileEvidenceItem, ProfileMatchResponse, RequirementMatch } from "../../resume/types";

export const evidenceFixture: ProfileEvidenceItem = {
  evidenceId: "ev-infosys-api",
  evidenceType: "work_experience",
  sourceRecordId: "experience-exp-infosys",
  sourceLabel: "Work Experience: Senior .NET Developer at Infosys",
  originalText:
    "Built C# and ASP.NET Core REST API enhancements with SQL Server. Led code reviews and Agile release validation, improving release quality by 20%.",
  matchedText: "C# .NET REST API SQL Server",
  companyName: "Infosys",
  roleTitle: "Senior .NET Developer",
  strengthScore: 95,
  reason: "Directly supports C#, .NET, APIs, SQL, and code review.",
};

export function requirementFixture(
  value: string,
  classification: RequirementMatch["classification"],
  evidence: ProfileEvidenceItem[] = [],
): RequirementMatch {
  return {
    requirementId: `req-${value.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
    requirementValue: value,
    requirementCategory: "technical",
    requirementPriority: classification === "unmatched" ? "medium" : "high",
    requirementPriorityScore: classification === "unmatched" ? 60 : 90,
    sourceType: "explicit",
    classification,
    matchScore: classification === "unmatched" ? 0 : classification === "adjacent" ? 45 : 95,
    evidence: classification === "exact" || classification === "normalized" ? evidence : [],
    adjacentEvidence: classification === "adjacent" ? evidence : [],
    isSafeToUse: classification !== "unmatched",
    requiresUserConfirmation: classification === "adjacent",
    reason:
      classification === "unmatched"
        ? "No stored profile evidence supports this requirement."
        : "Matched against stored profile evidence.",
  };
}

export const profileMatchFixture: ProfileMatchResponse = {
  cacheHit: false,
  cacheVersion: "test",
  profileId: "profile-123",
  profileVersion: 3,
  profileContentHash: "profile-hash",
  packageId: "package-123",
  jobDescriptionHash: "jd-hash",
  summaryIntelligence: {
    summary:
      "Senior .NET Developer with experience building enterprise applications using C#, .NET, REST APIs, and SQL Server. Focused on maintainable API delivery, database-backed features, and clear technical execution for business stakeholders.",
    selectedTechnologies: ["C#", ".NET", "REST APIs", "SQL Server"],
    selectedCapabilities: ["API delivery", "database-backed features"],
    usedEvidenceIds: ["ev-infosys-api"],
    excludedJdTerms: ["Azure", "Trading"],
    riskFlags: [],
    validationStatus: "valid",
    validationWarnings: [],
    generationMode: "openai",
    model: "gpt-5.5",
    profileId: "profile-123",
    profileVersion: 3,
    profileHash: "profile-hash",
    jobDescriptionHash: "jd-hash",
    targetRole: "Software Engineer IV",
    targetCompany: "Morgan Stanley",
    level: "Senior",
    promptVersion: "summary-generation-v2-intelligence",
    modelConfigurationHash: "test-summary-model-config",
    createdAt: "2026-07-18T00:00:00+00:00",
  },
  validationStatus: "valid",
  validationWarnings: [],
  matchSummary: {
    overallMatchScore: 72,
    coreRequirementScore: 75,
    supportingRequirementScore: 69,
    exactMatchCount: 2,
    normalizedMatchCount: 1,
    adjacentMatchCount: 1,
    unmatchedCount: 2,
    matchedRequirements: [
      requirementFixture("C#", "exact", [evidenceFixture]),
      requirementFixture(".NET", "normalized", [evidenceFixture]),
    ],
    partiallyMatchedRequirements: [requirementFixture("Cloud Development", "adjacent", [evidenceFixture])],
    unmatchedRequirements: [requirementFixture("Azure", "unmatched"), requirementFixture("Trading", "unmatched")],
    strengths: ["C# and .NET API delivery"],
    gaps: ["Azure", "Trading"],
    transferableStrengths: ["Enterprise release validation"],
    warnings: [],
  },
};
