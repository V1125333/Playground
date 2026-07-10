import { beforeEach, describe, expect, it, vi } from "vitest";
import { exportResumeDocx, exportResumePdf, generateResume, saveResumeVersion, updateResume } from "./resumeService";
import { structuredResumeFixture } from "../test/fixtures/resume";

const token = "service-token";

describe("resumeService", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    }) as unknown as typeof fetch;
  });

  it("generateResume sends the persisted profile payload without full profile data", async () => {
    await generateResume(token, {
      profileId: "profile-123",
      job_description: "JD",
      target_role: "Software Engineer IV",
      target_company: "Velera",
      templateId: "classic-ats",
      generationSettings: { maximumPages: 2 },
    });

    expect(fetch).toHaveBeenCalledWith("/api/resumes/generate", expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ Authorization: `Bearer ${token}` }),
    }));
    const body = JSON.parse(String((vi.mocked(fetch).mock.calls[0][1] as RequestInit).body));
    expect(body).toMatchObject({
      profileId: "profile-123",
      job_description: "JD",
      target_role: "Software Engineer IV",
      target_company: "Velera",
      templateId: "classic-ats",
      generationSettings: { maximumPages: 2 },
    });
    expect(body).not.toHaveProperty("candidate_profile");
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
