import { describe, expect, it } from "vitest";
import { buildGenerateResumeRequest } from "./generateResumeRequest";
import { jobAnalysisFixture } from "../test/fixtures/jobAnalysis";
import { profileFixture } from "../test/fixtures/profile";

const generationSettings = {
  maximumPages: 2,
  bulletsPerRecentRole: 5,
  bulletsPerOlderRole: 4,
  includeProjects: true,
  includeCertifications: true,
  includeUnmatchedKeywords: false,
  writingStyle: "balanced",
};

function build(overrides: Partial<Parameters<typeof buildGenerateResumeRequest>[0]> = {}) {
  return buildGenerateResumeRequest({
    profileRecord: profileFixture,
    jobDescription: "Need a senior engineer with C#, APIs, SQL, and Agile delivery.",
    targetRole: "Software Engineer IV",
    targetCompany: "Velera",
    experienceLevel: "Senior",
    jobAnalysis: jobAnalysisFixture,
    templateId: "classic-ats",
    generationSettings,
    ...overrides,
  });
}

describe("buildGenerateResumeRequest", () => {
  it("maps persisted profile identity, skills, work experience, job, preferences, and settings", () => {
    const payload = build({ resumeIntelligencePackageId: "package-123" });

    expect(payload.profileId).toBe("profile-123");
    expect(payload.profileVersion).toBe(3);
    expect(payload.resumeIntelligencePackageId).toBe("package-123");
    expect(payload.candidate).toMatchObject({
      firstName: "Venu Madhav",
      lastName: "Pendurthi",
      currentTitle: "Senior .NET Developer",
      email: "venu@example.com",
      phone: "+12014436937",
      location: { city: "Hartford", state: "CT", country: "United States", displayValue: "Hartford, CT" },
    });
    expect(payload.skills[0]).toMatchObject({
      categoryId: "programming-languages",
      categoryName: "Programming Languages",
      order: 0,
      items: ["C#", "SQL"],
    });
    expect(payload.workExperience[0]).toMatchObject({
      experienceId: "exp-infosys",
      companyName: "Infosys",
      clientName: "Molina Healthcare",
      roleTitle: "Senior .NET Developer",
      location: { city: "Hartford", state: "CT", country: "United States", displayValue: "Hartford, CT" },
      startDate: { year: 2025, month: 1, displayValue: "Jan 2025" },
      endDate: null,
      isCurrentRole: true,
    });
    expect(payload.job).toEqual({
      description: "Need a senior engineer with C#, APIs, SQL, and Agile delivery.",
      targetRole: "Software Engineer IV",
      targetCompany: "Velera",
      level: "Senior",
    });
    expect(payload.resumePreferences.headerVisibility).toMatchObject({
      linkedinUrl: false,
      githubUrl: false,
      portfolioUrl: false,
    });
    expect(payload.generationSettings).toBe(generationSettings);
  });

  it("does not include raw notes or generated bullets in work experience snapshots", () => {
    const payload = build();
    const serialized = JSON.stringify(payload.workExperience);

    expect(serialized).not.toContain("rawNotes");
    expect(serialized).not.toContain("bullets");
    expect(serialized).not.toContain("responsibilities");
    expect(serialized).not.toContain("achievements");
    expect(serialized).not.toContain("technologies");
    expect(serialized).not.toContain("metrics");
    expect(serialized).not.toContain("improving release quality");
  });

  it("sends structured skill categories directly instead of one Technical Skills bucket", () => {
    const payload = build();

    expect(payload.skills.map((group) => group.categoryName)).toEqual([
      "Programming Languages",
      "Backend Development",
      "Methodologies & Ways of Working",
    ]);
    expect(payload.skills).not.toContainEqual(expect.objectContaining({ categoryName: "Technical Skills" }));
    expect(JSON.stringify(payload.skills)).not.toContain("Programming Languages:");
  });

  it("does not include empty approved profile categories in the generate request", () => {
    const payload = build({
      profileRecord: {
        ...profileFixture,
        profileData: {
          ...profileFixture.profileData,
          skills: [
            ...profileFixture.profileData.skills,
            {
              category: "Cloud Platforms & Services",
              categoryId: "cloud-platforms-services",
              categoryName: "Cloud Platforms & Services",
              order: 3,
              items: [],
            },
          ],
        },
      },
    });

    expect(payload.skills.map((group) => group.categoryId)).not.toContain("cloud-platforms-services");
  });

  it("rejects category label text inside a skill item", () => {
    expect(() => build({
      profileRecord: {
        ...profileFixture,
        profileData: {
          ...profileFixture.profileData,
          skills: [{ category: "Programming Languages", categoryId: "programming-languages", categoryName: "Programming Languages", order: 0, items: ["Programming Languages: C#"] }],
        },
      },
    })).toThrow(/category label/i);
  });

  it("maps missing client to null and never copies state into country", () => {
    const payload = build();

    expect(payload.workExperience[1]).toMatchObject({
      clientName: null,
      location: { city: "Chicago", state: "IL", country: "United States", displayValue: "Chicago, IL" },
      startDate: { month: 7, year: 2023, displayValue: "Jul 2023" },
      endDate: { month: 1, year: 2025, displayValue: "Jan 2025" },
      isCurrentRole: false,
    });
    expect(payload.workExperience[1].location.country).not.toBe("IL");
    expect(payload.workExperience[0].location.country).not.toBe("CT");
  });

  it("uses controlled legacy location migration only as a compatibility fallback", () => {
    const payload = build({
      profileRecord: {
        ...profileFixture,
        profileData: {
          ...profileFixture.profileData,
          contact: { ...profileFixture.profileData.contact, locationData: undefined, location: "Hartford, CT" },
          experience: [
            {
              ...profileFixture.profileData.experience[0],
              locationData: undefined,
              location: "Visakhapatnam, Andhra Pradesh",
            },
          ],
        },
      },
    });

    expect(payload.candidate.location).toMatchObject({ city: "Hartford", state: "CT", country: "United States" });
    expect(payload.workExperience[0].location).toMatchObject({ city: "Visakhapatnam", state: "Andhra Pradesh", country: "India" });
  });

  it("rejects ambiguous legacy locations instead of copying city into country", () => {
    expect(() => build({
      profileRecord: {
        ...profileFixture,
        profileData: {
          ...profileFixture.profileData,
          contact: { ...profileFixture.profileData.contact, locationData: undefined, location: "Hyderabad" },
        },
      },
    })).toThrow(/location country/i);
  });

  it("blocks generation when the saved profile is missing required candidate details", () => {
    expect(() => build({
      profileRecord: {
        ...profileFixture,
        profileData: {
          ...profileFixture.profileData,
          contact: { ...profileFixture.profileData.contact, email: "" },
        },
      },
    })).toThrow(/valid email/i);
  });

  it("blocks generation when no persisted profile exists", () => {
    expect(() => build({ profileRecord: null })).toThrow(/complete your profile/i);
  });
});
