export type GeneratedResumeResponse = {
  resume: GeneratedResume;
  atsScore: number;
  breakdown: {
    keywordMatch: number;
    formatting: number;
    readability: number;
    matchedKeywords: string[];
    missingKeywords: string[];
  };
  suggestions: Array<{ text: string; points: number }>;
  aiMetrics?: {
    generationTimeMs: number;
    aiCost: number;
    tokensUsed: number;
    modelsUsed: string[];
    cacheUsed: boolean;
    atsScore: number;
    validationScore: number;
  };
  structuredResume?: StructuredGeneratedResume | null;
  validationResult?: ResumeValidationResult | null;
  persistedResumeId?: string;
  semanticPlan?: {
    exactKeywords: Array<{ term: string; category: string; priority: string; source: string }>;
    semanticKeywords: Array<{ term: string; category: string; priority: string; source: string }>;
    requirementGroups: Array<{
      name: string;
      category: string;
      priority: string;
      exactKeywords: string[];
      semanticKeywords: string[];
      relatedConcepts: string[];
    }>;
    candidateEvidenceMap: Array<{
      requirement: string;
      confidence: "strong" | "partial" | "missing" | string;
      evidence: string[];
      supportedKeywords: string[];
      missingKeywords: string[];
      suggestedResumeUse: string[];
    }>;
    missingRequirements: string[];
    weakRequirements: string[];
    atsKeywordPlan: Array<{
      keyword: string;
      priority: string;
      targetSections: string[];
      confidence: "strong" | "partial" | "missing" | string;
      guidance: string;
    }>;
  };
};

export type KeywordSourceType = "explicit" | "inferred" | "suggested";

export type KeywordConfidence = "high" | "medium" | "low";

export type KeywordPriority = "high" | "medium" | "low";

export type JobKeywordAnalysisItem = {
  id: string;
  value: string;
  normalizedValue: string;
  sourceType: KeywordSourceType;
  confidence: KeywordConfidence;
  directFromJD: boolean;
  evidenceText?: string | null;
  sourceSentence?: string | null;
  reason?: string | null;
  occurrenceCount: number;
  // Deprecated compatibility fields. Current UI still consumes these until the display layer is migrated.
  term: string;
  category: string;
  priority: KeywordPriority;
  priorityScore: number;
  recruiterWeight: number;
  explicit: boolean;
};

export type ExcludedKeywordItem = {
  value: string;
  normalizedValue: string;
  reason: string;
  originalSourceType?: KeywordSourceType | null;
};

export type JobAnalysisResponse = {
  roleInformation: {
    title: string;
    seniority: string;
    experience: string;
    domain: string;
  };
  keywords: JobKeywordAnalysisItem[];
  explicitKeywords: JobKeywordAnalysisItem[];
  inferredKeywords: JobKeywordAnalysisItem[];
  suggestedKeywords: JobKeywordAnalysisItem[];
  excludedTerms: ExcludedKeywordItem[];
  technicalSkills: Record<string, JobKeywordAnalysisItem[]>;
  leadershipCompetencies: JobKeywordAnalysisItem[];
  businessCompetencies: JobKeywordAnalysisItem[];
  responsibilities: JobKeywordAnalysisItem[];
  actionVerbs: string[];
  explicitAtsKeywords: JobKeywordAnalysisItem[];
  implicitInferredSkills: JobKeywordAnalysisItem[];
  hiddenInferredSkills: JobKeywordAnalysisItem[];
  atsFocusAreas: string[];
  noiseTermsToExclude: string[];
  totalExtractedKeywords: number;
  analysisHash: string;
};

export type MatchClassification = "exact" | "normalized" | "adjacent" | "unmatched";

export type ProfileEvidenceType =
  | "skill"
  | "work_experience"
  | "achievement"
  | "project"
  | "education"
  | "certification"
  | "summary";

export type ProfileEvidenceItem = {
  evidenceId: string;
  evidenceType: ProfileEvidenceType;
  sourceRecordId?: string | null;
  sourceLabel: string;
  originalText: string;
  matchedText?: string | null;
  companyName?: string | null;
  roleTitle?: string | null;
  projectName?: string | null;
  strengthScore: number;
  reason: string;
};

