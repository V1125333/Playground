import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ResumeDocumentEditor } from "./ResumeDocumentEditor";
import { profileFixture } from "../../test/fixtures/profile";
import { structuredResumeFixture } from "../../test/fixtures/resume";
import type { StructuredGeneratedResume } from "../../resume/types";

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
