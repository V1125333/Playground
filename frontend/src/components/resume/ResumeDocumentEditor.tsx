import { ChevronDown, ChevronUp, EyeOff, GripVertical, Info, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Button, Badge } from "../ui";
import { cn } from "../../lib/utils";
import { contactItems, formatPeriod } from "../../resume/format";
import type {
  GeneratedResume,
  GeneratedResumeSection,
  ProfileEvidenceItem,
  RequirementMatch,
  StructuredGeneratedResume,
} from "../../resume/types";

type ExperienceEntry = {
  company: string;
  role: string;
  location?: string;
  startDate?: string;
  endDate?: string;
  bullets: string[];
  sourceRecordId?: string;
};

type ProjectEntry = {
  name: string;
  org?: string;
  link?: string;
  bullets: string[];
  technologies?: string[];
  sourceRecordId?: string;
};

type SkillEntry = { category: string; items: string[] };

export function ResumeDocumentEditor({
  resume,
  profile,
  evidence,
  requirements,
  validationWarnings,
  editable,
  onChange,
}: {
  resume: StructuredGeneratedResume;
  profile: GeneratedResume | null;
  evidence: ProfileEvidenceItem[];
  requirements: RequirementMatch[];
  validationWarnings: string[];
  editable: boolean;
  onChange: (resume: StructuredGeneratedResume) => void;
}) {
  const sortedSections = useMemo(
    () => [...resume.sections].filter((section) => section.visible !== false && contentHasValue(section.content)).sort((a, b) => a.order - b.order),
    [resume.sections],
  );

  const updateSection = (sectionId: string, updater: (section: GeneratedResumeSection) => GeneratedResumeSection) => {
    const sections = resume.sections.map((section) => (section.sectionId === sectionId ? updater(section) : section));
    onChange(touchResume({ ...resume, sections }));
  };

  const moveSection = (sectionId: string, direction: -1 | 1) => {
    const ordered = [...resume.sections].sort((a, b) => a.order - b.order);
    const index = ordered.findIndex((section) => section.sectionId === sectionId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= ordered.length) return;
    const next = [...ordered];
    [next[index], next[target]] = [next[target], next[index]];
    const reordered = next.map((section, itemIndex) => ({ ...section, order: itemIndex + 1 }));
    onChange(touchResume({ ...resume, sections: reordered }));
  };

  const hideSection = (sectionId: string) => {
    if (!window.confirm("Hide this resume section from the current draft?")) return;
    updateSection(sectionId, (section) => ({ ...section, visible: false }));
  };

  return (
    <div className="resume-editor-shell">
      <article className="resume-document resume-document-editor" aria-label="Editable generated resume document">
        <ResumeHeader resume={resume} profile={profile} />
        {validationWarnings.length > 0 && (
          <div className="mb-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-[10pt] text-amber-900">
            <strong>Needs review:</strong> {validationWarnings[0]}
          </div>
        )}
        {sortedSections.map((section, index) => (
          <ResumeSectionEditor
            key={section.sectionId}
            section={section}
            editable={editable}
            evidence={evidence}
            requirements={requirements}
            canMoveUp={index > 0}
            canMoveDown={index < sortedSections.length - 1}
            onMoveUp={() => moveSection(section.sectionId, -1)}
            onMoveDown={() => moveSection(section.sectionId, 1)}
            onHide={() => hideSection(section.sectionId)}
            onChange={(nextSection) => updateSection(section.sectionId, () => nextSection)}
          />
        ))}
      </article>
    </div>
  );
}

function ResumeHeader({ resume, profile }: { resume: StructuredGeneratedResume; profile: GeneratedResume | null }) {
  const name = profile?.name || resume.resumeName.replace(` - ${resume.targetJobTitle}`, "");
  const title = profile?.title || "";
  const contacts = contactItems(resume.contact);
  return (
    <header className="resume-header">
      <h1>{name}</h1>
      {title && <p className="resume-title">{title}</p>}
      {contacts.length > 0 && <p className="resume-contact">{contacts.join("  |  ")}</p>}
    </header>
  );
}

function ResumeSectionEditor({
  section,
  editable,
  evidence,
  requirements,
  canMoveUp,
  canMoveDown,
  onMoveUp,
  onMoveDown,
  onHide,
  onChange,
}: {
  section: GeneratedResumeSection;
  editable: boolean;
  evidence: ProfileEvidenceItem[];
  requirements: RequirementMatch[];
  canMoveUp: boolean;
  canMoveDown: boolean;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onHide: () => void;
  onChange: (section: GeneratedResumeSection) => void;
}) {
  return (
    <section className="resume-section resume-section-editable">
      <div className="resume-section-heading-row">
        <h2>{section.title}</h2>
        {editable && (
          <div className="resume-section-toolbar" aria-label={`${section.title} section controls`}>
            <button type="button" aria-label={`Move ${section.title} up`} disabled={!canMoveUp} onClick={onMoveUp}>
              <ChevronUp size={13} />
            </button>
            <button type="button" aria-label={`Move ${section.title} down`} disabled={!canMoveDown} onClick={onMoveDown}>
              <ChevronDown size={13} />
            </button>
            <EvidenceButton section={section} evidence={evidence} requirements={requirements} />
            <button type="button" aria-label={`Hide ${section.title}`} onClick={onHide}>
              <EyeOff size={13} />
            </button>
          </div>
        )}
      </div>
      {section.type === "summary" && <SummaryEditor section={section} editable={editable} onChange={onChange} />}
      {section.type === "skills" && <SkillsEditor section={section} editable={editable} onChange={onChange} />}
      {section.type === "experience" && <ExperienceEditor section={section} editable={editable} onChange={onChange} />}
      {section.type === "projects" && <ProjectsEditor section={section} editable={editable} onChange={onChange} />}
      {section.type === "education" && <EducationEditor section={section} />}
      {section.type === "certifications" && <CertificationsEditor section={section} />}
    </section>
  );
}

