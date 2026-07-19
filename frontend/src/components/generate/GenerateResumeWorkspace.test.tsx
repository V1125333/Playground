import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GenerateResumeWorkspace } from "./GenerateResumeWorkspace";
import { renderWithProviders } from "../../test/renderWithProviders";
import { jobAnalysisFixture } from "../../test/fixtures/jobAnalysis";
import { profileFixture, lowCompletenessProfileFixture } from "../../test/fixtures/profile";
import { profileMatchFixture } from "../../test/fixtures/profileMatch";
import {
  generatedResumeResponseFixture,
  historicalResumeRecordFixture,
  resumeRecordFixture,
  structuredResumeFixture,
} from "../../test/fixtures/resume";
import * as resumeService from "../../services/resumeService";
import type { StructuredResumeRecord } from "../../resume/types";

vi.mock("../../services/resumeService", () => ({
  analyzeJob: vi.fn(),
  matchProfile: vi.fn(),
  generateResume: vi.fn(),
  getResume: vi.fn(),
  listResumes: vi.fn(),
  updateResume: vi.fn(),
  saveResumeVersion: vi.fn(),
  listResumeVersions: vi.fn(),
  deleteResume: vi.fn(),
  exportResumePdf: vi.fn(),
  exportResumeDocx: vi.fn(),
}));

const token = "test-token";
const jdText =
  "We need a Software Engineer IV with C#, .NET, REST APIs, SQL Server, Python, Azure, Agile delivery, code reviews, and trading systems.";

function renderWorkspace(options: {
  profile?: typeof profileFixture | null;
  route?: string;
  path?: string;
  profileLoadError?: string;
} = {}) {
  return renderWithProviders(
    <GenerateResumeWorkspace
      authToken={token}
      profileRecord={options.profile === undefined ? profileFixture : options.profile}
      profileLoadError={options.profileLoadError ?? ""}
      onResumeGenerated={vi.fn()}
    />,
    options.route ?? "/generate",
    options.path ?? "/generate",
  );
}

