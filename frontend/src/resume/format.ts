import type { GeneratedResume } from "./types";

export const resumeFormatConfig = {
  paperSize: "US Letter",
  fontFamily: '"Times New Roman", Georgia, serif',
  marginsIn: { top: 0.55, bottom: 0.55, left: 0.6, right: 0.6 },
  sectionOrder: ["SUMMARY", "TECHNICAL SKILLS", "PROFESSIONAL EXPERIENCE", "PROJECTS", "EDUCATION", "CERTIFICATIONS"],
} as const;

export function contactItems(contact: GeneratedResume["contact"]) {
  return [
    contact.phone,
    contact.email,
    contact.location,
    contact.linkedin,
    contact.github,
    contact.portfolio,
  ].filter((item): item is string => Boolean(item?.trim()));
}

export function headerContactItems(header: {
  email?: string;
  phone?: string;
  location?: string;
  linkedinUrl?: string;
  githubUrl?: string;
  portfolioUrl?: string;
}) {
  return [
    header.phone,
    header.email,
    header.location,
    header.linkedinUrl,
    header.githubUrl,
    header.portfolioUrl,
  ].filter((item): item is string => Boolean(item?.trim()));
}

export function formatPeriod(startDate?: string, endDate?: string) {
  return [formatDate(startDate), formatDate(endDate)].filter(Boolean).join(" - ");
}

function formatDate(value?: string) {
  if (!value) return "";
  if (value === "Present") return value;
  const [year, month] = value.split("-");
  if (!year || !month) return value;
  const date = new Date(Number(year), Number(month) - 1, 1);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", { month: "short", year: "numeric" });
}

export function hasResumeContent(resume: GeneratedResume) {
  return Boolean(
    resume.summary ||
      resume.skills.length ||
      resume.experience.length ||
      resume.projects.length ||
      resume.education.length ||
      resume.certifications.length,
  );
}