function SummaryEditor({ section, editable, onChange }: SectionEditorProps) {
  return (
    <EditableText
      value={String(section.content ?? "")}
      editable={editable}
      className="block"
      onChange={(value) => onChange(markSectionEdited(section, value))}
    />
  );
}

function SkillsEditor({ section, editable, onChange }: SectionEditorProps) {
  const content = asList<SkillEntry>(section.content);
  const updateSkill = (index: number, value: string) => {
    const items = value.split(",").map((item) => item.trim()).filter(Boolean);
    const next = content.map((group, groupIndex) => (groupIndex === index ? { ...group, items } : group));
    onChange(markSectionEdited(section, next));
  };
  return (
    <div className="resume-skill-list">
      {content.map((group, index) => (
        <p key={`${group.category}-${index}`}>
          <strong>{group.category}:</strong>{" "}
          <EditableText
            value={(group.items ?? []).join(", ")}
            editable={editable}
            onChange={(value) => updateSkill(index, value)}
          />
        </p>
      ))}
    </div>
  );
}

function ExperienceEditor({ section, editable, onChange }: SectionEditorProps) {
  const content = asList<ExperienceEntry>(section.content);
  const updateEntry = (index: number, updates: Partial<ExperienceEntry>) => {
    const next = content.map((entry, entryIndex) => (entryIndex === index ? { ...entry, ...updates } : entry));
    onChange(markSectionEdited(section, next));
  };
  return (
    <>
      {content.map((entry, index) => (
        <div className="resume-block resume-entry-editable" key={`${entry.sourceRecordId ?? entry.company}-${index}`}>
          <div className="resume-line">
            <strong>{entry.company}</strong>
            <span>{formatPeriod(entry.startDate, entry.endDate)}</span>
          </div>
          <p className="resume-role resume-line">
            <strong>{entry.role}</strong>
            {entry.location && <em>{entry.location}</em>}
          </p>
          <BulletList
            bullets={entry.bullets ?? []}
            editable={editable}
            onChange={(bullets) => updateEntry(index, { bullets })}
          />
        </div>
      ))}
    </>
  );
}

function ProjectsEditor({ section, editable, onChange }: SectionEditorProps) {
  const content = asList<ProjectEntry>(section.content);
  const updateProject = (index: number, updates: Partial<ProjectEntry>) => {
    const next = content.map((entry, entryIndex) => (entryIndex === index ? { ...entry, ...updates } : entry));
    onChange(markSectionEdited(section, next));
  };
  return (
    <>
      {content.map((project, index) => (
        <div className="resume-block resume-entry-editable" key={`${project.sourceRecordId ?? project.name}-${index}`}>
          <div className="resume-line">
            <strong>{[project.name, project.org].filter(Boolean).join(" | ")}</strong>
            {project.link && <span>{project.link}</span>}
          </div>
          <BulletList
            bullets={project.bullets ?? []}
            editable={editable}
            onChange={(bullets) => updateProject(index, { bullets })}
          />
          {project.technologies?.length ? (
            <p className="resume-technologies">
              <strong>Technologies:</strong> {project.technologies.join(", ")}
            </p>
          ) : null}
        </div>
      ))}
    </>
  );
}

function EducationEditor({ section }: { section: GeneratedResumeSection }) {
  const content = asList<{ degree: string; institution: string; location?: string; gradYear?: string; gpa?: string }>(section.content);
  return (
    <>
      {content.map((education, index) => (
        <div className="resume-block" key={`${education.degree}-${index}`}>
          <div className="resume-line">
            <strong>{education.degree}</strong>
            <span>{education.gradYear}</span>
          </div>
          <p className="resume-role">{[education.institution, education.location, education.gpa].filter(Boolean).join(" | ")}</p>
        </div>
      ))}
    </>
  );
}

function CertificationsEditor({ section }: { section: GeneratedResumeSection }) {
  const content = asList<{ name: string; issuer?: string; issuedDate?: string; expiryDate?: string }>(section.content);
  return (
    <>
      {content.map((certification, index) => (
        <p className="resume-certification" key={`${certification.name}-${index}`}>
          <strong>{certification.name}</strong>
          {formatCertification(certification)}
        </p>
      ))}
    </>
  );
}

