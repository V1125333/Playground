import type { ReactNode } from "react";
import { contactItems, formatPeriod, hasResumeContent } from "./format";
import type { GeneratedResume } from "./types";

export function ResumeDocument({
  resume,
  editable,
  onResumeChange,
}: {
  resume: GeneratedResume;
  editable: boolean;
  onResumeChange?: (resume: GeneratedResume) => void;
}) {
  const contacts = contactItems(resume.contact);
  const updateResume = (updates: Partial<GeneratedResume>) => onResumeChange?.({ ...resume, ...updates });
  const updateExperience = (index: number, updates: Partial<GeneratedResume["experience"][number]>) => {
    const next = resume.experience.map((item, itemIndex) => (itemIndex === index ? { ...item, ...updates } : item));
    updateResume({ experience: next });
  };
  const updateExperienceBullet = (experienceIndex: number, bulletIndex: number, value: string) => {
    const next = resume.experience.map((item, itemIndex) =>
      itemIndex === experienceIndex
        ? { ...item, bullets: item.bullets.map((bullet, index) => (index === bulletIndex ? value : bullet)) }
        : item,
    );
    updateResume({ experience: next });
  };
  const updateSkillItems = (skillIndex: number, value: string) => {
    const items = value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const next = resume.skills.map((item, index) => (index === skillIndex ? { ...item, items } : item));
    updateResume({ skills: next });
  };

  return (
    <article className="resume-document" aria-label="Generated resume document">
      <header className="resume-header">
        <h1>
          <EditableSpan editable={editable} onChange={(value) => updateResume({ name: value })}>
            {resume.name}
          </EditableSpan>
        </h1>
        {resume.title && (
          <p className="resume-title">
            <EditableSpan editable={editable} onChange={(value) => updateResume({ title: value })}>
              {resume.title}
            </EditableSpan>
          </p>
        )}
        {contacts.length > 0 && <p className="resume-contact">{contacts.join("  |  ")}</p>}
      </header>

      {hasResumeContent(resume) && (
        <>
          {resume.summary && (
            <ResumeSection title="SUMMARY">
              <EditableSpan editable={editable} onChange={(value) => updateResume({ summary: value })}>
                {resume.summary}
              </EditableSpan>
            </ResumeSection>
          )}

          {resume.skills.length > 0 && (
            <ResumeSection title="TECHNICAL SKILLS">
              <div className="resume-skill-list">
                {resume.skills.map((skill, skillIndex) => (
                  <p key={skill.category}>
                    <strong>{skill.category}:</strong>{" "}
                    <EditableSpan editable={editable} onChange={(value) => updateSkillItems(skillIndex, value)}>
                      {skill.items.join(", ")}
                    </EditableSpan>
                  </p>
                ))}
              </div>
            </ResumeSection>
          )}

          {resume.experience.length > 0 && (
            <ResumeSection title="PROFESSIONAL EXPERIENCE">
              {resume.experience.map((experience, experienceIndex) => (
                <div className="resume-block" key={`${experience.company}-${experience.role}`}>
                  <div className="resume-line">
                    <strong>
                      <EditableSpan editable={editable} onChange={(value) => updateExperience(experienceIndex, { company: value })}>
                        {experience.company}
                      </EditableSpan>
                    </strong>
                    <span>{formatPeriod(experience.startDate, experience.endDate)}</span>
                  </div>
                  <p className="resume-role resume-line">
                    <strong>
                      <EditableSpan editable={editable} onChange={(value) => updateExperience(experienceIndex, { role: value })}>
                        {experience.role}
                      </EditableSpan>
                    </strong>
                    {experience.location && (
                      <em>
                        <EditableSpan editable={editable} onChange={(value) => updateExperience(experienceIndex, { location: value })}>
                          {experience.location}
                        </EditableSpan>
                      </em>
                    )}
                  </p>
                  <ResumeBullets
                    bullets={experience.bullets}
                    editable={editable}
                    onBulletChange={(bulletIndex, value) => updateExperienceBullet(experienceIndex, bulletIndex, value)}
                  />
                </div>
              ))}
            </ResumeSection>
          )}

          {resume.projects.length > 0 && (
            <ResumeSection title="PROJECTS">
              {resume.projects.map((project) => (
                <div className="resume-block" key={project.name}>
                  <div className="resume-line">
                    <strong>{[project.name, project.org].filter(Boolean).join(" | ")}</strong>
                    {project.link && <span>{project.link}</span>}
                  </div>
                  <ResumeBullets bullets={project.bullets} editable={editable} />
                  {project.technologies.length > 0 && (
                    <p className="resume-technologies">
                      <strong>Technologies:</strong> {project.technologies.join(", ")}
                    </p>
                  )}
                </div>
              ))}
            </ResumeSection>
          )}

          {resume.education.length > 0 && (
            <ResumeSection title="EDUCATION">
              {resume.education.map((education) => (
                <div className="resume-block" key={`${education.institution}-${education.degree}`}>
                  <div className="resume-line">
                    <strong>{education.degree}</strong>
                    <span>{education.gradYear}</span>
                  </div>
                  <p className="resume-role">
                    {[education.institution, education.location, education.gpa].filter(Boolean).join(" | ")}
                  </p>
                </div>
              ))}
            </ResumeSection>
          )}

          {resume.certifications.length > 0 && (
            <ResumeSection title="CERTIFICATIONS">
              {resume.certifications.map((certification) => (
                <p className="resume-certification" key={certification.name}>
                  <strong>{certification.name}</strong>
                  {formatCertification(certification)}
                </p>
              ))}
            </ResumeSection>
          )}
        </>
      )}
    </article>
  );
}

function formatCertification(certification: GeneratedResume["certifications"][number]) {
  const details = [
    certification.issuer,
    certification.issuedDate ? `Issued ${certification.issuedDate}` : "",
    certification.expiryDate ? `Expires ${certification.expiryDate}` : "",
  ].filter(Boolean);
  return details.length ? ` - ${details.join(" | ")}` : "";
}

function ResumeSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="resume-section">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function ResumeBullets({
  bullets,
  editable,
  onBulletChange,
}: {
  bullets: string[];
  editable: boolean;
  onBulletChange?: (index: number, value: string) => void;
}) {
  if (bullets.length === 0) return null;

  return (
    <ul className="resume-bullets">
      {bullets.map((bullet, index) => (
        <li key={bullet}>
          <EditableSpan editable={editable} onChange={(value) => onBulletChange?.(index, value)}>
            {bullet}
          </EditableSpan>
        </li>
      ))}
    </ul>
  );
}

function EditableSpan({
  editable,
  children,
  onChange,
}: {
  editable: boolean;
  children: string;
  onChange?: (value: string) => void;
}) {
  if (!editable) return <>{children}</>;
  return (
    <span
      contentEditable
      suppressContentEditableWarning
      className="resume-editable"
      onBlur={(event) => onChange?.(event.currentTarget.textContent?.trim() ?? "")}
    >
      {children}
    </span>
  );
}
