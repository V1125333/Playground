import type {
  CandidateLocationSnapshot,
  CandidateProfileRecord,
  ExperienceDateSnapshot,
  GenerateResumeRequestPayload,
  JobAnalysisResponse,
  ResumeGenerationSettingsSnapshot,
} from "../resume/types";
import {
  datePrecedes,
  formatLocationDisplay,
  formatProfileDate,
  migrateLegacyLocation,
  parseProfileDate,
  validateStructuredLocation,
} from "./profileData";
import { hasCategoryPrefix, normalizeSkillName } from "./skillsData";

type BuildGenerateResumeRequestInput = {
  profileRecord: CandidateProfileRecord | null;
  jobDescription: string;
  targetRole: string;
  targetCompany: string;
  experienceLevel: string;
  jobAnalysis: JobAnalysisResponse;
  resumeIntelligencePackageId?: string;
  templateId: string;
  generationSettings: ResumeGenerationSettingsSnapshot;
};

export function buildGenerateResumeRequest(input: BuildGenerateResumeRequestInput): GenerateResumeRequestPayload {
  const profileRecord = input.profileRecord;
  if (!profileRecord?.profileId) {
    throw new Error("Complete your profile before generating a tailored resume.");
  }
  const profile = profileRecord.profileData;
  const [fallbackFirstName, fallbackLastName] = splitName(profile.name);
  const candidate = {
    firstName: profile.firstName?.trim() || fallbackFirstName,
    lastName: profile.lastName?.trim() || fallbackLastName,
    currentTitle: profile.title.trim(),
    email: (profile.contact.email ?? "").trim(),
    phone: (profile.contact.phone ?? "").trim(),
    location: locationSnapshot(profile.contact.locationData, profile.contact.location ?? ""),
  };
  const missing = requiredCandidateErrors(candidate);
  if (missing.length) {
    throw new Error(`Complete required profile fields before generating: ${missing.join(", ")}.`);
  }
  const skills = profile.skills
    .map((group, index) => ({
      categoryId: group.categoryId?.trim() || stableCategoryId(group.categoryName ?? group.category, index),
      categoryName: (group.categoryName ?? group.category).trim(),
      order: Number.isInteger(group.order) ? Number(group.order) : index,
      items: dedupe(group.items.map((item) => normalizeSkillName(item)).filter(Boolean)),
    }))
    .filter((group) => group.categoryName && group.items.length > 0);
  if (!skills.length) {
    throw new Error("Add at least one saved skill category before generating a resume.");
  }
  validateSkillCategories(skills);
  const workExperience = profile.experience
    .map((item) => {
      const isCurrentRole = Boolean(item.isCurrentRole ?? item.endDate?.trim().toLowerCase() === "present");
      const startDate = item.startDateData ?? parseProfileDate(item.startDate ?? "");
      const endDate = isCurrentRole ? null : item.endDateData ?? parseProfileDate(item.endDate ?? "");
      return {
        experienceId: (item.experienceId ?? "").trim(),
        companyName: item.company.trim(),
        clientName: item.clientName?.trim() || null,
        roleTitle: item.role.trim(),
        location: locationSnapshot(item.locationData, item.location ?? ""),
        startDate: dateSnapshot(startDate),
        endDate: endDate ? dateSnapshot(endDate) : null,
        isCurrentRole,
      };
    })
    .filter((item) => item.experienceId || item.companyName || item.roleTitle);
  validateWorkExperience(workExperience);
  const description = input.jobDescription.trim();
  const role = input.targetRole.trim();
  if (!description) throw new Error("Paste a job description before generating a resume.");
  if (!role) throw new Error("Enter a target job title before generating a resume.");

  return {
    profileId: profileRecord.profileId,
    profileVersion: profileRecord.profileVersion,
    resumeIntelligencePackageId: input.resumeIntelligencePackageId,
    candidate,
    skills,
    workExperience,
    job: {
      description,
      targetRole: role,
      targetCompany: input.targetCompany.trim() || null,
      level: input.experienceLevel.trim() || null,
    },
    jobAnalysis: input.jobAnalysis,
    resumePreferences: {
      templateId: input.templateId,
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
    generationSettings: input.generationSettings,
  };
}

function splitName(name: string): [string, string] {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length < 2) return [parts[0] ?? "", ""];
  return [parts[0], parts.slice(1).join(" ")];
}

