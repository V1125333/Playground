import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  FileText,
  Loader2,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  RotateCcw,
  Save,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Badge, Button, Card, Input, Progress, Select } from "../ui";
import { ResumeDocumentEditor } from "../resume/ResumeDocumentEditor";
import { useResumeAutosave } from "../../hooks/useResumeAutosave";
import { cn } from "../../lib/utils";
import type {
  CandidateProfileRecord,
  GeneratedResumeResponse,
  JobAnalysisResponse,
  ProfileEvidenceItem,
  ProfileMatchResponse,
  ProfileMatchSummary,
  RequirementMatch,
  ResumeValidationResult,
  StructuredGeneratedResume,
  StructuredResumeRecord,
} from "../../resume/types";
import {
  analyzeJob,
  exportResumeDocx,
  exportResumePdf,
  generateResume,
  getResume,
  listResumeVersions,
  listResumes,
  matchProfile,
  saveResumeVersion,
  updateResume,
} from "../../services/resumeService";
import { buildGenerateResumeRequest } from "../../services/generateResumeRequest";

const generationSettings = {
  maximumPages: 2,
  bulletsPerRecentRole: 5,
  bulletsPerOlderRole: 4,
  includeProjects: true,
  includeCertifications: true,
  includeUnmatchedKeywords: false,
  writingStyle: "balanced",
};

const analysisStages = [
  "Reading the job description",
  "Extracting requirements",
  "Validating direct evidence",
  "Normalizing and prioritizing requirements",
  "Matching against your profile",
  "Analysis complete",
];

const generationStages = [
  "Analyzing job description",
  "Matching your profile",
  "Selecting supporting evidence",
  "Writing professional summary",
  "Tailoring experience bullets",
  "Validating claims",
  "Saving resume",
  "Complete",
];