function mockDefaultServices(records: StructuredResumeRecord[] = []) {
  vi.mocked(resumeService.listResumes).mockResolvedValue(records);
  vi.mocked(resumeService.listResumeVersions).mockResolvedValue([]);
  vi.mocked(resumeService.getResume).mockResolvedValue(resumeRecordFixture);
  vi.mocked(resumeService.analyzeJob).mockResolvedValue(jobAnalysisFixture);
  vi.mocked(resumeService.matchProfile).mockResolvedValue(profileMatchFixture);
  vi.mocked(resumeService.generateResume).mockResolvedValue(generatedResumeResponseFixture);
  vi.mocked(resumeService.updateResume).mockImplementation(async (_token, _id, payload) => ({
    ...resumeRecordFixture,
    resumeJson: payload.resumeJson,
    updatedAt: "2026-07-01T10:05:00.000Z",
  }));
  vi.mocked(resumeService.saveResumeVersion).mockResolvedValue({ ...resumeRecordFixture, resumeId: "resume-456", versionNumber: 2 });
  vi.mocked(resumeService.exportResumePdf).mockResolvedValue({
    blob: new Blob(["%PDF test"], { type: "application/pdf" }),
    filename: "Venu_Madhav_Software_Engineer_IV_Morgan_Stanley_v1.pdf",
    contentType: "application/pdf",
    resumeVersion: "1",
    rendererVersion: "resume-export-v1-structured",
  });
  vi.mocked(resumeService.exportResumeDocx).mockResolvedValue({
    blob: new Blob(["docx"], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" }),
    filename: "Venu_Madhav_Software_Engineer_IV_Morgan_Stanley_v1.docx",
    contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    resumeVersion: "1",
    rendererVersion: "resume-export-v1-structured",
  });
}

async function fillJobAndAnalyze(user = userEvent.setup()) {
  await user.clear(screen.getByLabelText(/target job title/i));
  await user.type(screen.getByLabelText(/target job title/i), "Software Engineer IV");
  await user.clear(screen.getByLabelText(/company name/i));
  await user.type(screen.getByLabelText(/company name/i), "Morgan Stanley");
  await user.clear(screen.getByPlaceholderText(/paste the full job description/i));
  await user.type(screen.getByPlaceholderText(/paste the full job description/i), jdText);
  await user.click(screen.getByRole("button", { name: /analyze & match/i }));
  await screen.findByText("C#");
  return user;
}

describe("GenerateResumeWorkspace", () => {
  beforeEach(() => {
    mockDefaultServices();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:resume-export");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  });

  it("shows a profile empty state and disables actions when no profile exists", async () => {
    renderWorkspace({ profile: null });

    expect((await screen.findAllByText(/complete your profile before generating/i)).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /go to profile/i })).toHaveAttribute("href", "/profile");
    expect(screen.getByRole("button", { name: /analyze & match/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /generate resume/i })).toBeDisabled();
  });

  it("loads a ready profile without creating or migrating data", async () => {
    renderWorkspace();

    expect(await screen.findByLabelText(/target job title/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Saved$/)).not.toBeInTheDocument();
    expect(resumeService.listResumes).toHaveBeenCalledTimes(1);
    expect(resumeService.generateResume).not.toHaveBeenCalled();
  });

  it("analyzes a job, preserves input, and displays matched adjacent and missing requirements", async () => {
    const user = userEvent.setup();
    renderWorkspace();

    await fillJobAndAnalyze(user);

    expect(resumeService.analyzeJob).toHaveBeenCalledTimes(1);
    expect(resumeService.analyzeJob).toHaveBeenCalledWith(token, expect.objectContaining({
      job_description: jdText,
      target_role: "Software Engineer IV",
      target_company: "Morgan Stanley",
      level: "Senior",
    }));
    expect(resumeService.matchProfile).toHaveBeenCalledWith(token, {
      profileId: "profile-123",
      jobAnalysis: jobAnalysisFixture,
      jobDescription: jdText,
      targetRole: "Software Engineer IV",
      targetCompany: "Morgan Stanley",
      level: "Senior",
    });
    expect(screen.getByPlaceholderText(/paste the full job description/i)).toHaveValue(jdText);
    expect(screen.getByText("Profile match 72%")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Profile Match" })).toBeInTheDocument();
    expect(screen.getByText("Profile-to-job match")).toBeInTheDocument();
    expect(screen.getByText("Analyze the job description and compare it with your saved profile.")).toBeInTheDocument();
    expect(screen.getByText(/This score compares the job requirements with evidence in your saved profile/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Summary Intelligence" })).toBeInTheDocument();
    expect(screen.getByText(/maintainable API delivery/i)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Resume ATS Score" })).not.toBeInTheDocument();
    expect(screen.getAllByText(/exact or normalized match/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/transferable, not a direct match/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/not found in profile/i).length).toBeGreaterThan(0);
  });

  it("ignores stale analysis responses when the job input changes while analysis is running", async () => {
    let resolveAnalyze: (value: typeof jobAnalysisFixture) => void = () => {};
    vi.mocked(resumeService.analyzeJob).mockReturnValueOnce(new Promise((resolve) => {
      resolveAnalyze = resolve;
    }));
    const user = userEvent.setup();
    renderWorkspace();

    await user.clear(screen.getByLabelText(/target job title/i));
    await user.type(screen.getByLabelText(/target job title/i), "Software Engineer IV");
    await user.clear(screen.getByPlaceholderText(/paste the full job description/i));
    await user.type(screen.getByPlaceholderText(/paste the full job description/i), jdText);
    await user.click(screen.getByRole("button", { name: /analyze & match/i }));
    fireEvent.change(screen.getByPlaceholderText(/paste the full job description/i), {
      target: { value: `${jdText} Updated after analyze started.` },
    });

    await act(async () => resolveAnalyze(jobAnalysisFixture));

    await waitFor(() => expect(screen.getByRole("button", { name: /analyze & match/i })).not.toBeDisabled());
    expect(resumeService.matchProfile).not.toHaveBeenCalled();
    expect(screen.queryByText("Profile match 72%")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate resume/i })).toBeDisabled();
  });

  it("clears analyzed package state after editing analyzed job details", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    await fillJobAndAnalyze(user);

    expect(screen.getByText("Profile match 72%")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/company name/i), " Updated");

    expect(screen.queryByText("Profile match 72%")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate resume/i })).toBeDisabled();
  });

  it("shows an analysis error, keeps the JD, and does not generate", async () => {
    vi.mocked(resumeService.analyzeJob).mockRejectedValueOnce(new Error("Analysis service unavailable."));
    const user = userEvent.setup();
    renderWorkspace();

    await user.clear(screen.getByLabelText(/target job title/i));
    await user.type(screen.getByLabelText(/target job title/i), "Software Engineer IV");
    await user.type(screen.getByPlaceholderText(/paste the full job description/i), jdText);
    await user.click(screen.getByRole("button", { name: /analyze & match/i }));

    expect(await screen.findByText(/analysis service unavailable/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/paste the full job description/i)).toHaveValue(jdText);
    expect(resumeService.generateResume).not.toHaveBeenCalled();
  });

  it("generates with a canonical profile snapshot from the persisted profile", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    await fillJobAndAnalyze(user);

    await user.click(screen.getByRole("button", { name: /generate resume/i }));

    await screen.findByText(/venu madhav pendurthi/i);
    expect(screen.getByText("Resume ATS 72%")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Resume ATS Score" })).toBeInTheDocument();
    expect(screen.getByText("Generated resume ATS score")).toBeInTheDocument();
    expect(screen.getByText(/^Saved$/)).toBeInTheDocument();
    expect(resumeService.generateResume).toHaveBeenCalledTimes(1);
    expect(resumeService.generateResume).toHaveBeenCalledWith(token, expect.objectContaining({
      profileId: "profile-123",
      profileVersion: 3,
      resumeIntelligencePackageId: "package-123",
      candidate: expect.objectContaining({
        firstName: "Venu Madhav",
        lastName: "Pendurthi",
        currentTitle: "Senior .NET Developer",
        email: "venu@example.com",
        phone: "+12014436937",
      }),
      skills: expect.arrayContaining([
        expect.objectContaining({
          categoryId: "programming-languages",
          categoryName: "Programming Languages",
          items: ["C#", "SQL"],
        }),
      ]),
      workExperience: expect.arrayContaining([
        expect.objectContaining({
          experienceId: "exp-infosys",
          companyName: "Infosys",
          roleTitle: "Senior .NET Developer",
          isCurrentRole: true,
          endDate: null,
        }),
      ]),
      job: {
        description: jdText,
        targetRole: "Software Engineer IV",
        targetCompany: "Morgan Stanley",
        level: "Senior",
      },
      resumePreferences: expect.objectContaining({
        templateId: "classic-ats",
        headerVisibility: expect.objectContaining({
          linkedinUrl: false,
          githubUrl: false,
          portfolioUrl: false,
        }),
      }),
      generationSettings: expect.any(Object),
    }));
    const body = vi.mocked(resumeService.generateResume).mock.calls[0][1];
    expect(body).not.toHaveProperty("candidate_profile");
    expect(body).not.toHaveProperty("job_description");
    expect(JSON.stringify(body.workExperience)).not.toContain("rawNotes");
    expect(JSON.stringify(body.workExperience)).not.toContain("bullets");
    expect(resumeService.getResume).toHaveBeenCalledWith(token, generatedResumeResponseFixture.resumeId);
  });

  it("prevents rapid double-click duplicate generation", async () => {
    let resolveGenerate: (value: typeof generatedResumeResponseFixture) => void = () => {};
    vi.mocked(resumeService.generateResume).mockReturnValueOnce(new Promise((resolve) => {
      resolveGenerate = resolve;
    }));
    const user = userEvent.setup();
    renderWorkspace();
    await fillJobAndAnalyze(user);

    const button = screen.getByRole("button", { name: /generate resume/i });
    await user.dblClick(button);
    expect(resumeService.generateResume).toHaveBeenCalledTimes(1);
    expect(button).toBeDisabled();

    await act(async () => resolveGenerate(generatedResumeResponseFixture));
  });

  it("renders structured resume sections and omits empty sections", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    await fillJobAndAnalyze(user);
    await user.click(screen.getByRole("button", { name: /generate resume/i }));

    expect(await screen.findByText(/venu madhav pendurthi/i)).toBeInTheDocument();
    expect(screen.getByText(/Senior \.NET Developer with enterprise C#/i)).toBeInTheDocument();
    expect(screen.getByText(/C#, \.NET, REST APIs, SQL Server/i)).toBeInTheDocument();
    expect(screen.getAllByText(/improving release quality by 20%/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Master of Science in Computer Science/i)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "PROJECTS" })).not.toBeInTheDocument();
  });

  it("keeps unsupported requirements in Missing insights without claiming them in the resume", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    await fillJobAndAnalyze(user);
    await user.click(screen.getByRole("button", { name: /generate resume/i }));

    await screen.findByText(/venu madhav pendurthi/i);
    const article = screen.getByRole("article", { name: /editable generated resume document/i });
    expect(screen.getAllByText("Azure").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Trading").length).toBeGreaterThan(0);
    expect(article).not.toHaveTextContent("Azure");
    expect(article).not.toHaveTextContent("Trading");
  });

  it("shows human-readable evidence without making raw IDs the primary content", async () => {
    const user = userEvent.setup();
    renderWorkspace({ route: "/generate/resume-123", path: "/generate/:resumeId" });
    await screen.findByText(/venu madhav pendurthi/i);

    await user.click(screen.getAllByRole("button", { name: /show evidence details/i })[0]);

    expect(screen.getByText(/Work Experience: Senior \.NET Developer at Infosys/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Built C# and ASP.NET Core REST API enhancements/i).length).toBeGreaterThan(0);
    expect(screen.queryByText("ev-infosys-api")).not.toBeInTheDocument();
  });

  it("edits a bullet and autosaves the latest text after debounce", async () => {
    const user = userEvent.setup();
    renderWorkspace({ route: "/generate/resume-123", path: "/generate/:resumeId" });
    await screen.findByText(/venu madhav pendurthi/i);

    const article = screen.getByRole("article", { name: /editable generated resume document/i });
    const editableText = within(article).getAllByRole("textbox", { name: /editable resume text/i })[2];
    editableText.textContent = `${editableText.textContent} Updated for test.`;
    fireEvent.input(editableText);

    expect(screen.getByText(/unsaved changes/i)).toBeInTheDocument();
    expect(resumeService.updateResume).not.toHaveBeenCalled();

    await waitFor(() => expect(resumeService.updateResume).toHaveBeenCalledTimes(1), { timeout: 2500 });
    const payload = vi.mocked(resumeService.updateResume).mock.calls[0][2];
    expect(JSON.stringify(payload.resumeJson.sections)).toContain("Updated for test");

  });

  it("preserves structured bullet provenance when editing currentText", async () => {
    const structured = structuredClone(structuredResumeFixture);
    const experienceSection = structured.sections.find((section) => section.type === "experience");
    const experienceEntries = experienceSection?.content as Array<{ bullets: unknown[] }>;
    experienceEntries[0].bullets = [
      {
        bulletId: "bullet-structured-1",
        order: 1,
        generatedText: "Structured generated bullet should remain immutable.",
        currentText: "Structured current bullet for rendering.",
        userEdited: false,
        supportedRequirementIds: ["req-c"],
        supportingEvidenceIds: ["ev-infosys-api"],
        validationStatus: "validated",
        warnings: [],
      },
    ];
    const structuredRecord = { ...resumeRecordFixture, resumeJson: structured };
    vi.mocked(resumeService.listResumes).mockResolvedValueOnce([structuredRecord]);
    vi.mocked(resumeService.getResume).mockResolvedValueOnce(structuredRecord);

    renderWorkspace({ route: "/generate/resume-123", path: "/generate/:resumeId" });
    await screen.findByText(/Structured current bullet for rendering/i);
    expect(screen.queryByText(/Structured generated bullet should remain immutable/i)).not.toBeInTheDocument();

    const article = screen.getByRole("article", { name: /editable generated resume document/i });
    const editableText = within(article).getByText(/Structured current bullet for rendering/i);
    editableText.textContent = "Edited currentText while keeping provenance.";
    fireEvent.input(editableText);

    await waitFor(() => expect(resumeService.updateResume).toHaveBeenCalledTimes(1), { timeout: 2500 });
    const payload = vi.mocked(resumeService.updateResume).mock.calls[0][2];
    const savedExperience = payload.resumeJson.sections.find((section) => section.type === "experience")?.content as Array<{ bullets: Array<Record<string, unknown>> }>;
    const savedBullet = savedExperience[0].bullets[0];
    expect(savedBullet.currentText).toBe("Edited currentText while keeping provenance.");
    expect(savedBullet.generatedText).toBe("Structured generated bullet should remain immutable.");
    expect(savedBullet.bulletId).toBe("bullet-structured-1");
    expect(savedBullet.supportingEvidenceIds).toEqual(["ev-infosys-api"]);
    expect(savedBullet.supportedRequirementIds).toEqual(["req-c"]);
    expect(savedBullet.userEdited).toBe(true);
    expect(savedBullet.validationStatus).toBe("pending_validation");
  });

  it("keeps edited content visible and shows an error when autosave fails", async () => {
    vi.mocked(resumeService.updateResume).mockRejectedValueOnce(new Error("Network failed."));
    renderWorkspace({ route: "/generate/resume-123", path: "/generate/:resumeId" });
    await screen.findByText(/venu madhav pendurthi/i);

    const article = screen.getByRole("article", { name: /editable generated resume document/i });
    const editableText = within(article).getAllByRole("textbox", { name: /editable resume text/i })[2];
    editableText.textContent = `${editableText.textContent} Failure remains.`;
    fireEvent.input(editableText);

    await waitFor(() => expect(resumeService.updateResume).toHaveBeenCalledTimes(1), { timeout: 2500 });
    expect(await screen.findByText(/save failed/i)).toBeInTheDocument();
    expect(screen.getByText(/Failure remains/i)).toBeInTheDocument();

  });

  it("displays unsupported edit warnings for claims without profile evidence", async () => {
    const user = userEvent.setup();
    renderWorkspace({ route: "/generate/resume-123", path: "/generate/:resumeId" });
    await screen.findByText(/venu madhav pendurthi/i);

    const article = screen.getByRole("article", { name: /editable generated resume document/i });
    const editableText = within(article).getAllByRole("textbox", { name: /editable resume text/i })[2];
    editableText.textContent = `${editableText.textContent} Azure`;
    fireEvent.input(editableText);

    expect((await screen.findAllByText(/draft mentions azure/i)).length).toBeGreaterThan(0);
  });

  it("requires confirmation before deleting a bullet", async () => {
    const user = userEvent.setup();
    vi.mocked(window.confirm).mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderWorkspace({ route: "/generate/resume-123", path: "/generate/:resumeId" });
    await screen.findByText(/venu madhav pendurthi/i);

    await user.click(screen.getAllByRole("button", { name: /delete bullet/i })[0]);
    expect(screen.getAllByText(/improving release quality by 20%/i).length).toBeGreaterThan(0);

    await user.click(screen.getAllByRole("button", { name: /delete bullet/i })[0]);
    expect(within(screen.getByRole("article", { name: /editable generated resume document/i })).queryByText(/improving release quality by 20%/i)).not.toBeInTheDocument();
  });

  it("adds a bullet inside the same role and does not create cross-role movement controls", async () => {
    const user = userEvent.setup();
    renderWorkspace({ route: "/generate/resume-123", path: "/generate/:resumeId" });
    await screen.findByText(/venu madhav pendurthi/i);

    await user.click(screen.getAllByRole("button", { name: /add bullet/i })[0]);
    expect(screen.getByText(/Describe a truthful, evidence-supported accomplishment/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /move bullet to/i })).not.toBeInTheDocument();
  });

  it("reorders sections and persists the new order", async () => {
    const user = userEvent.setup();
    renderWorkspace({ route: "/generate/resume-123", path: "/generate/:resumeId" });
    await screen.findByText(/venu madhav pendurthi/i);

    await user.click(screen.getByRole("button", { name: /move technical skills up/i }));

    await waitFor(() => expect(resumeService.updateResume).toHaveBeenCalled(), { timeout: 2500 });
    const sections = vi.mocked(resumeService.updateResume).mock.calls.at(-1)?.[2].resumeJson.sections ?? [];
    expect(sections.find((section) => section.sectionId === "section-skills")?.order).toBe(1);

  });

  it("reorders bullets within one role and persists the order", async () => {
    const user = userEvent.setup();
    renderWorkspace({ route: "/generate/resume-123", path: "/generate/:resumeId" });
    await screen.findByText(/venu madhav pendurthi/i);

    await user.click(screen.getAllByRole("button", { name: /move bullet down/i })[0]);

    await waitFor(() => expect(resumeService.updateResume).toHaveBeenCalled(), { timeout: 2500 });
    const payloadText = JSON.stringify(vi.mocked(resumeService.updateResume).mock.calls.at(-1)?.[2].resumeJson.sections);
    expect(payloadText.indexOf("Reviewed API")).toBeLessThan(payloadText.indexOf("Built C#"));

  });

  it("hides a section after confirmation and persists visibility", async () => {
    const user = userEvent.setup();
    renderWorkspace({ route: "/generate/resume-123", path: "/generate/:resumeId" });
    await screen.findByText(/venu madhav pendurthi/i);

    await user.click(screen.getByRole("button", { name: /hide technical skills/i }));
    expect(screen.queryByRole("heading", { name: "TECHNICAL SKILLS" })).not.toBeInTheDocument();
    await waitFor(() => expect(resumeService.updateResume).toHaveBeenCalled(), { timeout: 2500 });
    expect(JSON.stringify(vi.mocked(resumeService.updateResume).mock.calls.at(-1)?.[2].resumeJson.sections)).toContain('"visible":false');

  });

  it("loads a persisted resume from the route", async () => {
    renderWorkspace({ route: "/generate/resume-123", path: "/generate/:resumeId" });

    expect(await screen.findByText(/venu madhav pendurthi/i)).toBeInTheDocument();
    expect(resumeService.getResume).toHaveBeenCalledWith(token, "resume-123");
    expect(screen.getByLabelText(/target job title/i)).toHaveValue("Software Engineer IV");
  });

  it("shows a readable load error without crashing", async () => {
    vi.mocked(resumeService.listResumes).mockRejectedValueOnce(new Error("Could not load saved resumes."));
    renderWorkspace();

    expect(await screen.findByText(/could not load saved resumes/i)).toBeInTheDocument();
  });

  it("saves a new version and refreshes the selector", async () => {
    vi.mocked(resumeService.listResumeVersions)
      .mockResolvedValueOnce([resumeRecordFixture])
      .mockResolvedValueOnce([resumeRecordFixture, { ...resumeRecordFixture, resumeId: "resume-456", versionNumber: 2 }]);
    const user = userEvent.setup();
    renderWorkspace({ route: "/generate/resume-123", path: "/generate/:resumeId" });
    await screen.findByText(/venu madhav pendurthi/i);

    await user.click(screen.getByRole("button", { name: /new version/i }));

    await waitFor(() => expect(resumeService.saveResumeVersion).toHaveBeenCalledWith(token, "resume-123"));
    expect(await screen.findByRole("option", { name: /version 2/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /version 1/i })).toBeInTheDocument();
  });

  it("opens historical versions read-only with autosave disabled", async () => {
    vi.mocked(resumeService.listResumes).mockResolvedValueOnce([historicalResumeRecordFixture]);
    vi.mocked(resumeService.getResume).mockResolvedValueOnce(historicalResumeRecordFixture);
    renderWorkspace({ route: "/generate/resume-history-1", path: "/generate/:resumeId" });

    expect(await screen.findByText(/Historical version opened read-only/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /save/i })).toBeDisabled();
  });

  it("saves unsaved draft content before exporting PDF", async () => {
    const user = userEvent.setup();
    renderWorkspace({ route: "/generate/resume-123", path: "/generate/:resumeId" });
    await screen.findByText(/venu madhav pendurthi/i);

    const article = screen.getByRole("article", { name: /editable generated resume document/i });
    const editableText = within(article).getAllByRole("textbox", { name: /editable resume text/i })[2];
    editableText.textContent = `${editableText.textContent} Export edit.`;
    fireEvent.input(editableText);

    await user.click(screen.getByRole("button", { name: /^pdf$/i }));

    await waitFor(() => expect(resumeService.updateResume).toHaveBeenCalled(), { timeout: 2500 });
    expect(resumeService.exportResumePdf).toHaveBeenCalledWith(token, "resume-123", expect.objectContaining({
      templateId: "classic-ats",
      paperSize: "letter",
    }));
  });

  it("shows PDF export loading state and prevents duplicate export clicks", async () => {
    let resolveExport: (value: Awaited<ReturnType<typeof resumeService.exportResumePdf>>) => void = () => {};
    vi.mocked(resumeService.exportResumePdf).mockReturnValueOnce(new Promise((resolve) => {
      resolveExport = resolve;
    }));
    const user = userEvent.setup();
    renderWorkspace({ route: "/generate/resume-123", path: "/generate/:resumeId" });
    await screen.findByText(/venu madhav pendurthi/i);

    const button = screen.getByRole("button", { name: /^pdf$/i });
    await user.dblClick(button);

    expect(await screen.findByRole("button", { name: /preparing pdf/i })).toBeDisabled();
    expect(resumeService.exportResumePdf).toHaveBeenCalledTimes(1);
    await act(async () => resolveExport({
      blob: new Blob(["%PDF"], { type: "application/pdf" }),
      filename: "resume.pdf",
      contentType: "application/pdf",
      resumeVersion: "1",
      rendererVersion: "resume-export-v1-structured",
    }));
  });

  it("successful Word export triggers a browser download and revokes the blob URL", async () => {
    const user = userEvent.setup();
    renderWorkspace({ route: "/generate/resume-123", path: "/generate/:resumeId" });
    await screen.findByText(/venu madhav pendurthi/i);

    await user.click(screen.getByRole("button", { name: /^word$/i }));

    await waitFor(() => expect(resumeService.exportResumeDocx).toHaveBeenCalledTimes(1));
    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:resume-export");
  });

  it("export failure displays a readable error without discarding the resume", async () => {
    vi.mocked(resumeService.exportResumePdf).mockRejectedValueOnce(new Error("Export failed."));
    const user = userEvent.setup();
    renderWorkspace({ route: "/generate/resume-123", path: "/generate/:resumeId" });
    await screen.findByText(/venu madhav pendurthi/i);

    await user.click(screen.getByRole("button", { name: /^pdf$/i }));

    expect(await screen.findByText(/export failed/i)).toBeInTheDocument();
    expect(screen.getByText(/venu madhav pendurthi/i)).toBeInTheDocument();
  });

  it("historical version export uses the selected historical resume without autosave", async () => {
    vi.mocked(resumeService.listResumes).mockResolvedValueOnce([historicalResumeRecordFixture]);
    vi.mocked(resumeService.getResume).mockResolvedValueOnce(historicalResumeRecordFixture);
    const user = userEvent.setup();
    renderWorkspace({ route: "/generate/resume-history-1", path: "/generate/:resumeId" });
    await screen.findByText(/historical version opened read-only/i);

    await user.click(screen.getByRole("button", { name: /^pdf$/i }));

    expect(resumeService.updateResume).not.toHaveBeenCalled();
    expect(resumeService.exportResumePdf).toHaveBeenCalledWith(token, "resume-history-1", expect.any(Object));
  });

  it("shows low profile completeness warning without blocking optional incompleteness", async () => {
    renderWorkspace({ profile: lowCompletenessProfileFixture });

    expect(await screen.findByText(/profile is 42% complete/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /analyze & match/i })).toBeDisabled();
    expect(screen.getByLabelText(/target job title/i)).toBeEnabled();
  });

  it("clears the job form without deleting the persisted resume", async () => {
    const user = userEvent.setup();
    renderWorkspace({ route: "/generate/resume-123", path: "/generate/:resumeId" });
    await screen.findByText(/venu madhav pendurthi/i);

    await user.click(screen.getByRole("button", { name: /clear/i }));

    expect(screen.getByLabelText(/target job title/i)).toHaveValue("");
    expect(screen.getByPlaceholderText(/paste the full job description/i)).toHaveValue("");
    expect(resumeService.deleteResume).not.toHaveBeenCalled();
  });
});