function locationSnapshot(locationData: Parameters<typeof migrateLegacyLocation>[0], legacyDisplay: string): CandidateLocationSnapshot {
  const migrated = locationData ? migrateLegacyLocation(locationData) : migrateLegacyLocation(legacyDisplay);
  const location = migrated.location;
  return {
    city: location.city,
    state: location.state,
    country: location.country,
    displayValue: formatLocationDisplay(location),
  };
}

function dateSnapshot(value: ReturnType<typeof parseProfileDate>): ExperienceDateSnapshot {
  return {
    year: value?.year ?? 0,
    month: value?.month ?? 0,
    displayValue: formatProfileDate(value),
  };
}

function requiredCandidateErrors(candidate: GenerateResumeRequestPayload["candidate"]): string[] {
  const errors: string[] = [];
  if (!candidate.firstName) errors.push("first name");
  if (!candidate.lastName) errors.push("last name");
  if (!candidate.currentTitle) errors.push("current title");
  if (!candidate.email || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(candidate.email)) errors.push("valid email");
  if (!candidate.phone) errors.push("phone");
  if (!candidate.location.city) errors.push("location city");
  if (!candidate.location.country) errors.push("location country");
  errors.push(...validateStructuredLocation(candidate.location, "candidate location").map((error) => error.replace(/\.$/, "")));
  return errors;
}

function validateWorkExperience(workExperience: GenerateResumeRequestPayload["workExperience"]) {
  if (!workExperience.length) {
    throw new Error("Add at least one saved work experience before generating a resume.");
  }
  for (const item of workExperience) {
    const missing = [];
    if (!item.experienceId) missing.push("experience ID");
    if (!item.companyName) missing.push("company");
    if (!item.roleTitle) missing.push("role");
    if (!item.location.city) missing.push("location city");
    if (!item.location.country) missing.push("location country");
    const locationErrors = validateStructuredLocation(item.location, `${item.companyName || "work experience"} location`);
    if (locationErrors.length) missing.push(...locationErrors);
    if (!item.startDate.displayValue) missing.push("start date");
    if (!item.isCurrentRole && !item.endDate?.displayValue) missing.push("end date");
    if (!item.isCurrentRole && item.endDate && datePrecedes(
      { month: item.endDate.month, year: item.endDate.year },
      { month: item.startDate.month, year: item.startDate.year },
    )) {
      missing.push("end date cannot be before start date");
    }
    if (missing.length) {
      throw new Error(`Complete work experience metadata before generating: ${missing.join(", ")}.`);
    }
  }
}

function validateSkillCategories(skills: GenerateResumeRequestPayload["skills"]) {
  const categoryIds = new Set<string>();
  const categoryNames = new Set<string>();
  for (const category of skills) {
    if (categoryIds.has(category.categoryId)) throw new Error(`Duplicate skill category ID: ${category.categoryId}.`);
    categoryIds.add(category.categoryId);
    const categoryNameKey = category.categoryName.toLowerCase();
    if (categoryNames.has(categoryNameKey)) throw new Error(`Duplicate skill category name: ${category.categoryName}.`);
    categoryNames.add(categoryNameKey);
    const localSkills = new Set<string>();
    for (const skill of category.items) {
      const skillKey = skill.toLowerCase();
      if (hasCategoryPrefix(skill)) throw new Error(`Skill item contains category label text: ${skill}.`);
      if (localSkills.has(skillKey)) throw new Error(`Duplicate skill in ${category.categoryName}: ${skill}.`);
      localSkills.add(skillKey);
    }
  }
}

function dedupe(items: string[]): string[] {
  const seen = new Set<string>();
  const output: string[] = [];
  for (const item of items) {
    const key = item.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      output.push(item);
    }
  }
  return output;
}

function stableCategoryId(category: string, index: number): string {
  const slug = category.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return `skill-category-${index}-${slug || "group"}`;
}
