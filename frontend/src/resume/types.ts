export type AtsCoverageItem = {
  requirementId: string;
  requirementValue: string;
  category: string;
  classification: string;
};

export type AtsCoverageBreakdown = {
  supportedAndCovered: AtsCoverageItem[];
  supportedButNotRepresented: AtsCoverageItem[];
  adjacentUnsupported: AtsCoverageItem[];
  unmatched: AtsCoverageItem[];
  suggestedExcluded: AtsCoverageItem[];
};

export type AtsAnalysisBreakdown = {
  keywordMatch: number;
  formatting: number;
  readability: number;
  matchedKeywords: string[];
  missingKeywords: string[];
};

export type ResumeSuggestion = { text: string; points: number };

export type AtsAnalysis = {
  score: number;
  breakdown: AtsAnalysisBreakdown;
  coverage: AtsCoverageBreakdown;
  suggestions: ResumeSuggestion[];
};

export type GenerationMetadata = {
  model: string | null;
  durationMs: number;
  generatedAt: string;
  pipelineVersion: string;
};

export type GeneratedResumeResponse = {
  resumeId?: string;
  atsAnalysis?: AtsAnalysis;
  generationMetadata?: GenerationMetadata;
  resume: GeneratedResume;
  atsScore: number;
  breakdown: AtsAnalysisBreakdown & {
    coverage?: AtsCoverageBreakdown;
  };
  suggestions: ResumeSuggestion[];
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
  technicalRequirements?: TypedJobRequirement[];
  responsibilityRequirements?: TypedJobRequirement[];
  experienceRequirements?: TypedJobRequirement[];
  educationRequirements?: TypedJobRequirement[];
  certificationRequirements?: TypedJobRequirement[];
  leadershipRequirements?: TypedJobRequirement[];
  softSkillRequirements?: TypedJobRequirement[];
  domainRequirements?: TypedJobRequirement[];
  inferredRequirements?: TypedJobRequirement[];
  excludedNoiseTerms?: string[];
  analysisWarnings?: string[];
  normalizedRequirements?: NormalizedRequirements;
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

export type TypedJobRequirement = {
  requirementId: string;
  canonicalTerm: string;
  originalTerms: string[];
  category: string;
  requirementLevel: "required" | "preferred" | "responsibility" | "inferred";
  priority: "critical" | "high" | "medium" | "low";
  explicit: boolean;
  confidence: number;
  evidenceText: string;
  sourceSentence: string;
  reason: string;
};

export type NormalizedRequirements = {
  technicalRequirements: TypedJobRequirement[];
  responsibilityRequirements: TypedJobRequirement[];
  experienceRequirements: TypedJobRequirement[];
  educationRequirements: TypedJobRequirement[];
  certificationRequirements: TypedJobRequirement[];
  leadershipRequirements: TypedJobRequirement[];
  softSkillRequirements: TypedJobRequirement[];
  domainRequirements: TypedJobRequirement[];
  inferredRequirements: TypedJobRequirement[];
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

export type SummaryIntelligence = {
  summary: string;
  selectedTechnologies: string[];
  selectedCapabilities: string[];
  usedEvidenceIds: string[];
  excludedJdTerms: string[];
  riskFlags: string[];
  validationStatus: "valid" | "invalid" | "fallback";
  validationWarnings: string[];
  generationMode: "openai" | "retry" | "deterministic_fallback" | string;
  model: string;
  profileId: string;
  profileVersion: number;
  profileHash: string;
  jobDescriptionHash: string;
  targetRole: string;
  targetCompany: string;
  level: string;
  promptVersion?: string;
  modelConfigurationHash?: string;
  createdAt: string;
};

export type ExperiencePromptInput = {
  experienceId: string;
  roleContext: {
    roleTitle: string;
    companyName: string;
    clientName: string | null;
    isCurrentRole: boolean;
    roleFamily: string;
  };
  targetContext: {
    targetRole: string;
    targetCompany: string;
    level: string;
    targetThemes: string[];
  };
  approvedEvidence: Array<{
    evidenceId: string;
    evidenceType: string;
    text: string;
    sourceRecordId: string;
    projectId: string | null;
  }>;
  approvedTechnologies: Array<{ name: string; evidenceIds: string[] }>;
  approvedCapabilities: Array<{ name: string; evidenceIds: string[]; supportedRequirementIds: string[] }>;
  approvedMetrics: Array<{ value: string; context: string; evidenceIds: string[] }>;
  linkedProjects: Array<{ projectId: string; projectName: string; evidenceIds: string[]; technologies: string[]; approvedFacts: string[] }>;
  bulletThemes: string[];
  supportedRequirementIds: string[];
  excludedTerms: string[];
  writingRules: {
    bulletCount: number;
    maximumWordsPerBullet: number;
    useOnlyApprovedEvidence: boolean;
    doNotInventMetrics: boolean;
    doNotInventTechnologies: boolean;
    doNotInventLeadership: boolean;
    doNotInventArchitectureOwnership: boolean;
    doNotUseUnsupportedJdTerms: boolean;
    startWithActionVerb: boolean;
    avoidFirstPerson: boolean;
    avoidDuplicateOpenings: boolean;
    avoidGenericFiller: boolean;
  };
  plannerVersion: string;
  promptVersion: string;
  validationResult: { isValid: boolean; codes: string[]; warnings: string[] };
};

export type ExperienceIntelligence = {
  plannerVersion: string;
  roleFamily: string;
  roles: unknown[];
  experiencePromptInputs: ExperiencePromptInput[];
  roleIntelligence?: Array<{
    experienceId: string;
    bullets: GeneratedResumeBullet[];
    generationMode: string;
    model: string;
    promptVersion: string;
      validationStatus: string;
      warnings: string[];
      modelConfigurationHash?: string;
    }>;
    writerPromptVersion?: string;
    writerModel?: string;
    modelConfigurationHash?: string;
    overallValidationStatus?: string;
  createdAt?: string;
  warnings: string[];
  validationStatus: string;
};

export type ProfileMatchResponse = {
  matchSummary: ProfileMatchSummary;
  cacheVersion: string;
  cacheHit: boolean;
  profileId?: string;
  profileVersion?: number;
  profileUpdatedAt?: string;
  profileContentHash?: string;
  matchingAlgorithmVersion?: string;
  packageId?: string;
  jobDescriptionHash?: string;
  summaryIntelligence?: SummaryIntelligence | null;
  experienceIntelligence?: ExperienceIntelligence | null;
  validationStatus?: string;
  validationWarnings?: string[];
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

export type GeneratedResumeBullet = {
  bulletId: string;
  order: number;
  generatedText: string;
  currentText: string;
  userEdited: boolean;
  supportedRequirementIds: string[];
  supportingEvidenceIds: string[];
  validationStatus: string;
  warnings: string[];
};

export type StructuredGeneratedResume = {
  resumeId: string;
  userId: string;
  resumeHeader?: {
    fullName?: string;
    currentTitle?: string;
    email?: string;
    phone?: string;
    location?: string;
    linkedinUrl?: string;
    githubUrl?: string;
    portfolioUrl?: string;
  };
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
  enhancementHistory?: Array<Record<string, unknown>>;
  createdAt: string;
  updatedAt: string;
};

export type ResumeValidationResult = {
  isValid: boolean;
  errors: Array<{ code: string; severity: string; message: string; sectionId: string; contentId: string; evidenceIds: string[] }>;
  warnings: Array<{ code: string; severity: string; message: string; sectionId: string; contentId: string; evidenceIds: string[] }>;
  rejectedContentIds: string[];
};

export type SkillCategory = {
  category: string;
  categoryId?: string;
  categoryName?: string;
  order?: number;
  items: string[];
  migrationReviewRequired?: boolean;
  legacyUnparsed?: string;
};

export type GeneratedResume = {
  name: string;
  firstName?: string;
  lastName?: string;
  title: string;
  contact: {
    phone?: string;
    email?: string;
    location?: string;
    locationData?: StructuredLocation;
    linkedin?: string;
    github?: string;
    portfolio?: string;
  };
  summary?: string;
  skills: SkillCategory[];
  experience: Array<{
    experienceId?: string;
    company: string;
    clientName?: string | null;
    role: string;
    location?: string;
    locationData?: StructuredLocation;
    startDate?: string;
    startDateData?: ProfileExperienceDate;
    endDate?: string;
    endDateData?: ProfileExperienceDate | null;
    isCurrentRole?: boolean;
    rawNotes?: string;
    bullets: string[];
    metricFlags?: string[];
    responsibilities?: string[];
    achievements?: string[];
    technologies?: string[];
    metrics?: ExperienceMetric[];
    legacyNotes?: string;
    migrationReviewRequired?: boolean;
  }>;
  projects: Array<{
    projectId?: string;
    name: string;
    org?: string;
    link?: string;
    bullets: string[];
    technologies: string[];
    linkedExperienceIds?: string[];
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

export type StructuredLocation = {
  city: string;
  state?: string | null;
  country: string;
};

export type ProfileExperienceDate = {
  month: number;
  year: number;
};

export type ExperienceMetric = {
  metricId: string;
  label: string;
  value: string;
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

export type CandidateLocationSnapshot = {
  city: string;
  state?: string | null;
  country: string;
  displayValue: string;
};

export type CandidateSnapshot = {
  firstName: string;
  lastName: string;
  currentTitle: string;
  email: string;
  phone: string;
  location: CandidateLocationSnapshot;
};

export type SkillCategorySnapshot = {
  categoryId: string;
  categoryName: string;
  order: number;
  items: string[];
};

export type ExperienceDateSnapshot = {
  month: number;
  year: number;
  displayValue: string;
};

export type WorkExperienceSnapshot = {
  experienceId: string;
  companyName: string;
  clientName: string | null;
  roleTitle: string;
  location: CandidateLocationSnapshot;
  startDate: ExperienceDateSnapshot;
  endDate: ExperienceDateSnapshot | null;
  isCurrentRole: boolean;
};

export type ResumePreferencesSnapshot = {
  templateId: string;
  headerVisibility: {
    fullName: boolean;
    currentTitle: boolean;
    email: boolean;
    phone: boolean;
    location: boolean;
    linkedinUrl: boolean;
    githubUrl: boolean;
    portfolioUrl: boolean;
  };
  sectionVisibility: {
    summary: boolean;
    skills: boolean;
    experience: boolean;
    projects: boolean;
    education: boolean;
    certifications: boolean;
  };
};

export type ResumeGenerationSettingsSnapshot = {
  maximumPages: number;
  bulletsPerRecentRole: number;
  bulletsPerOlderRole: number;
  includeProjects: boolean;
  includeCertifications: boolean;
  includeUnmatchedKeywords: boolean;
  writingStyle: string;
};

export type GenerateResumeRequestPayload = {
  profileId: string;
  profileVersion: number;
  resumeIntelligencePackageId?: string;
  candidate: CandidateSnapshot;
  skills: SkillCategorySnapshot[];
  workExperience: WorkExperienceSnapshot[];
  job: {
    description: string;
    targetRole: string;
    targetCompany: string | null;
    level: string | null;
  };
  jobAnalysis?: JobAnalysisResponse | null;
  resumePreferences: ResumePreferencesSnapshot;
  generationSettings: ResumeGenerationSettingsSnapshot;
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

export type EnhancementMode =
  | "polish"
  | "concise"
  | "strengthen"
  | "ats_optimize"
  | "grammar"
  | "reduce_repetition"
  | "custom";

export type SectionEnhancementSuggestion = {
  suggestionId: string;
  sectionType: string;
  sectionId: string;
  originalText: string;
  enhancedText: string;
  explanation: string;
  supportingEvidenceIds: string[];
  supportedRequirementIds: string[];
  validationStatus: string;
  warnings: string[];
  model: string;
  promptVersion: string;
  createdAt: string;
};

export type SectionEnhancementResponse = {
  suggestions: SectionEnhancementSuggestion[];
  validationStatus: string;
  warnings: string[];
  resumeRevision: string;
};
