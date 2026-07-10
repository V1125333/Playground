import type { CandidateProfileRecord } from "../../resume/types";

export const profileFixture: CandidateProfileRecord = {
  profileId: "profile-123",
  userId: "user-123",
  profileName: "Primary Profile",
  profileVersion: 3,
  schemaVersion: 1,
  completenessScore: 86,
  contentHash: "profile-hash",
  createdAt: "2026-07-01T10:00:00.000Z",
  updatedAt: "2026-07-01T10:00:00.000Z",
  profileData: {
    name: "Venu Madhav Pendurthi",
    title: "Senior .NET Developer",
    contact: {
      email: "venu@example.com",
      phone: "+12014436937",
      location: "Hartford, CT",
      linkedin: "https://www.linkedin.com/in/venukyr91/",
    },
    summary: "Senior .NET developer with enterprise delivery experience.",
    skills: [
      { category: "Languages", items: ["C#", "SQL"] },
      { category: "Backend", items: [".NET", "ASP.NET Core", "REST APIs"] },
      { category: "Delivery", items: ["Agile/Scrum", "Code Review", "Release Management"] },
    ],
    experience: [
      {
        experienceId: "exp-infosys",
        company: "Infosys",
        role: "Senior .NET Developer",
        location: "Hartford, CT",
        startDate: "2025-01",
        endDate: "Present",
        rawNotes:
          "Built C# and ASP.NET Core REST API enhancements with SQL Server. Led code reviews and Agile release validation, improving release quality by 20%.",
        bullets: [],
        metricFlags: ["20% release quality improvement"],
      },
      {
        experienceId: "exp-euniverse",
        company: "E-Universe Technologies LLC",
        role: "Sr. Full Stack .NET Developer",
        location: "Chicago, IL",
        startDate: "2023-07",
        endDate: "2025-01",
        rawNotes: "Developed Angular and ASP.NET Core modules and integrated REST APIs.",
        bullets: [],
        metricFlags: [],
      },
    ],
    projects: [],
    education: [
      {
        educationId: "edu-1",
        degree: "Master of Science in Computer Science",
        institution: "University of Central Missouri",
        location: "Warrensburg, MO",
        gradYear: "2022",
        gpa: "",
      },
    ],
    certifications: [],
  },
};

export const lowCompletenessProfileFixture: CandidateProfileRecord = {
  ...profileFixture,
  completenessScore: 42,
};
