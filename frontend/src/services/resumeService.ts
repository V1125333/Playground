import type {
  GeneratedResumeResponse,
  JobAnalysisResponse,
  ProfileMatchResponse,
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
    throw new Error(error?.detail ?? "Resume request failed.");
  }
  return (await response.json()) as T;
}

export async function generateResume(token: string, payload: Record<string, unknown>): Promise<GeneratedResumeResponse> {
  return requestJson<GeneratedResumeResponse>("/api/resumes/generate", token, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
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
    throw new Error(error?.detail ?? "Resume delete failed.");
  }
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
      throw new Error(error?.detail ?? `Resume ${format.toUpperCase()} export failed.`);
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
