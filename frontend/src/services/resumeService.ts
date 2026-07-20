import type {
  AtsAnalysis,
  AtsCoverageBreakdown,
  GenerateResumeRequestPayload,
  GeneratedResumeResponse,
  GenerationMetadata,
  JobAnalysisResponse,
  ProfileMatchResponse,
  SectionEnhancementResponse,
  StructuredGeneratedResume,
  StructuredResumeRecord,
} from "../resume/types";

const authHeaders = (token: string) => ({
  "Content-Type": "application/json",
  Authorization: `Bearer ${token}`,
});

async function requestJson<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      Authorization: `Bearer ${token}`,
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(formatApiErrorDetail(error?.detail, "Resume request failed."));
  }
  return (await response.json()) as T;
}

function formatApiErrorDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (!detail || typeof detail !== "object") return fallback;

  const payload = detail as { message?: unknown; details?: unknown };
  const message = typeof payload.message === "string" && payload.message.trim() ? payload.message.trim() : fallback;
  if (!Array.isArray(payload.details) || payload.details.length === 0) return message;

  const detailMessages = payload.details
    .map((item) => {
      if (!item || typeof item !== "object") return "";
      const value = (item as { message?: unknown }).message;
      return typeof value === "string" ? value.trim() : "";
    })
    .filter(Boolean);
  return detailMessages.length ? `${message} ${detailMessages.join(" ")}` : message;
}