export type RequirementMatch = {
  requirementId: string;
  requirementValue: string;
  requirementCategory: string;
  requirementPriority: KeywordPriority;
  requirementPriorityScore: number;
  sourceType: KeywordSourceType;
  classification: MatchClassification;
  matchScore: number;
  evidence: ProfileEvidenceItem[];
  adjacentEvidence: ProfileEvidenceItem[];
  isSafeToUse: boolean;
  requiresUserConfirmation: boolean;
  reason: string;
};

export type ProfileMatchSummary = {
  overallMatchScore: number;
  coreRequirementScore: number;
  supportingRequirementScore: number;
  exactMatchCount: number;
  normalizedMatchCount: number;
  adjacentMatchCount: number;
  unmatchedCount: number;
  matchedRequirements: RequirementMatch[];
  partiallyMatchedRequirements: RequirementMatch[];
  unmatchedRequirements: RequirementMatch[];
  strengths: string[];
  gaps: string[];
  transferableStrengths: string[];
  warnings: string[];
};

export type ProfileMatchResponse = {
  matchSummary: ProfileMatchSummary;
  cacheVersion: string;
  cacheHit: boolean;
};

export type GeneratedResumeSection = {
  sectionId: string;
  type: string;
  title: string;
  order: number;
  visible: boolean;
  content: unknown;
  provenance: {
    supportingEvidenceIds: string[];
    supportedRequirementIds: string[];
    generationMethod: string;
    validationStatus: string;
    warnings: string[];
  };
};

export type StructuredGeneratedResume = {
  resumeId: string;
  userId: string;
  resumeName: string;
  targetJobTitle: string;
  targetCompany: string;
  jobDescription: string;
  profileId: string;
  profileVersion: number;
  profileContentHash: string;
  jobAnalysisVersion: string;
  matchingAlgorithmVersion: string;
  generationAlgorithmVersion: string;
  templateId: string;
  versionNumber: number;
  status: string;
  matchScore: number;
  missingRequirements: string[];
  warnings: string[];
  contact: GeneratedResume["contact"];
  sections: GeneratedResumeSection[];
  createdAt: string;
  updatedAt: string;
};

export type ResumeValidationResult = {
  isValid: boolean;
  errors: Array<{ code: string; severity: string; message: string; sectionId: string; contentId: string; evidenceIds: string[] }>;
  warnings: Array<{ code: string; severity: string; message: string; sectionId: string; contentId: string; evidenceIds: string[] }>;
  rejectedContentIds: string[];
};

export type GeneratedResume = {
  name: string;
  title: string;
  contact: {
    phone?: string;
    email?: string;
    location?: string;
    linkedin?: string;
    github?: string;
    portfolio?: string;
  };
  summary?: string;
  skills: Array<{ category: string; items: string[] }>;
  experience: Array<{
    experienceId?: string;
    company: string;
    role: string;
    location?: string;
    startDate?: string;
    endDate?: string;
    rawNotes?: string;
    bullets: string[];
    metricFlags?: string[];
  }>;
  projects: Array<{
    projectId?: string;
    name: string;
    org?: string;
    link?: string;
    bullets: string[];
    technologies: string[];
  }>;
  education: Array<{
    educationId?: string;
    degree: string;
    institution: string;
    location?: string;
    gradYear?: string;
    gpa?: string;
  }>;
  certifications: Array<{ certificationId?: string; name: string; issuer?: string; issuedDate?: string; expiryDate?: string }>;
};

export type CandidateProfileRecord = {
  profileId: string;
  userId: string;
  profileName: string;
  profileData: GeneratedResume;
  schemaVersion: number;
  profileVersion: number;
  completenessScore: number;
  contentHash: string;
  createdAt: string;
  updatedAt: string;
};

export type StructuredResumeRecord = {
  resumeId: string;
  userId: string;
  profileId: string;
  profileVersion: number;
  profileContentHash: string;
  resumeName: string;
  targetJobTitle: string;
  targetCompany: string;
  jobDescription: string;
  jobAnalysisJson: Record<string, unknown>;
  profileMatchJson: Record<string, unknown>;
  resumeJson: StructuredGeneratedResume;
  templateId: string;
  matchScore: number;
  generationAlgorithmVersion: string;
  status: string;
  versionNumber: number;
  parentResumeId: string;
  createdAt: string;
  updatedAt: string;
};
