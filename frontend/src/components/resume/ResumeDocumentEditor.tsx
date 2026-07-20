import { ChevronDown, ChevronUp, EyeOff, GripVertical, Info, Plus, Sparkles, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Button, Badge } from "../ui";
import { cn } from "../../lib/utils";
import { contactItems, formatPeriod, headerContactItems } from "../../resume/format";
import { applySectionEnhancement, enhanceResumeSection } from "../../services/resumeService";
import type {
  EnhancementMode,
  GeneratedResume,
  GeneratedResumeBullet,
  GeneratedResumeSection,
  ProfileEvidenceItem,
  RequirementMatch,
  SectionEnhancementResponse,
  SectionEnhancementSuggestion,
  StructuredGeneratedResume,
  StructuredResumeRecord,
} from "../../resume/types";

type BulletValue = string | Partial<GeneratedResumeBullet>;

type ExperienceEntry = {
  company: string;
  role: string;
  location?: string;
  startDate?: string;
  endDate?: string;
  bullets: BulletValue[];
  sourceRecordId?: string;
};

type ProjectEntry = {
  name: string;
  org?: string;
  link?: string;
  bullets: BulletValue[];
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
  authToken = "",
  currentRecord = null,
  onPersistedChange,
  onChange,
}: {
  resume: StructuredGeneratedResume;
  profile: GeneratedResume | null;
  evidence: ProfileEvidenceItem[];
  requirements: RequirementMatch[];
  validationWarnings: string[];
  editable: boolean;
  authToken?: string;
  currentRecord?: StructuredResumeRecord | null;
  onPersistedChange?: (record: StructuredResumeRecord) => void;
  onChange: (resume: StructuredGeneratedResume) => void;
}) {
  const [enhancementTarget, setEnhancementTarget] = useState<EnhancementTarget | null>(null);
  const sortedSections = useMemo(
    () => [...resume.sections].filter((section) => section.visible !== false && contentHasValue(section.content)).sort((a, b) => a.order - b.order),
    [resume.sections],
  );
  const canEnhance = editable && Boolean(authToken && currentRecord?.resumeId);

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
            onEnhance={canEnhance ? setEnhancementTarget : undefined}
            onChange={(nextSection) => updateSection(section.sectionId, () => nextSection)}
          />
        ))}
      </article>
      {enhancementTarget && currentRecord && authToken && (
        <SectionEnhancementDialog
          target={enhancementTarget}
          authToken={authToken}
          currentRecord={currentRecord}
          onClose={() => setEnhancementTarget(null)}
          onApplied={(record) => {
            onPersistedChange?.(record);
            onChange(record.resumeJson);
            setEnhancementTarget(null);
          }}
        />
      )}
    </div>
  );
}

function ResumeHeader({ resume, profile }: { resume: StructuredGeneratedResume; profile: GeneratedResume | null }) {
  const name = resume.resumeHeader ? resume.resumeHeader.fullName ?? "" : profile?.name ?? resume.resumeName.replace(` - ${resume.targetJobTitle}`, "");
  const title = resume.resumeHeader ? resume.resumeHeader.currentTitle ?? "" : profile?.title ?? "";
  const contacts = resume.resumeHeader ? headerContactItems(resume.resumeHeader) : contactItems(resume.contact);
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
  onEnhance,
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
  onEnhance?: (target: EnhancementTarget) => void;
  onChange: (section: GeneratedResumeSection) => void;
}) {
  const canEnhanceSection = Boolean(onEnhance && section.type === "summary" && typeof section.content === "string");
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
            {canEnhanceSection && (
              <button
                type="button"
                aria-label={`Enhance ${section.title} with AI`}
                title="Enhance with AI"
                onClick={() => onEnhance?.({
                  sectionType: "summary",
                  sectionId: section.sectionId,
                  parentSectionId: section.sectionId,
                  currentText: String(section.content ?? ""),
                  maximumWords: 90,
                })}
              >
                <Sparkles size={13} />
              </button>
            )}
            {section.type === "skills" && (
              <button type="button" aria-label="Skills enhancement unavailable" title="Skills are controlled by Skills Intelligence and cannot be freely rewritten by AI." disabled>
                <Sparkles size={13} />
              </button>
            )}
            <EvidenceButton section={section} evidence={evidence} requirements={requirements} />
            <button type="button" aria-label={`Hide ${section.title}`} onClick={onHide}>
              <EyeOff size={13} />
            </button>
          </div>
        )}
      </div>
      {section.type === "summary" && <SummaryEditor section={section} editable={editable} onChange={onChange} />}
      {section.type === "skills" && <SkillsEditor section={section} editable={editable} onChange={onChange} />}
      {section.type === "experience" && <ExperienceEditor section={section} editable={editable} onEnhance={onEnhance} onChange={onChange} />}
      {section.type === "projects" && <ProjectsEditor section={section} editable={editable} onEnhance={onEnhance} onChange={onChange} />}
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

