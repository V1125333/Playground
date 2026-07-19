import { describe, expect, it } from "vitest";
import {
  buildCandidateProfile,
  normalizeProjectForms,
  profileFormFromCandidateProfile,
  validateProfile,
  type CandidateProfileForm,
} from "./App";
import { profileFixture } from "./test/fixtures/profile";

function profileFormWithProject(): CandidateProfileForm {
  const form = profileFormFromCandidateProfile(profileFixture.profileData);
  return {
    ...form,
    projects: [
      {
        id: "project-provider-portal",
        name: "Provider Portal Modernization",
        org: "Molina Healthcare",
        link: "",
        bullets: "Built C# API workflows\nImproved SQL validation",
        technologies: "C#, ASP.NET Core, SQL Server",
        linkedExperienceIds: ["exp-infosys", "exp-infosys", " exp-euniverse "],
      },
    ],
  };
}

describe("profile project experience mapping", () => {
  it("loads legacy project JSON with empty linked experience IDs", () => {
    const [project] = normalizeProjectForms([
      {
        projectId: "project-legacy",
        name: "Legacy Project",
        bullets: ["Built API workflow."],
        technologies: ["C#", "SQL Server"],
      },
    ]);

    expect(project).toMatchObject({
      id: "project-legacy",
      bullets: "Built API workflow.",
      technologies: "C#, SQL Server",
      linkedExperienceIds: [],
    });
  });

  it("loads snake-case project mappings from API-shaped JSON", () => {
    const [project] = normalizeProjectForms([
      {
        projectId: "project-api",
        name: "API Project",
        bullets: ["Integrated REST API."],
        technologies: ["ASP.NET Core"],
        linked_experience_ids: ["exp-infosys", " exp-infosys ", "", "exp-euniverse"],
      },
    ]);

    expect(project.linkedExperienceIds).toEqual(["exp-infosys", "exp-euniverse"]);
  });

  it("saves project mappings as linkedExperienceIds in the candidate payload", () => {
    const payload = buildCandidateProfile(profileFormWithProject());

    expect(payload.projects).toEqual([
      expect.objectContaining({
        projectId: "project-provider-portal",
        bullets: ["Built C# API workflows", "Improved SQL validation"],
        technologies: ["C#", "ASP.NET Core", "SQL Server"],
        linkedExperienceIds: ["exp-infosys", "exp-euniverse"],
      }),
    ]);
  });

  it("loads persisted project mappings back into the editable profile form", () => {
    const payload = buildCandidateProfile(profileFormWithProject());
    const reloaded = profileFormFromCandidateProfile(payload);

    expect(reloaded.projects[0]).toEqual(expect.objectContaining({
      id: "project-provider-portal",
      linkedExperienceIds: ["exp-infosys", "exp-euniverse"],
      bullets: "Built C# API workflows\nImproved SQL validation",
      technologies: "C#, ASP.NET Core, SQL Server",
    }));
  });

  it("rejects project mappings that reference deleted work experiences", () => {
    const form = profileFormWithProject();
    const deletedExperience = {
      ...form,
      experience: form.experience.filter((experience) => experience.id !== "exp-infosys"),
      projects: [{ ...form.projects[0], linkedExperienceIds: ["exp-infosys"] }],
    };

    expect(validateProfile(deletedExperience)).toContain("Project 1 references a work experience that no longer exists.");
  });
});