function BulletList({
  bullets,
  editable,
  onChange,
}: {
  bullets: string[];
  editable: boolean;
  onChange: (bullets: string[]) => void;
}) {
  const updateBullet = (index: number, value: string) => onChange(bullets.map((bullet, itemIndex) => (itemIndex === index ? value : bullet)));
  const addBullet = () => onChange([...bullets, "Describe a truthful, evidence-supported accomplishment."]);
  const deleteBullet = (index: number) => {
    if (!window.confirm("Delete this bullet from the current draft?")) return;
    onChange(bullets.filter((_, itemIndex) => itemIndex !== index));
  };
  const moveBullet = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= bullets.length) return;
    const next = [...bullets];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };

  return (
    <div>
      <ul className="resume-bullets">
        {bullets.map((bullet, index) => (
          <li className="resume-bullet-editable" key={`bullet-${index}`}>
            <EditableText value={bullet} editable={editable} onChange={(value) => updateBullet(index, value)} />
            {editable && (
              <span className="resume-bullet-toolbar">
                <button type="button" aria-label="Move bullet up" disabled={index === 0} onClick={() => moveBullet(index, -1)}>
                  <ChevronUp size={12} />
                </button>
                <button type="button" aria-label="Move bullet down" disabled={index === bullets.length - 1} onClick={() => moveBullet(index, 1)}>
                  <ChevronDown size={12} />
                </button>
                <button type="button" aria-label="Delete bullet" onClick={() => deleteBullet(index)}>
                  <Trash2 size={12} />
                </button>
              </span>
            )}
          </li>
        ))}
      </ul>
      {editable && (
        <button type="button" className="resume-add-bullet" onClick={addBullet}>
          <Plus size={12} /> Add bullet
        </button>
      )}
    </div>
  );
}

function EvidenceButton({
  section,
  evidence,
  requirements,
}: {
  section: GeneratedResumeSection;
  evidence: ProfileEvidenceItem[];
  requirements: RequirementMatch[];
}) {
  const [open, setOpen] = useState(false);
  const evidenceById = new Map(evidence.map((item) => [item.evidenceId, item]));
  const requirementById = new Map(requirements.map((item) => [item.requirementId, item]));
  const evidenceItems = section.provenance.supportingEvidenceIds.map((id) => evidenceById.get(id)).filter(Boolean) as ProfileEvidenceItem[];
  const requirementItems = section.provenance.supportedRequirementIds.map((id) => requirementById.get(id)).filter(Boolean) as RequirementMatch[];

  return (
    <span className="relative">
      <button type="button" aria-label="Show evidence details" onClick={() => setOpen((current) => !current)}>
        <Info size={13} />
      </button>
      {open && (
        <div className="resume-evidence-popover">
          <p className="font-semibold">Supported by</p>
          {evidenceItems.length ? (
            <ul>
              {evidenceItems.slice(0, 4).map((item) => (
                <li key={item.evidenceId}>
                  <strong>{item.sourceLabel}</strong>
                  <span>{item.originalText}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-slate-500">No supporting evidence attached.</p>
          )}
          {requirementItems.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {requirementItems.slice(0, 5).map((item) => (
                <Badge key={item.requirementId} tone={item.classification === "adjacent" ? "amber" : "green"}>
                  {item.requirementValue}
                </Badge>
              ))}
            </div>
          )}
        </div>
      )}
    </span>
  );
}

function EditableText({
  value,
  editable,
  className,
  onChange,
}: {
  value: string;
  editable: boolean;
  className?: string;
  onChange: (value: string) => void;
}) {
  if (!editable) return <span className={className}>{value}</span>;
  return (
    <span
      role="textbox"
      aria-label="Editable resume text"
      contentEditable
      suppressContentEditableWarning
      className={cn("resume-editable", className)}
      onInput={(event) => onChange(event.currentTarget.textContent ?? "")}
      onBlur={(event) => onChange(event.currentTarget.textContent?.trim() ?? "")}
    >
      {value}
    </span>
  );
}

type SectionEditorProps = {
  section: GeneratedResumeSection;
  editable: boolean;
  onChange: (section: GeneratedResumeSection) => void;
};

function markSectionEdited(section: GeneratedResumeSection, content: unknown): GeneratedResumeSection {
  return {
    ...section,
    content,
    provenance: {
      ...section.provenance,
      validationStatus: "needs_review",
      warnings: Array.from(new Set([...(section.provenance.warnings ?? []), "User edited this content; validation review is recommended."])),
    },
  };
}

function touchResume(resume: StructuredGeneratedResume): StructuredGeneratedResume {
  return { ...resume, updatedAt: new Date().toISOString() };
}

function asList<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function contentHasValue(value: unknown): boolean {
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "string") return value.trim().length > 0;
  if (value && typeof value === "object") return Object.keys(value).length > 0;
  return Boolean(value);
}

function formatCertification(certification: { issuer?: string; issuedDate?: string; expiryDate?: string }) {
  const details = [
    certification.issuer,
    certification.issuedDate ? `Issued ${certification.issuedDate}` : "",
    certification.expiryDate ? `Expires ${certification.expiryDate}` : "",
  ].filter(Boolean);
  return details.length ? ` - ${details.join(" | ")}` : "";
}