function ExperienceEditor({ section, editable, onEnhance, onChange }: SectionEditorProps & { onEnhance?: (target: EnhancementTarget) => void }) {
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
          {editable && onEnhance && (
            <button
              type="button"
              className="resume-enhance-inline"
              onClick={() => onEnhance({
                sectionType: "experience_role",
                sectionId: entry.sourceRecordId || `experience:${index}`,
                parentSectionId: section.sectionId,
                currentText: (entry.bullets ?? []).map((bullet) => `- ${bulletText(bullet)}`).join("\n"),
                maximumWords: 220,
              })}
            >
              <Sparkles size={12} /> Enhance all bullets
            </button>
          )}
          <BulletList
            bullets={entry.bullets ?? []}
            editable={editable}
            parentSectionId={section.sectionId}
            parentRecordId={entry.sourceRecordId || `experience:${index}`}
            sectionType="experience_bullet"
            onEnhance={onEnhance}
            onChange={(bullets) => updateEntry(index, { bullets })}
          />
        </div>
      ))}
    </>
  );
}

function ProjectsEditor({ section, editable, onEnhance, onChange }: SectionEditorProps & { onEnhance?: (target: EnhancementTarget) => void }) {
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
            parentSectionId={section.sectionId}
            parentRecordId={project.sourceRecordId || project.name || `project:${index}`}
            sectionType="project_bullet"
            onEnhance={onEnhance}
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
  parentSectionId,
  parentRecordId,
  sectionType,
  onEnhance,
  onChange,
}: {
  bullets: BulletValue[];
  editable: boolean;
  parentSectionId?: string;
  parentRecordId?: string;
  sectionType?: "experience_bullet" | "project_bullet";
  onEnhance?: (target: EnhancementTarget) => void;
  onChange: (bullets: BulletValue[]) => void;
}) {
  const updateBullet = (index: number, value: string) => onChange(bullets.map((bullet, itemIndex) => (itemIndex === index ? updateBulletText(bullet, value) : bullet)));
  const addBullet = () => onChange([...bullets, createManualBullet(bullets.length + 1)]);
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
            <EditableText value={bulletText(bullet)} editable={editable} onChange={(value) => updateBullet(index, value)} />
            {editable && (
              <span className="resume-bullet-toolbar">
                <button type="button" aria-label="Move bullet up" disabled={index === 0} onClick={() => moveBullet(index, -1)}>
                  <ChevronUp size={12} />
                </button>
                <button type="button" aria-label="Move bullet down" disabled={index === bullets.length - 1} onClick={() => moveBullet(index, 1)}>
                  <ChevronDown size={12} />
                </button>
                {onEnhance && sectionType && parentSectionId && (
                  <button
                    type="button"
                    aria-label="Enhance bullet with AI"
                    title="Enhance with AI"
                    onClick={() => onEnhance({
                      sectionType,
                      sectionId: bulletEnhancementId(bullet, parentRecordId || "entry", index),
                      parentSectionId,
                      currentText: bulletText(bullet),
                      maximumWords: 38,
                    })}
                  >
                    <Sparkles size={12} />
                  </button>
                )}
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

type EnhancementTarget = {
  sectionType: "summary" | "experience_bullet" | "experience_role" | "project_bullet" | "custom_section_text";
  sectionId: string;
  parentSectionId: string;
  currentText: string;
  maximumWords: number;
};

const enhancementModes: Array<{ value: EnhancementMode; label: string }> = [
  { value: "polish", label: "Polish" },
  { value: "concise", label: "Make concise" },
  { value: "strengthen", label: "Strengthen wording" },
  { value: "ats_optimize", label: "Improve ATS phrasing" },
  { value: "grammar", label: "Fix grammar" },
  { value: "reduce_repetition", label: "Reduce repetition" },
  { value: "custom", label: "Custom instruction" },
];

function SectionEnhancementDialog({
  target,
  authToken,
  currentRecord,
  onClose,
  onApplied,
}: {
  target: EnhancementTarget;
  authToken: string;
  currentRecord: StructuredResumeRecord;
  onClose: () => void;
  onApplied: (record: StructuredResumeRecord) => void;
}) {
  const [mode, setMode] = useState<EnhancementMode>("polish");
  const [instruction, setInstruction] = useState("");
  const [response, setResponse] = useState<SectionEnhancementResponse | null>(null);
  const [selectedSuggestion, setSelectedSuggestion] = useState<SectionEnhancementSuggestion | null>(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState("");

  const runEnhancement = async () => {
    setLoading(true);
    setError("");
    setResponse(null);
    setSelectedSuggestion(null);
    try {
      const result = await enhanceResumeSection(authToken, currentRecord.resumeId, {
        resumeId: currentRecord.resumeId,
        sectionType: target.sectionType,
        sectionId: target.sectionId,
        parentSectionId: target.parentSectionId,
        currentText: target.currentText,
        enhancementMode: mode,
        instruction: mode === "custom" ? instruction : "",
        preserveLength: mode !== "concise",
        maximumWords: target.maximumWords,
        expectedRevision: currentRecord.updatedAt,
      });
      setResponse(result);
      setSelectedSuggestion(result.suggestions[0] ?? null);
    } catch (enhancementError) {
      setError(enhancementError instanceof Error ? enhancementError.message : "Could not enhance this section.");
    } finally {
      setLoading(false);
    }
  };

  const applySuggestion = async () => {
    if (!selectedSuggestion || !response) return;
    setApplying(true);
    setError("");
    try {
      const record = await applySectionEnhancement(authToken, currentRecord.resumeId, {
        resumeId: currentRecord.resumeId,
        sectionType: target.sectionType,
        sectionId: target.sectionId,
        suggestionId: selectedSuggestion.suggestionId,
        expectedRevision: response.resumeRevision || currentRecord.updatedAt,
      });
      onApplied(record);
    } catch (applyError) {
      setError(applyError instanceof Error ? applyError.message : "Could not apply this enhancement.");
    } finally {
      setApplying(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/40 p-4">
      <div className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-lg border border-slate-200 bg-white p-5 shadow-xl">
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-bold text-slate-950">Enhance with AI</h3>
            <p className="text-sm text-slate-500">AI can polish wording only. It cannot add unsupported experience.</p>
          </div>
          <button type="button" className="text-sm font-semibold text-slate-500 hover:text-slate-900" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="mb-4 grid gap-3 sm:grid-cols-[220px_1fr]">
          <label className="text-sm font-semibold text-slate-700">
            Mode
            <select
              className="mt-1 h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm"
              value={mode}
              onChange={(event) => setMode(event.target.value as EnhancementMode)}
            >
              {enhancementModes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>
          {mode === "custom" && (
            <label className="text-sm font-semibold text-slate-700">
              Custom writing instruction
              <input
                className="mt-1 h-10 w-full rounded-md border border-slate-200 px-3 text-sm"
                value={instruction}
                onChange={(event) => setInstruction(event.target.value)}
                placeholder="Example: Make this more concise and recruiter-friendly"
              />
            </label>
          )}
        </div>
        <div className="mb-4 grid gap-4 md:grid-cols-2">
          <section>
            <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">Original</h4>
            <div className="min-h-28 whitespace-pre-wrap rounded-md border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-800">
              {target.currentText}
            </div>
          </section>
          <section>
            <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">Enhanced</h4>
            <div className="min-h-28 whitespace-pre-wrap rounded-md border border-slate-200 bg-white p-3 text-sm leading-6 text-slate-900">
              {selectedSuggestion?.enhancedText ?? (loading ? "Enhancing..." : "Run enhancement to preview a safe suggestion.")}
            </div>
          </section>
        </div>
        {response && response.suggestions.length > 1 && (
          <div className="mb-4 flex flex-wrap gap-2">
            {response.suggestions.map((suggestion, index) => (
              <button
                key={suggestion.suggestionId}
                type="button"
                className={cn("rounded-md border px-3 py-1 text-sm", selectedSuggestion?.suggestionId === suggestion.suggestionId ? "border-blue-600 bg-blue-50 text-blue-700" : "border-slate-200")}
                onClick={() => setSelectedSuggestion(suggestion)}
              >
                Suggestion {index + 1}
              </button>
            ))}
          </div>
        )}
        {selectedSuggestion && (
          <p className="mb-3 text-sm text-slate-600">
            {selectedSuggestion.explanation} Evidence: {selectedSuggestion.supportingEvidenceIds.length}. Requirements: {selectedSuggestion.supportedRequirementIds.length}.
          </p>
        )}
        {error && <p className="mb-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-700">{error}</p>}
        {response?.warnings?.length ? <p className="mb-3 text-sm text-amber-700">{response.warnings[0]}</p> : null}
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={loading || applying}>Cancel</Button>
          <Button variant="outline" onClick={runEnhancement} disabled={loading || applying}>
            <Sparkles size={16} /> {response ? "Try again" : "Enhance"}
          </Button>
          <Button onClick={applySuggestion} disabled={!selectedSuggestion || loading || applying}>
            {applying ? "Applying..." : "Apply"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function bulletEnhancementId(bullet: BulletValue, parentRecordId: string, index: number): string {
  if (typeof bullet !== "string" && bullet.bulletId) return bullet.bulletId;
  return `${parentRecordId}:bullet:${index}`;
}

function bulletText(bullet: BulletValue): string {
  if (typeof bullet === "string") return bullet;
  return String(bullet.currentText || bullet.generatedText || "");
}

function updateBulletText(bullet: BulletValue, value: string): BulletValue {
  if (typeof bullet === "string") return value;
  const generatedText = String(bullet.generatedText || "");
  return {
    ...bullet,
    currentText: value,
    userEdited: generatedText ? value !== generatedText : true,
    validationStatus: "pending_validation",
    warnings: Array.from(new Set([...(bullet.warnings ?? []), "User edited this bullet; validation review is recommended."])),
  };
}

function createManualBullet(order: number): GeneratedResumeBullet {
  const currentText = "Describe a truthful, evidence-supported accomplishment.";
  return {
    bulletId: `manual-bullet-${Date.now()}-${order}`,
    order,
    generatedText: "",
    currentText,
    userEdited: true,
    supportedRequirementIds: [],
    supportingEvidenceIds: [],
    validationStatus: "pending_validation",
    warnings: ["Manual bullet has no provenance; validation required before treating it as evidence-backed."],
  };
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