export async function generateResume(token: string, payload: GenerateResumeRequestPayload | Record<string, unknown>): Promise<GeneratedResumeResponse> {
  const response = await requestJson<GeneratedResumeResponse>("/api/resumes/generate", token, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  return normalizeGenerateResumeResponse(response);
}

export function normalizeGenerateResumeResponse(response: GeneratedResumeResponse): GeneratedResumeResponse {
  const legacyBreakdown = response.breakdown ?? {
    keywordMatch: 0,
    formatting: 0,
    readability: 0,
    matchedKeywords: [],
    missingKeywords: [],
  };
  const score = response.atsAnalysis?.score ?? response.atsScore ?? 0;
  const coverage = response.atsAnalysis?.coverage ?? legacyBreakdown.coverage ?? emptyCoverage();
  const breakdown = response.atsAnalysis?.breakdown ?? {
    keywordMatch: legacyBreakdown.keywordMatch ?? 0,
    formatting: legacyBreakdown.formatting ?? 0,
    readability: legacyBreakdown.readability ?? 0,
    matchedKeywords: legacyBreakdown.matchedKeywords ?? [],
    missingKeywords: legacyBreakdown.missingKeywords ?? [],
  };
  const suggestions = response.atsAnalysis?.suggestions ?? response.suggestions ?? [];
  const resumeId = response.resumeId ?? response.persistedResumeId ?? response.structuredResume?.resumeId ?? "";
  const generationMetadata = response.generationMetadata ?? metadataFromLegacy(response);
  const aiMetrics = response.aiMetrics ?? {
    generationTimeMs: generationMetadata.durationMs,
    aiCost: 0,
    tokensUsed: 0,
    modelsUsed: generationMetadata.model ? [generationMetadata.model] : [],
    cacheUsed: false,
    atsScore: score,
    validationScore: response.validationResult?.isValid === false ? 0 : 100,
  };
  const atsAnalysis: AtsAnalysis = {
    score,
    breakdown,
    coverage,
    suggestions,
  };

  return {
    ...response,
    resumeId,
    persistedResumeId: resumeId,
    atsAnalysis,
    atsScore: score,
    breakdown: { ...breakdown, coverage },
    suggestions,
    generationMetadata,
    aiMetrics: {
      ...aiMetrics,
      generationTimeMs: generationMetadata.durationMs,
      modelsUsed: generationMetadata.model ? [generationMetadata.model] : aiMetrics.modelsUsed,
      atsScore: score,
    },
  };
}

export async function analyzeJob(token: string, payload: Record<string, unknown>): Promise<JobAnalysisResponse> {
  return requestJson<JobAnalysisResponse>("/api/resumes/analyze", token, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
}

export async function matchProfile(token: string, payload: Record<string, unknown>): Promise<ProfileMatchResponse> {
  return requestJson<ProfileMatchResponse>("/api/resumes/match-profile", token, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
}

export async function listResumes(token: string): Promise<StructuredResumeRecord[]> {
  return requestJson<StructuredResumeRecord[]>("/api/resumes", token);
}

export async function getResume(token: string, resumeId: string): Promise<StructuredResumeRecord> {
  return requestJson<StructuredResumeRecord>(`/api/resumes/${resumeId}`, token);
}

export async function updateResume(token: string, resumeId: string, payload: { resumeJson: StructuredGeneratedResume; status?: string }): Promise<StructuredResumeRecord> {
  return requestJson<StructuredResumeRecord>(`/api/resumes/${resumeId}`, token, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
}

export async function saveResumeVersion(token: string, resumeId: string): Promise<StructuredResumeRecord> {
  return requestJson<StructuredResumeRecord>(`/api/resumes/${resumeId}/versions`, token, { method: "POST" });
}

export async function listResumeVersions(token: string, resumeId: string): Promise<StructuredResumeRecord[]> {
  return requestJson<StructuredResumeRecord[]>(`/api/resumes/${resumeId}/versions`, token);
}

export async function deleteResume(token: string, resumeId: string): Promise<void> {
  const response = await fetch(`/api/resumes/${resumeId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(formatApiErrorDetail(error?.detail, "Resume delete failed."));
  }
}

export async function enhanceResumeSection(
  token: string,
  resumeId: string,
  payload: Record<string, unknown>,
): Promise<SectionEnhancementResponse> {
  return requestJson<SectionEnhancementResponse>(`/api/resumes/${resumeId}/enhance-section`, token, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
}

export async function applySectionEnhancement(
  token: string,
  resumeId: string,
  payload: Record<string, unknown>,
): Promise<StructuredResumeRecord> {
  return requestJson<StructuredResumeRecord>(`/api/resumes/${resumeId}/apply-section-enhancement`, token, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
}

export type ResumeExportOptions = {
  templateId?: string;
  paperSize?: "letter" | "a4";
  filename?: string;
};

export type ResumeExportResult = {
  blob: Blob;
  filename: string;
  contentType: string;
  resumeVersion: string;
  rendererVersion: string;
};

export async function exportResumePdf(token: string, resumeId: string, options: ResumeExportOptions = {}): Promise<ResumeExportResult> {
  return exportResume(token, resumeId, "pdf", options);
}

export async function exportResumeDocx(token: string, resumeId: string, options: ResumeExportOptions = {}): Promise<ResumeExportResult> {
  return exportResume(token, resumeId, "docx", options);
}

async function exportResume(token: string, resumeId: string, format: "pdf" | "docx", options: ResumeExportOptions): Promise<ResumeExportResult> {
  const params = new URLSearchParams();
  if (options.templateId) params.set("template_id", options.templateId);
  if (options.paperSize) params.set("paper_size", options.paperSize);
  if (options.filename) params.set("filename", options.filename);
  const query = params.toString();
  const response = await fetch(`/api/resumes/${resumeId}/export/${format}${query ? `?${query}` : ""}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      const error = await response.json().catch(() => null);
      throw new Error(formatApiErrorDetail(error?.detail, `Resume ${format.toUpperCase()} export failed.`));
    }
    throw new Error(`Resume ${format.toUpperCase()} export failed.`);
  }
  const contentType = response.headers.get("content-type") ?? "";
  const expected = format === "pdf" ? "application/pdf" : "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  if (!contentType.includes(expected)) {
    throw new Error(`Resume export returned an invalid ${format.toUpperCase()} file.`);
  }
  const blob = await response.blob();
  if (blob.size === 0) {
    throw new Error(`Resume ${format.toUpperCase()} export returned an empty file.`);
  }
  return {
    blob,
    filename: filenameFromDisposition(response.headers.get("content-disposition")) ?? `Resume.${format}`,
    contentType,
    resumeVersion: response.headers.get("x-resume-version") ?? "",
    rendererVersion: response.headers.get("x-export-renderer-version") ?? "",
  };
}

function filenameFromDisposition(value: string | null): string | null {
  const match = value?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

function emptyCoverage(): AtsCoverageBreakdown {
  return {
    supportedAndCovered: [],
    supportedButNotRepresented: [],
    adjacentUnsupported: [],
    unmatched: [],
    suggestedExcluded: [],
  };
}

function metadataFromLegacy(response: GeneratedResumeResponse): GenerationMetadata {
  return {
    model: response.aiMetrics?.modelsUsed?.[0] ?? null,
    durationMs: response.aiMetrics?.generationTimeMs ?? 0,
    generatedAt: response.structuredResume?.createdAt ?? "",
    pipelineVersion: response.structuredResume?.generationAlgorithmVersion ?? "",
  };
}
