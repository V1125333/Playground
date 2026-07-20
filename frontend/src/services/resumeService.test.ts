import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  applySectionEnhancement,
  enhanceResumeSection,
  exportResumeDocx,
  exportResumePdf,
  generateResume,
  matchProfile,
  normalizeGenerateResumeResponse,
  saveResumeVersion,
  updateResume,
} from "./resumeService";
import { generatedResumeResponseFixture, structuredResumeFixture } from "../test/fixtures/resume";
import { jobAnalysisFixture } from "../test/fixtures/jobAnalysis";

const token = "service-token";

describe("resumeService", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => generatedResumeResponseFixture,
    }) as unknown as typeof fetch;
  });

  it("generateResume sends the persisted profile payload without full profile data", async () => {
    await generateResume(token, {
      profileId: "profile-123",
      profileVersion: 3,
      candidate: {
        firstName: "Test",
        lastName: "Candidate",
        currentTitle: "Software Engineer",
        email: "test@example.com",
        phone: "555-0100",
        location: { city: "Austin", state: "TX", country: "USA", displayValue: "Austin, TX, USA" },
      },
      skills: [{ categoryId: "skill-category-0-languages", categoryName: "Languages", order: 0, items: ["C#"] }],
      workExperience: [{
        experienceId: "exp-1",
        companyName: "Company",
        clientName: null,
        roleTitle: "Software Engineer",
        location: { city: "Austin", state: "TX", country: "USA", displayValue: "Austin, TX, USA" },
        startDate: { month: 1, year: 2024, displayValue: "2024-01" },
        endDate: null,
        isCurrentRole: true,
      }],
      job: { description: "JD", targetRole: "Software Engineer IV", targetCompany: "Velera", level: "Senior" },
      jobAnalysis: jobAnalysisFixture,
      resumePreferences: {
        templateId: "classic-ats",
        headerVisibility: {
          fullName: true,
          currentTitle: true,
          email: true,
          phone: true,
          location: true,
          linkedinUrl: false,
          githubUrl: false,
          portfolioUrl: false,
        },
        sectionVisibility: {
          summary: true,
          skills: true,
          experience: true,
          projects: true,
          education: true,
          certifications: true,
        },
      },
      generationSettings: {
        maximumPages: 2,
        bulletsPerRecentRole: 5,
        bulletsPerOlderRole: 4,
        includeProjects: true,
        includeCertifications: true,
        includeUnmatchedKeywords: false,
        writingStyle: "balanced",
      },
    });

    expect(fetch).toHaveBeenCalledWith("/api/resumes/generate", expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ Authorization: `Bearer ${token}` }),
    }));
    const body = JSON.parse(String((vi.mocked(fetch).mock.calls[0][1] as RequestInit).body));
    expect(body).toMatchObject({
      profileId: "profile-123",
      profileVersion: 3,
      job: { description: "JD", targetRole: "Software Engineer IV", targetCompany: "Velera", level: "Senior" },
      resumePreferences: { headerVisibility: { linkedinUrl: false, githubUrl: false, portfolioUrl: false } },
      generationSettings: { maximumPages: 2, writingStyle: "balanced" },
    });
    expect(body).not.toHaveProperty("candidate_profile");
    expect(body).not.toHaveProperty("job_description");
  });

  it("normalizes new grouped response fields as the authoritative frontend model", () => {
    const normalized = normalizeGenerateResumeResponse({
      ...generatedResumeResponseFixture,
      atsScore: 1,
      breakdown: {
        keywordMatch: 1,
        formatting: 1,
        readability: 1,
        matchedKeywords: [],
        missingKeywords: [],
        coverage: {
          supportedAndCovered: [],
          supportedButNotRepresented: [],
          adjacentUnsupported: [],
          unmatched: [],
          suggestedExcluded: [],
        },
      },
      suggestions: [{ text: "legacy stale suggestion", points: 1 }],
      persistedResumeId: "legacy-id",
    });

    expect(normalized.resumeId).toBe("resume-123");
    expect(normalized.persistedResumeId).toBe("resume-123");
    expect(normalized.atsScore).toBe(normalized.atsAnalysis?.score);
    expect(normalized.breakdown.keywordMatch).toBe(normalized.atsAnalysis?.breakdown.keywordMatch);
    expect(normalized.breakdown.coverage).toEqual(normalized.atsAnalysis?.coverage);
    expect(normalized.suggestions).toEqual(normalized.atsAnalysis?.suggestions);
    expect(normalized.generationMetadata?.pipelineVersion).toBe("generation-v1");
    expect(normalized.aiMetrics?.generationTimeMs).toBe(normalized.generationMetadata?.durationMs);
  });

  it("normalizes legacy generate responses when grouped fields are absent", () => {
    const legacy = {
      ...generatedResumeResponseFixture,
      resumeId: undefined,
      atsAnalysis: undefined,
      generationMetadata: undefined,
      aiMetrics: {
        generationTimeMs: 424,
        aiCost: 0.02,
        tokensUsed: 100,
        modelsUsed: ["legacy-model"],
        cacheUsed: false,
        atsScore: 72,
        validationScore: 100,
      },
    };

    const normalized = normalizeGenerateResumeResponse(legacy);

    expect(normalized.resumeId).toBe("resume-123");
    expect(normalized.atsAnalysis?.score).toBe(72);
    expect(normalized.atsAnalysis?.breakdown.keywordMatch).toBe(72);
    expect(normalized.generationMetadata).toEqual({
      model: "legacy-model",
      durationMs: 424,
      generatedAt: "2026-07-01T10:00:00.000Z",
      pipelineVersion: "generation-v1",
    });
  });

  it("updateResume targets the correct resume endpoint with structured JSON", async () => {
    await updateResume(token, "resume-123", { resumeJson: structuredResumeFixture, status: "draft" });

    expect(fetch).toHaveBeenCalledWith("/api/resumes/resume-123", expect.objectContaining({ method: "PUT" }));
    const body = JSON.parse(String((vi.mocked(fetch).mock.calls[0][1] as RequestInit).body));
    expect(body.resumeJson.resumeId).toBe("resume-123");
    expect(body.status).toBe("draft");
  });

  it("saveResumeVersion targets the version endpoint", async () => {
    await saveResumeVersion(token, "resume-123");

    expect(fetch).toHaveBeenCalledWith("/api/resumes/resume-123/versions", expect.objectContaining({ method: "POST" }));
  });

  it("enhanceResumeSection targets the read-only enhancement endpoint", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ suggestions: [], validationStatus: "valid", warnings: [], resumeRevision: "rev-1" }),
    }) as unknown as typeof fetch;

    await enhanceResumeSection(token, "resume-123", {
      sectionType: "summary",
      sectionId: "section-summary",
      currentText: "Original",
    });

    expect(fetch).toHaveBeenCalledWith("/api/resumes/resume-123/enhance-section", expect.objectContaining({ method: "POST" }));
    const body = JSON.parse(String((vi.mocked(fetch).mock.calls[0][1] as RequestInit).body));
    expect(body).toMatchObject({ sectionType: "summary", sectionId: "section-summary", currentText: "Original" });
  });

  it("applySectionEnhancement targets the explicit apply endpoint", async () => {
    await applySectionEnhancement(token, "resume-123", {
      sectionType: "summary",
      sectionId: "section-summary",
      suggestionId: "suggestion-1",
    });

    expect(fetch).toHaveBeenCalledWith("/api/resumes/resume-123/apply-section-enhancement", expect.objectContaining({ method: "POST" }));
    const body = JSON.parse(String((vi.mocked(fetch).mock.calls[0][1] as RequestInit).body));
    expect(body).toMatchObject({ suggestionId: "suggestion-1" });
  });

  it("exportResumePdf handles binary blob and filename", async () => {
    const blob = new Blob(["%PDF"], { type: "application/pdf" });
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: headers({
        "content-type": "application/pdf",
        "content-disposition": 'attachment; filename="Venu_v2.pdf"',
        "x-resume-version": "2",
        "x-export-renderer-version": "resume-export-v1-structured",
      }),
      blob: async () => blob,
    }) as unknown as typeof fetch;

    const result = await exportResumePdf(token, "resume-123", { templateId: "classic-ats", paperSize: "letter" });

    expect(fetch).toHaveBeenCalledWith("/api/resumes/resume-123/export/pdf?template_id=classic-ats&paper_size=letter", expect.objectContaining({
      headers: { Authorization: `Bearer ${token}` },
    }));
    expect(result.blob).toBe(blob);
    expect(result.filename).toBe("Venu_v2.pdf");
    expect(result.resumeVersion).toBe("2");
  });

  it("exportResumeDocx handles binary blob and filename", async () => {
    const blob = new Blob(["docx"], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: headers({
        "content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "content-disposition": 'attachment; filename="Venu_v2.docx"',
      }),
      blob: async () => blob,
    }) as unknown as typeof fetch;

    const result = await exportResumeDocx(token, "resume-123");

    expect(fetch).toHaveBeenCalledWith("/api/resumes/resume-123/export/docx", expect.any(Object));
    expect(result.blob).toBe(blob);
    expect(result.filename).toBe("Venu_v2.docx");
  });

  it("export service parses JSON error responses", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      headers: headers({ "content-type": "application/json" }),
      json: async () => ({ detail: "Validation failed." }),
    }) as unknown as typeof fetch;

    await expect(exportResumePdf(token, "resume-123")).rejects.toThrow("Validation failed.");
  });

  it("formats structured backend validation errors without leaking raw detail objects", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({
        detail: {
          code: "SUMMARY_INTELLIGENCE_INVALID",
          message: "Summary intelligence could not be validated. Review your profile evidence and run Analyze & Match again.",
          details: [{ code: "UNSUPPORTED_TECHNOLOGY_CLAIM", message: "Summary claims unsupported technology: java." }],
        },
      }),
    }) as unknown as typeof fetch;

    await expect(matchProfile(token, { profileId: "profile-123" })).rejects.toThrow(
      "Summary intelligence could not be validated. Review your profile evidence and run Analyze & Match again. Summary claims unsupported technology: java.",
    );
  });

  it("export service rejects invalid content type", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: headers({ "content-type": "text/html" }),
      blob: async () => new Blob(["nope"], { type: "text/html" }),
    }) as unknown as typeof fetch;

    await expect(exportResumePdf(token, "resume-123")).rejects.toThrow(/invalid pdf file/i);
  });
});

function headers(values: Record<string, string>) {
  return {
    get(name: string) {
      return values[name.toLowerCase()] ?? null;
    },
  };
}