export function GenerateResumeWorkspace({
  authToken,
  profileRecord,
  profileLoadError,
  onResumeGenerated,
}: {
  authToken: string;
  profileRecord: CandidateProfileRecord | null;
  profileLoadError: string;
  onResumeGenerated: (generation: GeneratedResumeResponse, target?: { role?: string; company?: string }) => void;
}) {
  const navigate = useNavigate();
  const { resumeId } = useParams();
  const [targetRole, setTargetRole] = useState("");
  const [targetCompany, setTargetCompany] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [experienceLevel, setExperienceLevel] = useState("Senior");
  const [analysis, setAnalysis] = useState<JobAnalysisResponse | null>(null);
  const [match, setMatch] = useState<ProfileMatchResponse | null>(null);
  const [summaryIntelligence, setSummaryIntelligence] = useState<ProfileMatchResponse["summaryIntelligence"] | null>(null);
  const [currentResume, setCurrentResume] = useState<StructuredGeneratedResume | null>(null);
  const [currentRecord, setCurrentRecord] = useState<StructuredResumeRecord | null>(null);
  const [recentResumes, setRecentResumes] = useState<StructuredResumeRecord[]>([]);
  const [versions, setVersions] = useState<StructuredResumeRecord[]>([]);
  const [validation, setValidation] = useState<ResumeValidationResult | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSavingVersion, setIsSavingVersion] = useState(false);
  const [exportingFormat, setExportingFormat] = useState<"pdf" | "docx" | null>(null);
  const [mode, setMode] = useState<"preview" | "edit">("edit");
  const [insightsOpen, setInsightsOpen] = useState(true);
  const [error, setError] = useState("");
  const [activeStage, setActiveStage] = useState("");
  const generationInFlight = useRef(false);
  const analysisRequestSequence = useRef(0);
  const [loadKey, setLoadKey] = useState(0);

  const matchSummary = match?.matchSummary ?? (currentRecord?.profileMatchJson as unknown as ProfileMatchSummary | undefined);
  const resumeIntelligencePackageId = match?.packageId ?? "";
  const allRequirements = useMemo(() => collectRequirements(matchSummary), [matchSummary]);
  const evidence = useMemo(() => collectEvidence(matchSummary), [matchSummary]);
  const isHistoricalVersion = Boolean(currentRecord?.parentResumeId);
  const canEdit = mode === "edit" && Boolean(currentResume) && !isHistoricalVersion;
  const profileReady = Boolean(profileRecord?.profileId && profileRecord.profileData?.name?.trim());
  const canAnalyze = profileReady && targetRole.trim().length > 0 && jobDescription.trim().length >= 20 && !isAnalyzing && !isGenerating;
  const canGenerate = Boolean(
    canAnalyze
    && analysis
    && match
    && resumeIntelligencePackageId
    && summaryIntelligence
    && match.validationStatus !== "stale"
    && summaryIntelligence.validationStatus !== "invalid"
    && !generationInFlight.current,
  );
  const localValidationWarnings = useMemo(
    () => editedContentWarnings(currentResume, evidence),
    [currentResume, evidence],
  );
  const displayScore = currentResume
    ? currentResume.matchScore ?? currentRecord?.matchScore ?? 0
    : matchSummary?.overallMatchScore ?? 0;

  const saveCurrentResume = useCallback(
    async (resume: StructuredGeneratedResume) => {
      if (!currentRecord || isHistoricalVersion) return;
      const saved = await updateResume(authToken, currentRecord.resumeId, { resumeJson: resume, status: "draft" });
      setCurrentRecord(saved);
    },
    [authToken, currentRecord, isHistoricalVersion],
  );

  const autosave = useResumeAutosave({
    value: currentResume,
    enabled: Boolean(currentResume && currentRecord && canEdit),
    onSave: saveCurrentResume,
  });

  useEffect(() => {
    let cancelled = false;
    async function loadInitialResumes() {
      try {
        const records = await listResumes(authToken);
        if (cancelled) return;
        setRecentResumes(records);
        if (resumeId) {
          const record = await getResume(authToken, resumeId);
          if (cancelled) return;
          loadRecord(record);
        } else if (records[0]) {
          loadRecord(records[0]);
        }
      } catch (loadError) {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Could not load saved resumes.");
      }
    }
    void loadInitialResumes();
    return () => {
      cancelled = true;
    };
  }, [authToken, resumeId, loadKey]);

  useEffect(() => {
    if (!currentRecord) {
      setVersions([]);
      return;
    }
    let cancelled = false;
    void listResumeVersions(authToken, currentRecord.parentResumeId || currentRecord.resumeId)
      .then((items) => {
        if (!cancelled) setVersions(items);
      })
      .catch(() => {
        if (!cancelled) setVersions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [authToken, currentRecord?.resumeId, currentRecord?.parentResumeId]);

  const loadRecord = (record: StructuredResumeRecord) => {
    setCurrentRecord(record);
    setCurrentResume(record.resumeJson);
    setTargetRole(record.targetJobTitle);
    setTargetCompany(record.targetCompany ?? "");
    setJobDescription(record.jobDescription ?? "");
    setAnalysis(record.jobAnalysisJson as unknown as JobAnalysisResponse);
    setMatch({ matchSummary: record.profileMatchJson as unknown as ProfileMatchSummary, cacheHit: false, cacheVersion: "" });
    setSummaryIntelligence(null);
    setValidation(null);
    setError("");
    setMode(record.parentResumeId ? "preview" : "edit");
  };

  const clearAnalysisPackage = () => {
    analysisRequestSequence.current += 1;
    setAnalysis(null);
    setMatch(null);
    setSummaryIntelligence(null);
  };

  const handleAnalyze = async () => {
    if (!profileRecord?.profileId) {
      setError("Complete your profile before analyzing a job.");
      return;
    }
    setIsAnalyzing(true);
    setError("");
    setActiveStage(analysisStages[0]);
    const requestId = analysisRequestSequence.current + 1;
    analysisRequestSequence.current = requestId;
    const snapshot = {
      profileId: profileRecord.profileId,
      jobDescription: jobDescription.trim(),
      targetRole: targetRole.trim(),
      targetCompany: targetCompany.trim(),
      experienceLevel,
    };
    const isCurrentRequest = () => (
      analysisRequestSequence.current === requestId
      && profileRecord?.profileId === snapshot.profileId
      && jobDescription.trim() === snapshot.jobDescription
      && targetRole.trim() === snapshot.targetRole
      && targetCompany.trim() === snapshot.targetCompany
      && experienceLevel === snapshot.experienceLevel
    );
    try {
      const analyzed = await analyzeJob(authToken, {
        job_description: snapshot.jobDescription,
        target_role: snapshot.targetRole,
        target_company: snapshot.targetCompany,
        level: snapshot.experienceLevel,
      });
      if (!isCurrentRequest()) return;
      setActiveStage(analysisStages[3]);
      const matched = await matchProfile(authToken, {
        profileId: snapshot.profileId,
        jobAnalysis: analyzed,
        jobDescription: snapshot.jobDescription,
        targetRole: snapshot.targetRole,
        targetCompany: snapshot.targetCompany,
        level: snapshot.experienceLevel,
      });
      if (!isCurrentRequest()) return;
      setAnalysis(analyzed);
      setMatch(matched);
      setSummaryIntelligence(matched.summaryIntelligence ?? null);
      setActiveStage(analysisStages[5]);
    } catch (analyzeError) {
      if (!isCurrentRequest()) return;
      setError(analyzeError instanceof Error ? analyzeError.message : "Job analysis failed.");
      setActiveStage("Analysis failed");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleGenerate = async () => {
    if (!profileRecord?.profileId || !analysis || !match || generationInFlight.current) return;
    generationInFlight.current = true;
    setIsGenerating(true);
    setError("");
    setActiveStage(generationStages[0]);
    try {
      const stageTimer = startStageTicker(generationStages, setActiveStage);
      const generated = await generateResume(authToken, buildGenerateResumeRequest({
        profileRecord,
        jobDescription,
        targetRole,
        targetCompany,
        experienceLevel,
        jobAnalysis: analysis,
        resumeIntelligencePackageId,
        templateId: "classic-ats",
        generationSettings,
      }));
      window.clearInterval(stageTimer);
      setActiveStage(generationStages[generationStages.length - 1]);
      if (!generated.structuredResume || !generated.resumeId) {
        throw new Error("Generation completed without a structured persisted resume.");
      }
      setCurrentResume(generated.structuredResume);
      setValidation(generated.validationResult ?? null);
      const record = await getResume(authToken, generated.resumeId);
      setCurrentRecord(record);
      setRecentResumes((current) => [record, ...current.filter((item) => item.resumeId !== record.resumeId)]);
      navigate(`/generate/${record.resumeId}`, { replace: true });
      onResumeGenerated(generated, { role: targetRole.trim(), company: targetCompany.trim() });
      autosave.markSaved();
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : "Resume generation failed.");
      setActiveStage("Generation failed");
    } finally {
      generationInFlight.current = false;
      setIsGenerating(false);
    }
  };

  const handleManualSave = async () => {
    if (!currentResume) return;
    await saveCurrentResume(currentResume);
    autosave.markSaved();
  };

  const handleExport = async (format: "pdf" | "docx") => {
    if (!currentRecord) return;
    setExportingFormat(format);
    setError("");
    try {
      if (!isHistoricalVersion && currentResume && autosave.status !== "saved") {
        await handleManualSave();
      }
      const result = format === "pdf"
        ? await exportResumePdf(authToken, currentRecord.resumeId, { templateId: currentRecord.templateId, paperSize: "letter" })
        : await exportResumeDocx(authToken, currentRecord.resumeId, { templateId: currentRecord.templateId, paperSize: "letter" });
      triggerDownload(result.blob, result.filename);
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : "Export failed.");
    } finally {
      setExportingFormat(null);
    }
  };

  const handleSaveVersion = async () => {
    if (!currentRecord) return;
    setIsSavingVersion(true);
    setError("");
    try {
      await handleManualSave();
      const version = await saveResumeVersion(authToken, currentRecord.parentResumeId || currentRecord.resumeId);
      setVersions((current) => [version, ...current.filter((item) => item.resumeId !== version.resumeId)]);
    } catch (versionError) {
      setError(versionError instanceof Error ? versionError.message : "Could not save a new version.");
    } finally {
      setIsSavingVersion(false);
    }
  };

  const handleOpenVersion = async (id: string) => {
    try {
      const record = await getResume(authToken, id);
      loadRecord(record);
      navigate(`/generate/${record.resumeId}`);
    } catch (versionError) {
      setError(versionError instanceof Error ? versionError.message : "Could not open version.");
    }
  };

  const clearWorkspace = () => {
    setTargetRole("");
    setTargetCompany("");
    setJobDescription("");
    setAnalysis(null);
    setMatch(null);
    setCurrentResume(null);
    setCurrentRecord(null);
    setVersions([]);
    setValidation(null);
    setError("");
    navigate("/generate");
  };

  const profileWarning = profileRecord && profileRecord.completenessScore < 60
    ? `Your profile is ${profileRecord.completenessScore}% complete. Adding detailed work experience and skills will improve generated resume quality.`
    : "";

  return (
    <div className={cn("generate-workspace", insightsOpen ? "insights-open" : "insights-closed")}>
      <JobDescriptionPanel
        targetRole={targetRole}
        targetCompany={targetCompany}
        jobDescription={jobDescription}
        experienceLevel={experienceLevel}
        profileReady={profileReady}
        profileWarning={profileWarning || profileLoadError}
        isAnalyzing={isAnalyzing}
        isGenerating={isGenerating}
        canAnalyze={canAnalyze}
        canGenerate={canGenerate}
        error={error}
        activeStage={activeStage}
        onTargetRoleChange={(value) => {
          setTargetRole(value);
          clearAnalysisPackage();
        }}
        onTargetCompanyChange={(value) => {
          setTargetCompany(value);
          clearAnalysisPackage();
        }}
        onJobDescriptionChange={(value) => {
          setJobDescription(value);
          clearAnalysisPackage();
        }}
        onExperienceLevelChange={(value) => {
          setExperienceLevel(value);
          clearAnalysisPackage();
        }}
        onAnalyze={handleAnalyze}
        onGenerate={handleGenerate}
        onClear={clearWorkspace}
      />

      <main className="resume-main-panel">
        <WorkspaceHeader
          resume={currentResume}
          targetRole={targetRole}
          targetCompany={targetCompany}
          autosaveStatus={autosave.status}
          autosaveError={autosave.error}
          matchScore={displayScore}
          versions={versions}
          currentRecord={currentRecord}
          isHistorical={isHistoricalVersion}
          mode={mode}
          onModeChange={setMode}
          onSave={handleManualSave}
          onSaveVersion={handleSaveVersion}
          onOpenVersion={handleOpenVersion}
          onExport={handleExport}
          onToggleInsights={() => setInsightsOpen((current) => !current)}
          insightsOpen={insightsOpen}
          isSavingVersion={isSavingVersion}
          exportingFormat={exportingFormat}
        />

        <div className="resume-paper-workspace">
          {!currentResume && !isGenerating && (
            <EmptyResumeState profileReady={profileReady} />
          )}
          {isGenerating && <ProgressState stages={generationStages} activeStage={activeStage} />}
          {currentResume && (
            <ResumeDocumentEditor
              resume={currentResume}
              profile={profileRecord?.profileData ?? null}
              evidence={evidence}
              requirements={allRequirements}
              validationWarnings={[...localValidationWarnings, ...(validation?.warnings ?? []).map((item) => item.message)]}
              editable={canEdit}
              authToken={authToken}
              currentRecord={currentRecord}
              onPersistedChange={(record) => {
                setCurrentRecord(record);
                setCurrentResume(record.resumeJson);
                setRecentResumes((items) => items.map((item) => (item.resumeId === record.resumeId ? record : item)));
              }}
              onChange={setCurrentResume}
            />
          )}
        </div>
      </main>

      {insightsOpen && (
        <ResumeInsightsPanel
          matchSummary={matchSummary}
          hasResume={Boolean(currentResume)}
          resumeScore={currentResume?.matchScore ?? currentRecord?.matchScore ?? 0}
          analysis={analysis}
          validation={validation}
          summaryIntelligence={summaryIntelligence}
          localWarnings={localValidationWarnings}
          versions={versions}
          recentResumes={recentResumes}
          onOpenResume={(id) => {
            navigate(`/generate/${id}`);
            setLoadKey((key) => key + 1);
          }}
          onOpenVersion={handleOpenVersion}
        />
      )}
    </div>
  );
}

function JobDescriptionPanel(props: {
  targetRole: string;
  targetCompany: string;
  jobDescription: string;
  experienceLevel: string;
  profileReady: boolean;
  profileWarning: string;
  isAnalyzing: boolean;
  isGenerating: boolean;
  canAnalyze: boolean;
  canGenerate: boolean;
  error: string;
  activeStage: string;
  onTargetRoleChange: (value: string) => void;
  onTargetCompanyChange: (value: string) => void;
  onJobDescriptionChange: (value: string) => void;
  onExperienceLevelChange: (value: string) => void;
  onAnalyze: () => void;
  onGenerate: () => void;
  onClear: () => void;
}) {
  const disableReason = !props.profileReady
    ? "Complete your profile before generating a tailored resume."
    : !props.targetRole.trim()
      ? "Enter a target job title."
      : props.jobDescription.trim().length < 20
        ? "Paste the job description."
        : "";
  return (
    <aside className="job-panel">
      <div className="panel-title-row">
        <div>
          <h1>Generate Resume</h1>
          <p>Analyze a role, match it to your profile, then write a grounded resume.</p>
        </div>
      </div>
      {props.profileWarning && (
        <div className="status-banner amber">
          <AlertCircle size={16} /> {props.profileWarning}
        </div>
      )}
      <section className="job-panel-section">
        <h2>Job details</h2>
        <label>
          <span>Target Job Title</span>
          <Input value={props.targetRole} onChange={(event) => props.onTargetRoleChange(event.target.value)} placeholder="Software Engineer IV" />
        </label>
        <label>
          <span>Company Name</span>
          <Input value={props.targetCompany} onChange={(event) => props.onTargetCompanyChange(event.target.value)} placeholder="Company name" />
        </label>
        <label>
          <span>Experience Level</span>
          <Select value={props.experienceLevel} onChange={(event) => props.onExperienceLevelChange(event.target.value)} className="w-full">
            <option>Senior</option>
            <option>Lead</option>
            <option>Mid-level</option>
          </Select>
        </label>
      </section>
      <section className="job-panel-section flex-1">
        <div className="flex items-center justify-between">
          <h2>Job Description</h2>
          <span className="text-xs text-slate-500">{props.jobDescription.length.toLocaleString()} chars</span>
        </div>
        <textarea
          className="job-description-textarea"
          value={props.jobDescription}
          onChange={(event) => props.onJobDescriptionChange(event.target.value)}
          placeholder="Paste the full job description here..."
        />
      </section>
      {(props.isAnalyzing || props.isGenerating) && <ProgressState stages={props.isAnalyzing ? analysisStages : generationStages} activeStage={props.activeStage} compact />}
      {props.error && (
        <div className="status-banner danger">
          <AlertCircle size={16} /> {props.error}
        </div>
      )}
      {disableReason && <p className="text-xs font-medium text-slate-500">{disableReason}</p>}
      <div className="job-actions">
        <Button variant="secondary" onClick={props.onClear}>Clear</Button>
        <Button variant="outline" disabled={!props.canAnalyze} onClick={props.onAnalyze}>
          {props.isAnalyzing ? <Loader2 className="animate-spin" size={16} /> : <Sparkles size={16} />}
          Analyze & Match
        </Button>
        <Button className="bg-blue-600 hover:bg-blue-700" disabled={!props.canGenerate} onClick={props.onGenerate}>
          {props.isGenerating ? <Loader2 className="animate-spin" size={16} /> : <FileText size={16} />}
          Generate Resume
        </Button>
      </div>
      <p className="text-xs text-slate-500">Analyze the job description and compare it with your saved profile.</p>
    </aside>
  );
}

function WorkspaceHeader(props: {
  resume: StructuredGeneratedResume | null;
  targetRole: string;
  targetCompany: string;
  autosaveStatus: string;
  autosaveError: string;
  matchScore: number;
  versions: StructuredResumeRecord[];
  currentRecord: StructuredResumeRecord | null;
  isHistorical: boolean;
  mode: "preview" | "edit";
  insightsOpen: boolean;
  isSavingVersion: boolean;
  onModeChange: (mode: "preview" | "edit") => void;
  onSave: () => void;
  onSaveVersion: () => void;
  onOpenVersion: (id: string) => void;
  onExport: (format: "pdf" | "docx") => void;
  onToggleInsights: () => void;
  exportingFormat: "pdf" | "docx" | null;
}) {
  const saveText = props.autosaveStatus === "saving"
    ? "Saving..."
    : props.autosaveStatus === "error"
      ? "Save failed"
      : props.autosaveStatus === "dirty"
        ? "Unsaved changes"
        : "Saved";
  const scoreLabel = props.resume ? "Resume ATS" : "Profile match";
  return (
    <header className="generate-editor-header">
      <div className="min-w-0">
        <input
          className="resume-name-input"
          value={props.resume?.resumeName ?? "Untitled tailored resume"}
          readOnly
          aria-label="Resume name"
        />
        <p>{[props.targetCompany, props.targetRole].filter(Boolean).join(" · ") || "Paste a job description to start"}</p>
      </div>
      <div className="header-actions">
        {props.currentRecord && (
          <Badge tone={props.autosaveStatus === "error" ? "red" : props.autosaveStatus === "dirty" ? "amber" : "green"}>
            {saveText}
          </Badge>
        )}
        <Badge tone={props.matchScore >= 80 ? "green" : props.matchScore >= 60 ? "amber" : "neutral"}>{scoreLabel} {props.matchScore || 0}%</Badge>
        <div className="inline-flex overflow-hidden rounded-md border border-slate-200 bg-white">
          <button className={cn("h-9 px-3 text-sm font-semibold", props.mode === "preview" && "bg-blue-600 text-white")} onClick={() => props.onModeChange("preview")}>Preview</button>
          <button className={cn("h-9 px-3 text-sm font-semibold", props.mode === "edit" && "bg-blue-600 text-white")} disabled={props.isHistorical} onClick={() => props.onModeChange("edit")}>Edit</button>
        </div>
        <Select
          aria-label="Resume versions"
          value={props.currentRecord?.resumeId ?? ""}
          onChange={(event) => event.target.value && props.onOpenVersion(event.target.value)}
          className="max-w-[170px]"
        >
          {props.currentRecord && <option value={props.currentRecord.resumeId}>Current v{props.currentRecord.versionNumber}</option>}
          {props.versions.map((version) => (
            <option key={version.resumeId} value={version.resumeId}>Version {version.versionNumber}</option>
          ))}
        </Select>
        <Button variant="secondary" onClick={props.onSave} disabled={!props.resume || props.isHistorical}>
          <Save size={16} /> Save
        </Button>
        <Button variant="outline" onClick={props.onSaveVersion} disabled={!props.currentRecord || props.isSavingVersion || props.isHistorical}>
          <Plus size={16} /> New Version
        </Button>
        <Button
          variant="secondary"
          onClick={() => props.onExport("pdf")}
          disabled={!props.currentRecord || props.exportingFormat !== null}
        >
          {props.exportingFormat === "pdf" ? <Loader2 size={16} className="animate-spin" /> : <FileText size={16} />}
          {props.exportingFormat === "pdf" ? "Preparing PDF..." : "PDF"}
        </Button>
        <Button
          variant="secondary"
          onClick={() => props.onExport("docx")}
          disabled={!props.currentRecord || props.exportingFormat !== null}
        >
          {props.exportingFormat === "docx" ? <Loader2 size={16} className="animate-spin" /> : <FileText size={16} />}
          {props.exportingFormat === "docx" ? "Preparing Word document..." : "Word"}
        </Button>
        <Button variant="ghost" size="icon" aria-label="Toggle insights panel" onClick={props.onToggleInsights}>
          {props.insightsOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
        </Button>
      </div>
      {props.autosaveError && <p className="basis-full text-xs font-medium text-rose-700">{props.autosaveError}</p>}
      {props.isHistorical && <p className="basis-full text-xs font-medium text-amber-700">Historical version opened read-only. Save as a new version from the current draft to preserve history.</p>}
    </header>
  );
}

function ResumeInsightsPanel({
  matchSummary,
  hasResume,
  resumeScore,
  analysis,
  validation,
  summaryIntelligence,
  localWarnings,
  versions,
  recentResumes,
  onOpenResume,
  onOpenVersion,
}: {
  matchSummary?: ProfileMatchSummary;
  hasResume: boolean;
  resumeScore: number;
  analysis: JobAnalysisResponse | null;
  validation: ResumeValidationResult | null;
  summaryIntelligence?: ProfileMatchResponse["summaryIntelligence"] | null;
  localWarnings: string[];
  versions: StructuredResumeRecord[];
  recentResumes: StructuredResumeRecord[];
  onOpenResume: (id: string) => void;
  onOpenVersion: (id: string) => void;
}) {
  const matched = matchSummary?.matchedRequirements ?? [];
  const adjacent = matchSummary?.partiallyMatchedRequirements ?? [];
  const missing = matchSummary?.unmatchedRequirements ?? [];
  const displayedScore = hasResume ? resumeScore : matchSummary?.overallMatchScore ?? 0;
  const scoreTitle = hasResume ? "Resume ATS Score" : "Profile Match";
  const scoreSubtitle = hasResume ? "Generated resume ATS score" : "Profile-to-job match";
  return (
    <aside className="insights-panel">
      <section>
        <h2>{scoreTitle}</h2>
        <div className="score-card">
          <strong>{displayedScore}%</strong>
          <span>{scoreSubtitle}</span>
        </div>
        {!hasResume && (
          <p className="mt-2 text-xs leading-relaxed text-slate-500">
            This score compares the job requirements with evidence in your saved profile. It is not the ATS score of a generated resume.
          </p>
        )}
        <div className="grid grid-cols-2 gap-2 text-xs">
          <Metric label="Core" value={matchSummary?.coreRequirementScore ?? 0} />
          <Metric label="Supporting" value={matchSummary?.supportingRequirementScore ?? 0} />
        </div>
      </section>
      {analysis && (
        <section>
          <h2>Requirements</h2>
          <RequirementGroup title="Matched" items={matched} tone="green" statusText="Exact or normalized match" empty="No matched requirements yet." />
          <RequirementGroup title="Adjacent" items={adjacent} tone="amber" statusText="Transferable, not a direct match" empty="No transferable-only matches." />
          <RequirementGroup title="Missing" items={missing} tone="red" statusText="Not found in profile" empty="No missing requirements." />
        </section>
      )}
      {!hasResume && summaryIntelligence?.summary && (
        <section>
          <h2>Summary Intelligence</h2>
          <p className="text-xs leading-relaxed text-slate-600">{summaryIntelligence.summary}</p>
          {summaryIntelligence.validationStatus === "fallback" && (
            <p className="mt-2 text-xs text-amber-700">Fallback summary prepared. You can still generate the resume.</p>
          )}
        </section>
      )}
      <section>
        <h2>Validation</h2>
        {[...localWarnings, ...(validation?.warnings ?? []).map((item) => item.message), ...(validation?.errors ?? []).map((item) => item.message)].length === 0 ? (
          <p className="insight-muted"><CheckCircle2 size={14} /> No validation warnings.</p>
        ) : (
          <ul className="insight-list">
            {[...localWarnings, ...(validation?.warnings ?? []).map((item) => item.message), ...(validation?.errors ?? []).map((item) => item.message)].map((item, index) => (
              <li key={`${item}-${index}`} className="text-amber-800">{item}</li>
            ))}
          </ul>
        )}
      </section>
      <section>
        <h2>Versions</h2>
        {versions.length === 0 && <p className="insight-muted">No saved versions yet.</p>}
        {versions.map((version) => (
          <button key={version.resumeId} className="version-row" onClick={() => onOpenVersion(version.resumeId)}>
            <span>Version {version.versionNumber}</span>
            <small>{formatDateTime(version.createdAt)}</small>
          </button>
        ))}
      </section>
      <section>
        <h2>Recent</h2>
        {recentResumes.slice(0, 5).map((resume) => (
          <button key={resume.resumeId} className="version-row" onClick={() => onOpenResume(resume.resumeId)}>
            <span>{resume.targetJobTitle}</span>
            <small>{resume.targetCompany || formatDateTime(resume.updatedAt)}</small>
          </button>
        ))}
      </section>
    </aside>
  );
}

function RequirementGroup({ title, items, tone, statusText, empty }: { title: string; items: RequirementMatch[]; tone: "green" | "amber" | "red"; statusText: string; empty: string }) {
  return (
    <div className="requirement-group">
      <p>{title}</p>
      {items.length === 0 && <span className="text-xs text-slate-500">{empty}</span>}
      {items.slice(0, 7).map((item) => (
        <details key={item.requirementId} className={cn("requirement-chip", tone)}>
          <summary>
            <span>{item.requirementValue}</span>
            <small>{item.requirementPriority} · {item.classification} · {statusText}</small>
          </summary>
          <div>
            {(item.evidence.length ? item.evidence : item.adjacentEvidence).slice(0, 2).map((evidence) => (
              <p key={evidence.evidenceId}>{evidence.originalText}</p>
            ))}
            {!item.evidence.length && !item.adjacentEvidence.length && <p>No stored profile evidence supports this. It will not be claimed.</p>}
          </div>
        </details>
      ))}
    </div>
  );
}

function ProgressState({ stages, activeStage, compact = false }: { stages: string[]; activeStage: string; compact?: boolean }) {
  const activeIndex = Math.max(0, stages.indexOf(activeStage));
  return (
    <Card className={cn("progress-panel", compact && "compact")}>
      <p className="font-semibold">{activeStage || stages[0]}</p>
      <Progress value={((activeIndex + 1) / stages.length) * 100} />
      <ol>
        {stages.map((stage, index) => (
          <li key={stage} className={cn(index < activeIndex && "done", index === activeIndex && "active")}>{stage}</li>
        ))}
      </ol>
    </Card>
  );
}

function EmptyResumeState({ profileReady }: { profileReady: boolean }) {
  return (
    <div className="empty-resume-state">
      <div className="grid h-12 w-12 place-items-center rounded-md bg-blue-50 text-blue-700">
        <Sparkles size={22} />
      </div>
      <h2>{profileReady ? "Paste a job description to create your first tailored resume." : "Complete your profile before generating a tailored resume."}</h2>
      <p>{profileReady ? "Analyze the job first, then generate an evidence-grounded resume draft." : "Your profile provides the factual boundary for every generated claim."}</p>
      {!profileReady && <Link to="/profile">Go to Profile</Link>}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-2">
      <strong>{value}%</strong>
      <span className="block text-slate-500">{label}</span>
    </div>
  );
}

function collectRequirements(summary?: ProfileMatchSummary): RequirementMatch[] {
  if (!summary) return [];
  return [...summary.matchedRequirements, ...summary.partiallyMatchedRequirements, ...summary.unmatchedRequirements];
}

function collectEvidence(summary?: ProfileMatchSummary): ProfileEvidenceItem[] {
  const byId = new Map<string, ProfileEvidenceItem>();
  for (const requirement of collectRequirements(summary)) {
    for (const evidence of [...requirement.evidence, ...requirement.adjacentEvidence]) {
      byId.set(evidence.evidenceId, evidence);
    }
  }
  return [...byId.values()];
}

function editedContentWarnings(resume: StructuredGeneratedResume | null, evidence: ProfileEvidenceItem[]) {
  if (!resume) return [];
  const source = evidence.map((item) => item.originalText).join(" ").toLowerCase();
  const content = JSON.stringify(resume.sections).toLowerCase();
  const warnings: string[] = [];
  for (const term of ["azure", "aws", "trading", "python"]) {
    if (content.includes(term) && !source.includes(term)) {
      warnings.push(`The draft mentions ${term}, but no supporting ${term} evidence exists in the stored profile.`);
    }
  }
  return warnings;
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename || "Resume";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function startStageTicker(stages: string[], setActiveStage: (stage: string) => void) {
  let index = 0;
  return window.setInterval(() => {
    index = Math.min(index + 1, stages.length - 2);
    setActiveStage(stages[index]);
  }, 900);
}

function formatDateTime(value: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", { month: "short", day: "2-digit", hour: "numeric", minute: "2-digit" });
}


