import type { JobAnalysisResponse, JobKeywordAnalysisItem } from "../../resume/types";

export function keywordFixture(value: string, priorityScore = 80): JobKeywordAnalysisItem {
  return {
    id: `kw-${value.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
    value,
    normalizedValue: value.toLowerCase(),
    sourceType: "explicit",
    confidence: "high",
    directFromJD: true,
    evidenceText: value,
    sourceSentence: value,
    reason: "Explicitly present in the job description.",
    occurrenceCount: 1,
    term: value,
    category: "technical",
    priority: priorityScore >= 70 ? "high" : priorityScore >= 40 ? "medium" : "low",
    priorityScore,
    recruiterWeight: priorityScore,
    explicit: true,
  };
}

export const jobAnalysisFixture: JobAnalysisResponse = {
  roleInformation: {
    title: "Software Engineer IV",
    seniority: "Senior",
    experience: "Senior-level",
    domain: "Financial services trading platforms",
  },
  keywords: [keywordFixture("C#"), keywordFixture(".NET"), keywordFixture("Python"), keywordFixture("Trading")],
  explicitKeywords: [keywordFixture("C#"), keywordFixture(".NET"), keywordFixture("Python"), keywordFixture("Trading")],
  inferredKeywords: [],
  suggestedKeywords: [],
  excludedTerms: [],
  technicalSkills: {
    Languages: [keywordFixture("C#"), keywordFixture("Python")],
    Backend: [keywordFixture(".NET"), keywordFixture("REST APIs")],
  },
  leadershipCompetencies: [keywordFixture("Code reviews")],
  businessCompetencies: [keywordFixture("Trading")],
  responsibilities: [keywordFixture("Release management")],
  actionVerbs: ["Built", "Reviewed"],
  explicitAtsKeywords: [keywordFixture("C#"), keywordFixture(".NET"), keywordFixture("Python"), keywordFixture("Trading")],
  implicitInferredSkills: [],
  hiddenInferredSkills: [],
  atsFocusAreas: ["C#", ".NET", "REST APIs"],
  noiseTermsToExclude: [],
  totalExtractedKeywords: 4,
  analysisHash: "analysis-hash",
};
