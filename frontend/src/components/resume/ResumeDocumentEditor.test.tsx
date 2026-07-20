import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ResumeDocumentEditor } from "./ResumeDocumentEditor";
import { profileFixture } from "../../test/fixtures/profile";
import { resumeRecordFixture, structuredResumeFixture } from "../../test/fixtures/resume";
import type { GeneratedResumeSection, StructuredGeneratedResume, StructuredResumeRecord } from "../../resume/types";

function renderEditor(resume: StructuredGeneratedResume) {
  render(
    <ResumeDocumentEditor
      resume={resume}
      profile={profileFixture.profileData}
      evidence={[]}
      requirements={[]}
      validationWarnings={[]}
      editable={false}
      onChange={vi.fn()}
    />,
  );
}

describe("ResumeDocumentEditor header visibility", () => {
  it("renders only fields present in structured resumeHeader", () => {
    const resume: StructuredGeneratedResume = {
      ...structuredResumeFixture,
      resumeHeader: {
        fullName: "Venu Madhav Pendurthi",
        phone: "+12014436937",
      },
      contact: {
        email: "hidden@example.com",
        phone: "+12014436937",
        location: "Hidden, CT",
        linkedin: "https://linkedin.com/in/hidden",
        github: "https://github.com/hidden",
        portfolio: "https://hidden.example.com",
      },
      sections: [],
    };

    renderEditor(resume);

    expect(screen.getByRole("heading", { name: "Venu Madhav Pendurthi" })).toBeInTheDocument();
    expect(screen.getByText("+12014436937")).toBeInTheDocument();
    expect(screen.queryByText("Senior .NET Developer")).not.toBeInTheDocument();
    expect(screen.queryByText("hidden@example.com")).not.toBeInTheDocument();
    expect(screen.queryByText("Hidden, CT")).not.toBeInTheDocument();
    expect(screen.queryByText("https://linkedin.com/in/hidden")).not.toBeInTheDocument();
    expect(screen.queryByText("https://github.com/hidden")).not.toBeInTheDocument();
    expect(screen.queryByText("https://hidden.example.com")).not.toBeInTheDocument();
  });

  it("renders all visible structured header fields and only sections present in structuredResume", () => {
    const experienceOnly = structuredResumeFixture.sections.filter((section) => section.type === "experience");
    const resume: StructuredGeneratedResume = {
      ...structuredResumeFixture,
      resumeHeader: {
        fullName: "Venu Madhav Pendurthi",
        currentTitle: "Senior .NET Developer",
        email: "venu@example.com",
        phone: "+12014436937",
        location: "Hartford, CT",
        linkedinUrl: "https://linkedin.com/in/venu",
        githubUrl: "https://github.com/venu",
        portfolioUrl: "https://venu.dev",
      },
      sections: experienceOnly,
    };

    renderEditor(resume);

    expect(screen.getByRole("heading", { name: "Venu Madhav Pendurthi" })).toBeInTheDocument();
    expect(screen.getAllByText("Senior .NET Developer").length).toBeGreaterThan(0);
    expect(screen.getByText(/\+12014436937/)).toHaveTextContent("+12014436937");
    expect(screen.getByText(/\+12014436937/)).toHaveTextContent("venu@example.com");
    expect(screen.getByText(/\+12014436937/)).toHaveTextContent("Hartford, CT");
    expect(screen.getByText(/\+12014436937/)).toHaveTextContent("https://linkedin.com/in/venu");
    expect(screen.getByText(/\+12014436937/)).toHaveTextContent("https://github.com/venu");
    expect(screen.getByText(/\+12014436937/)).toHaveTextContent("https://venu.dev");
    expect(screen.queryByText("SUMMARY")).not.toBeInTheDocument();
    expect(screen.queryByText("TECHNICAL SKILLS")).not.toBeInTheDocument();
    expect(screen.getByText("PROFESSIONAL EXPERIENCE")).toBeInTheDocument();
  });
});

describe("ResumeDocumentEditor section enhancement", () => {
  it("opens a safe preview dialog and applies an accepted summary enhancement", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const onPersistedChange = vi.fn();
    const updatedRecord = recordWithSummary("Improved summary with supported C# and SQL Server evidence.");
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          suggestions: [
            {
              suggestionId: "suggestion-1",
              sectionType: "summary",
              sectionId: "section-summary",
              originalText: "Senior .NET Developer with enterprise C# and API delivery experience.",
              enhancedText: "Improved summary with supported C# and SQL Server evidence.",
              explanation: "Polished wording while preserving supported facts.",
              supportingEvidenceIds: ["ev-infosys-api"],
              supportedRequirementIds: ["req-c"],
              validationStatus: "valid",
              warnings: [],
              model: "gpt-5.5-mini",
              promptVersion: "section-enhancement-v1",
              createdAt: "2026-07-19T00:00:00.000Z",
            },
          ],
          validationStatus: "valid",
          warnings: [],
          resumeRevision: resumeRecordFixture.updatedAt,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => updatedRecord,
      }) as unknown as typeof fetch;

    render(
      <ResumeDocumentEditor
        resume={structuredResumeFixture}
        profile={profileFixture.profileData}
        evidence={[]}
        requirements={[]}
        validationWarnings={[]}
        editable
        authToken="token-123"
        currentRecord={resumeRecordFixture}
        onChange={onChange}
        onPersistedChange={onPersistedChange}
      />,
    );

    await user.click(screen.getByLabelText("Enhance SUMMARY with AI"));

    expect(screen.getByRole("heading", { name: "Enhance with AI" })).toBeInTheDocument();
    expect(screen.getByText("AI can polish wording only. It cannot add unsupported experience.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Enhance" }));

    expect(await screen.findByText("Improved summary with supported C# and SQL Server evidence.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(onPersistedChange).toHaveBeenCalledWith(updatedRecord));
    expect(onChange).toHaveBeenCalledWith(updatedRecord.resumeJson);
    expect(fetch).toHaveBeenNthCalledWith(1, "/api/resumes/resume-123/enhance-section", expect.objectContaining({ method: "POST" }));
    expect(fetch).toHaveBeenNthCalledWith(2, "/api/resumes/resume-123/apply-section-enhancement", expect.objectContaining({ method: "POST" }));
  });

  it("does not allow free-form AI enhancement for skills", () => {
    render(
      <ResumeDocumentEditor
        resume={structuredResumeFixture}
        profile={profileFixture.profileData}
        evidence={[]}
        requirements={[]}
        validationWarnings={[]}
        editable
        authToken="token-123"
        currentRecord={resumeRecordFixture}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("Skills enhancement unavailable")).toBeDisabled();
  });
});

function recordWithSummary(summary: string): StructuredResumeRecord {
  const resumeJson: StructuredGeneratedResume = {
    ...structuredResumeFixture,
    sections: structuredResumeFixture.sections.map((section): GeneratedResumeSection => (
      section.sectionId === "section-summary" ? { ...section, content: summary } : section
    )),
    updatedAt: "2026-07-19T00:00:00.000Z",
  };
  return {
    ...resumeRecordFixture,
    resumeJson,
    updatedAt: "2026-07-19T00:00:00.000Z",
  };
}
