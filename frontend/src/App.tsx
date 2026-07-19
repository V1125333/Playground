import {
  ArrowDown,
  ArrowUp,
  BarChart3,
  Check,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  ClipboardList,
  Download,
  Eye,
  FileText,
  History,
  Mic,
  Pencil,
  Play,
  Plus,
  UserRound,
  RefreshCw,
  Settings,
  Sparkles,
  GripVertical,
  Trash2,
  WandSparkles,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import {
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Badge, Button, Card, Input, Progress, Select } from "./components/ui";
import { GenerateResumeWorkspace } from "./components/generate/GenerateResumeWorkspace";
import { cn } from "./lib/utils";
import jobyroIcon from "./assets/jobyro-icon-teal.png";
import { ResumeDocument } from "./resume/ResumeDocument";
import type {
  CandidateProfileRecord,
  ExperienceMetric,
  GeneratedResume,
  GeneratedResumeResponse,
  JobAnalysisResponse,
  JobKeywordAnalysisItem,
  SkillCategory,
} from "./resume/types";
import { createProfile, getPrimaryProfile, updateProfile } from "./services/profileService";
import { generateResume as generateStructuredResume } from "./services/resumeService";
import {
  clean,
  datePrecedes,
  formatLocationDisplay,
  migrateLegacyLocation,
  parseProfileDate,
  profileDateInputValue,
  splitLines,
  validateStructuredLocation,
} from "./services/profileData";
import {
  SKILL_CATEGORY_REGISTRY,
  approvedSkillCategoryDefinition,
  categoryDuplicateWarnings,
  categoryLabelIssueCount,
  createApprovedSkillCategory,
  hasCategoryPrefix,
  normalizeSkillCategories,
  normalizeSkillName,
  repairCategoryLabelSkills,
  splitSkillValues,
} from "./services/skillsData";

type ResumeStatus = "Draft" | "Applied" | "Interview" | "Offer" | "Rejected";

type ResumeRow = {
  id: string;
  role: string;
  company: string;
  ats: number;
  status: ResumeStatus;
  created: string;
};

export type CandidateProfileForm = {
  firstName: string;
  lastName: string;
  title: string;
  email: string;
  phone: string;
  locationCity: string;
  locationState: string;
  locationCountry: string;
  linkedin: string;
  github: string;
  portfolio: string;
  skills: SkillCategoryForm[];
  experience: WorkExperienceForm[];
  projects: ProjectForm[];
  education: EducationForm[];
  certifications: CertificationForm[];
};

type SetProfile = React.Dispatch<React.SetStateAction<CandidateProfileForm>>;

export type WorkExperienceForm = {
  id: string;
  company: string;
  clientName: string;
  role: string;
  city: string;
  state: string;
  country: string;
  startDate: string;
  endDate: string;
  isCurrentRole: boolean;
  responsibilities: string;
  achievements: string;
  technologies: string;
  metrics: MetricForm[];
  legacyNotes: string;
  migrationReviewRequired: boolean;
};

export type MetricForm = {
  id: string;
  label: string;
  value: string;
};

export type ProjectForm = {
  id: string;
  name: string;
  org: string;
  link: string;
  bullets: string;
  technologies: string;
  linkedExperienceIds: string[];
};

export type SkillCategoryForm = {
  categoryId: string;
  categoryName: string;
  order: number;
  items: string[];
  pendingSkill: string;
  pendingCategoryName?: string;
  collapsed: boolean;
  migrationReviewRequired: boolean;
  legacyUnparsed?: string;
};

export type EducationForm = {
  id: string;
  degree: string;
  institution: string;
  location: string;
  gradYear: string;
  gpa: string;
};

export type CertificationForm = {
  id: string;
  name: string;
  issuer: string;
  issuedDate: string;
  expiryDate: string;
};

type AuthUser = {
  name: string;
  email: string;
  role: "user" | "super_admin";
};

type AiUsageEvent = {
  id: number;
  timestamp: string;
  user: string;
  feature: string;
  model: string;
  purpose: string;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  estimatedCost: number;
  latencyMs: number;
  status: string;
  resumeId: string;
  jobId: string;
  cacheHit: boolean;
  error: string;
};

type AiUsageDashboard = {
  cards: {
    todayRequests: number;
    todayCost: number;
    monthCost: number;
    totalTokens: number;
    averageCostPerResume: number;
    cacheHitRate: number;
    averageResponseTimeMs: number;
    billableRequests: number;
  };
  usageByModel: Array<{ model: string; tokens: number }>;
  costByDay: Array<{ date: string; cost: number }>;
  events: AiUsageEvent[];
};

const initialProfile: CandidateProfileForm = {
  firstName: "",
  lastName: "",
  title: "",
  email: "",
  phone: "",
  locationCity: "",
  locationState: "",
  locationCountry: "",
  linkedin: "",
  github: "",
  portfolio: "",
  skills: [],
  experience: [
    {
      id: "exp-1",
      company: "",
      clientName: "",
      role: "",
      city: "",
      state: "",
      country: "",
      startDate: "",
      endDate: "",
      isCurrentRole: false,
      responsibilities: "",
      achievements: "",
      technologies: "",
      metrics: [],
      legacyNotes: "",
      migrationReviewRequired: false,
    },
  ],
  projects: [],
  education: [
    {
      id: "edu-1",
      degree: "",
      institution: "",
      location: "",
      gradYear: "",
      gpa: "",
    },
  ],
  certifications: [
    {
      id: "cert-1",
      name: "",
      issuer: "",
      issuedDate: "",
      expiryDate: "",
    },
  ],
};

const PROFILE_STORAGE_KEY = "jobyro:candidate-profile";
const PROFILE_ID_STORAGE_KEY = "jobyro:profile-id";
const PROFILE_MIGRATED_KEY = "jobyro:profile-migrated-v1";
const AUTH_TOKEN_KEY = "jobyro:auth-token";
const SIDEBAR_COLLAPSED_KEY = "jobyro:sidebar-collapsed";

function isInvalidSessionError(error: unknown) {
  return error instanceof Error && /invalid session|token expired|invalid token|missing bearer token/i.test(error.message);
}
const RESUME_HISTORY_STORAGE_KEY = "jobyro:resume-history";
const RESUME_HISTORY_CLEARED_KEY = "jobyro:resume-history-cleared:2026-07-01";

const sampleJobDescription = `We're hiring a Senior Frontend Engineer to own our customer-facing web platform.

You'll build accessible, high-performance interfaces in React and TypeScript, contribute to our design system, and champion performance budgets and CI/CD best practices.

Requirements: 5+ years frontend experience, deep React + TypeScript, WCAG accessibility, GraphQL, and hands-on experience with Storybook and component libraries.`;

const initialResumes: ResumeRow[] = [];

const questions = [
  ["Behavioral", "Tell me about a time you improved performance on a large web app."],
  ["Technical", "How do you manage state in a complex React application?"],
  ["Technical", "How would you make a component library accessible to WCAG 2.1 AA?"],
  ["Design", "Design a front-end architecture for a real-time analytics dashboard."],
  ["Behavioral", "Describe a disagreement with a designer and how you resolved it."],
  ["Technical", "What are performance budgets and how do you enforce them in CI?"],
] as const;

const navigation: Array<{ to: string; label: string; icon: LucideIcon }> = [
  { to: "/profile", label: "Profile", icon: UserRound },
  { to: "/generate", label: "Generate Resume", icon: WandSparkles },
  { to: "/history", label: "Track Applications", icon: History },
  { to: "/templates", label: "Templates", icon: FileText },
  { to: "/settings", label: "Settings", icon: Settings },
];

function loadStoredProfile(): CandidateProfileForm {
  if (typeof window === "undefined") return initialProfile;

  try {
    const stored = window.localStorage.getItem(PROFILE_STORAGE_KEY);
    if (!stored) return initialProfile;
    const parsed = JSON.parse(stored) as Partial<CandidateProfileForm>;
    const legacyParsed = parsed as Partial<CandidateProfileForm> & { location?: string };
    const candidateLocation = migrateLegacyLocation(
      parsed.locationCity || parsed.locationCountry
        ? { city: parsed.locationCity ?? "", state: parsed.locationState ?? "", country: parsed.locationCountry ?? "" }
        : legacyParsed.location ?? "",
    );
    const migratedSkills = normalizeSkillCategoryForms((parsed as Partial<CandidateProfileForm> & { skills?: unknown }).skills);
    return {
      ...initialProfile,
      ...parsed,
      skills: migratedSkills,
      locationCity: candidateLocation.location.city,
      locationState: candidateLocation.location.state ?? "",
      locationCountry: candidateLocation.location.country,
      experience: parsed.experience?.length
        ? normalizeExperienceForms(parsed.experience as WorkExperienceForm[])
        : initialProfile.experience,
      projects: parsed.projects?.length
        ? normalizeProjectForms(parsed.projects as ProjectForm[])
        : initialProfile.projects,
      education: parsed.education?.length
        ? parsed.education.map((item) => ({ ...initialProfile.education[0], ...item }))
        : initialProfile.education,
      certifications: parsed.certifications?.length
        ? parsed.certifications.map((item) => ({ ...initialProfile.certifications[0], ...item }))
        : initialProfile.certifications,
    };
  } catch {
    return initialProfile;
  }
}

function saveStoredProfile(profile: CandidateProfileForm) {
  window.localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(profile));
}

function hasProfileContent(profile: CandidateProfileForm) {
  return Boolean(
    profile.firstName.trim()
    || profile.lastName.trim()
    || profile.email.trim()
    || profile.skills.some((category) => category.categoryName.trim() || category.items.length)
    || profile.experience.some((item) => item.company.trim() || item.role.trim()),
  );
}

function normalizeSkillCategoryForms(value: unknown): SkillCategoryForm[] {
  const migration = normalizeSkillCategories(value);
  return migration.categories.map((category, index) => ({
    categoryId: category.categoryId || `skill-category-${index + 1}`,
    categoryName: category.categoryName || category.category,
    order: Number.isInteger(category.order) ? Number(category.order) : index,
    items: category.items,
    pendingSkill: "",
    pendingCategoryName: "",
    collapsed: index !== 0,
    migrationReviewRequired: Boolean(category.migrationReviewRequired || migration.requiresReview),
    legacyUnparsed: category.legacyUnparsed ?? migration.legacyUnparsed,
  }));
}

function skillFormToProfileCategory(category: SkillCategoryForm): SkillCategory {
  return {
    category: category.categoryName.trim(),
    categoryId: category.categoryId,
    categoryName: category.categoryName.trim(),
    order: category.order,
    items: category.items.map(normalizeSkillName).filter(Boolean),
    migrationReviewRequired: category.migrationReviewRequired,
    legacyUnparsed: category.legacyUnparsed,
  };
}

function normalizeExperienceForms(experience: WorkExperienceForm[]) {
  return experience.map((item) => {
    const legacy = item as WorkExperienceForm & { client_name?: string | null; location?: string; impactMetrics?: string };
    const migratedLocation = migrateLegacyLocation(
      item.city || item.country
        ? { city: item.city, state: item.state, country: item.country }
        : legacy.location ?? "",
    );
    const legacyNotes = clean([item.legacyNotes, legacy.impactMetrics].filter(Boolean).join("\n\n"));
    return {
      ...initialProfile.experience[0],
      ...item,
      clientName: getExperienceClientName(item, legacyNotes, legacy.client_name),
      city: migratedLocation.location.city,
      state: migratedLocation.location.state ?? "",
      country: migratedLocation.location.country,
      responsibilities: item.responsibilities ?? "",
      achievements: item.achievements ?? "",
      technologies: item.technologies ?? "",
      metrics: (item.metrics ?? []).map((metric, metricIndex) => ({
        ...metric,
        id: metric.id || `metric-${metricIndex + 1}`,
      })),
      legacyNotes,
      migrationReviewRequired: Boolean(item.migrationReviewRequired || migratedLocation.requiresReview || legacyNotes),
    };
  });
}

type ProjectFormInput = Partial<Omit<ProjectForm, "bullets" | "technologies">> & {
  projectId?: string;
  bullets?: string[] | string;
  technologies?: string[] | string;
  linked_experience_ids?: string[];
};

export function normalizeProjectForms(projects: ProjectFormInput[]): ProjectForm[] {
  return projects.map((item, index) => {
    return {
      id: item.id || item.projectId || `project-${index + 1}`,
      name: item.name ?? "",
      org: item.org ?? "",
      link: item.link ?? "",
      bullets: Array.isArray(item.bullets) ? item.bullets.join("\n") : item.bullets ?? "",
      technologies: Array.isArray(item.technologies) ? item.technologies.join(", ") : item.technologies ?? "",
      linkedExperienceIds: dedupeStrings(item.linkedExperienceIds ?? item.linked_experience_ids ?? []),
    };
  });
}

function dedupeStrings(values: string[]) {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)));
}

function extractClientName(value: string) {
  const match = value.match(/^\s*client\s*:\s*(.+)$/im);
  return match?.[1] ? clean(match[1]) : "";
}

function getExperienceClientName(item: { clientName?: string | null }, legacyNotes = "", snakeCaseClientName?: string | null) {
  return clean(item.clientName ?? snakeCaseClientName ?? extractClientName(legacyNotes) ?? "");
}

function loadStoredResumes(): ResumeRow[] {
  if (typeof window === "undefined") return initialResumes;

  try {
    if (clearStoredResumeHistoryOnce()) {
      return initialResumes;
    }
    const stored = window.localStorage.getItem(RESUME_HISTORY_STORAGE_KEY);
    return stored ? (JSON.parse(stored) as ResumeRow[]) : initialResumes;
  } catch {
    return initialResumes;
  }
}

function clearStoredResumeHistoryOnce() {
  if (typeof window === "undefined") return false;
  if (window.localStorage.getItem(RESUME_HISTORY_CLEARED_KEY)) return false;
  window.localStorage.removeItem(RESUME_HISTORY_STORAGE_KEY);
  window.localStorage.setItem(RESUME_HISTORY_CLEARED_KEY, "true");
  return true;
}

function saveStoredResumes(resumes: ResumeRow[]) {
  window.localStorage.setItem(RESUME_HISTORY_STORAGE_KEY, JSON.stringify(resumes));
}

function loadSidebarCollapsed() {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
}

export default function App() {
  const navigate = useNavigate();
  const [resumes, setResumes] = useState<ResumeRow[]>(() => loadStoredResumes());
  const [profile, setProfileState] = useState<CandidateProfileForm>(() => loadStoredProfile());
  const profileRef = useRef(profile);
  const setProfile: SetProfile = useCallback((action) => {
    const next = typeof action === "function"
      ? (action as (current: CandidateProfileForm) => CandidateProfileForm)(profileRef.current)
      : action;
    profileRef.current = next;
    setProfileState(next);
  }, []);
  const [profileRecord, setProfileRecord] = useState<CandidateProfileRecord | null>(null);
  const [profileLoadError, setProfileLoadError] = useState("");
  const [authToken, setAuthToken] = useState(() => window.localStorage.getItem(AUTH_TOKEN_KEY) ?? "");
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => loadSidebarCollapsed());
  const [authUser, setAuthUser] = useState<AuthUser | null>(() => {
    try {
      const raw = window.localStorage.getItem("jobyro:auth-user");
      return raw ? (JSON.parse(raw) as AuthUser) : null;
    } catch {
      return null;
    }
  });

  const clearAuthSession = useCallback(() => {
    window.localStorage.removeItem(AUTH_TOKEN_KEY);
    window.localStorage.removeItem("jobyro:auth-user");
    setAuthToken("");
    setAuthUser(null);
    setProfileRecord(null);
    setProfileLoadError("");
  }, []);

  useEffect(() => {
    if (clearStoredResumeHistoryOnce()) {
      setResumes([]);
    }
  }, []);

  useEffect(() => {
    if (!authToken || !authUser) return;
    let cancelled = false;

    async function loadBackendProfile() {
      setProfileLoadError("");
      try {
        const primary = await getPrimaryProfile(authToken);
        if (cancelled) return;
        if (primary) {
          setProfileRecord(primary);
          setProfile(profileFormFromCandidateProfile(primary.profileData));
          saveStoredProfile(profileFormFromCandidateProfile(primary.profileData));
          window.localStorage.setItem(PROFILE_ID_STORAGE_KEY, primary.profileId);
          window.localStorage.setItem(PROFILE_MIGRATED_KEY, "true");
          return;
        }

        const legacy = loadStoredProfile();
        if (hasProfileContent(legacy) && !window.localStorage.getItem(PROFILE_MIGRATED_KEY)) {
          const created = await createProfile(authToken, buildCandidateProfile(legacy));
          if (cancelled) return;
          setProfileRecord(created);
          setProfile(profileFormFromCandidateProfile(created.profileData));
          saveStoredProfile(profileFormFromCandidateProfile(created.profileData));
          window.localStorage.setItem(PROFILE_ID_STORAGE_KEY, created.profileId);
          window.localStorage.setItem(PROFILE_MIGRATED_KEY, "true");
        }
      } catch (error) {
        if (cancelled) return;
        if (isInvalidSessionError(error)) {
          clearAuthSession();
          return;
        }
        setProfileLoadError(error instanceof Error ? error.message : "Could not load profile.");
      }
    }

    void loadBackendProfile();
    return () => {
      cancelled = true;
    };
  }, [authToken, authUser, clearAuthSession]);

  const updateStatus = (id: string, status: ResumeStatus) => {
    setResumes((current) => {
      const next = current.map((resume) => (resume.id === id ? { ...resume, status } : resume));
      saveStoredResumes(next);
      return next;
    });
  };

  const addGeneratedResume = (generation: GeneratedResumeResponse, target?: { role?: string; company?: string }) => {
    setResumes((current) => {
      const primaryExperience = generation.resume.experience[0];
      const row: ResumeRow = {
        id: `generated-${Date.now()}`,
        role: target?.role || generation.resume.title || "Generated resume",
        company: target?.company || primaryExperience?.company || "Target company",
        ats: generation.atsAnalysis?.score ?? generation.atsScore,
        status: "Draft",
        created: new Date().toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" }),
      };
      const next = [row, ...current];
      saveStoredResumes(next);
      return next;
    });
  };

  const completeLogin = (token: string, user: AuthUser) => {
    window.localStorage.setItem(AUTH_TOKEN_KEY, token);
    window.localStorage.setItem("jobyro:auth-user", JSON.stringify(user));
    setAuthToken(token);
    setAuthUser(user);
    navigate("/generate", { replace: true });
  };

  const logout = async () => {
    if (authToken) {
      await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    }
    clearAuthSession();
  };

  const toggleSidebar = () => {
    setIsSidebarCollapsed((current) => {
      const next = !current;
      window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next));
      return next;
    });
  };

  if (!authToken || !authUser) {
    return <AuthPage onLogin={completeLogin} />;
  }

  return (
    <div className="min-h-screen bg-[#f5f6f8] text-[#020817]">
      <Sidebar user={authUser} collapsed={isSidebarCollapsed} onToggle={toggleSidebar} />
      <div className={cn("min-h-screen transition-[padding] duration-200", isSidebarCollapsed ? "lg:pl-[72px]" : "lg:pl-[240px]")}>
        <Topbar user={authUser} onLogout={logout} />
        <main>
          <Routes>
            <Route path="/" element={<Navigate to="/generate" replace />} />
            <Route
              path="/profile"
              element={
                <ProfilePage
                  profile={profile}
                  setProfile={setProfile}
                  getLatestProfile={() => profileRef.current}
                  authToken={authToken}
                  profileRecord={profileRecord}
                  setProfileRecord={setProfileRecord}
                  profileLoadError={profileLoadError}
                />
              }
            />
            <Route
              path="/generate"
              element={
                <GenerateResumeWorkspace
                  profileRecord={profileRecord}
                  profileLoadError={profileLoadError}
                  authToken={authToken}
                  onResumeGenerated={addGeneratedResume}
                />
              }
            />
            <Route
              path="/generate/:resumeId"
              element={
                <GenerateResumeWorkspace
                  profileRecord={profileRecord}
                  profileLoadError={profileLoadError}
                  authToken={authToken}
                  onResumeGenerated={addGeneratedResume}
                />
              }
            />
            <Route path="/history" element={<HistoryPage resumes={resumes} updateStatus={updateStatus} />} />
            <Route path="/analytics" element={<AnalyticsPage resumes={resumes} />} />
            <Route path="/interview" element={<InterviewPage />} />
            <Route path="/templates" element={<PlaceholderPage title="Templates" description="Resume templates will be connected after the editor workflow is complete." />} />
            <Route path="/settings" element={<PlaceholderPage title="Settings" description="Workspace settings will be connected in a later step." />} />
            {authUser.role === "super_admin" && <Route path="/ai-usage" element={<AiUsagePage />} />}
            {authUser.role === "super_admin" && <Route path="/admin/temp-passwords" element={<TempPasswordPage token={authToken} />} />}
            <Route path="*" element={<Navigate to="/generate" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

function Sidebar({ user, collapsed, onToggle }: { user: AuthUser; collapsed: boolean; onToggle: () => void }) {
  const initials = userInitials(user.name);

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-30 hidden flex-col border-r border-slate-200 bg-white text-slate-950 transition-[width] duration-200 lg:flex",
        collapsed ? "w-[72px]" : "w-[240px]",
      )}
    >
      <div className={cn("flex h-16 items-center gap-3 px-5", collapsed ? "justify-center px-2" : "justify-between")}>
        <div className={cn("flex items-center gap-3", collapsed && "flex-col gap-1")}>
          <img src={jobyroIcon} alt="Jobyro" className="h-9 w-9 rounded-lg object-contain" />
          {!collapsed && <span className="text-lg font-semibold">Jobyro</span>}
        </div>
        <button
          type="button"
          onClick={onToggle}
          className={cn(
            "grid h-9 place-items-center rounded-md border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:bg-slate-50 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-blue-500",
            collapsed ? "h-7 w-9" : "w-12",
          )}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronsRight size={18} /> : <ChevronsLeft size={18} />}
        </button>
      </div>

      <nav className={cn("flex-1 space-y-1 px-3 pt-2", collapsed && "px-2")}>
        {navigation.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            title={collapsed ? item.label : undefined}
            className={({ isActive }) =>
              cn(
                "relative flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-blue-500",
                collapsed && "justify-center px-0",
                isActive && "bg-blue-50 text-blue-700",
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && <span className="absolute -left-3 h-6 w-1 rounded-r bg-blue-600" />}
                <item.icon size={18} />
                {!collapsed && item.label}
              </>
            )}
          </NavLink>
        ))}
        {user.role === "super_admin" && (
          <NavLink
            to="/ai-usage"
            title={collapsed ? "AI Usage" : undefined}
            className={({ isActive }) =>
              cn(
                "relative flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-950",
                collapsed && "justify-center px-0",
                isActive && "bg-blue-50 text-blue-700",
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && <span className="absolute -left-3 h-6 w-1 rounded-r bg-blue-600" />}
                <ClipboardList size={18} />
                {!collapsed && "AI Usage"}
              </>
            )}
          </NavLink>
        )}
        {user.role === "super_admin" && (
          <NavLink
            to="/admin/temp-passwords"
            title={collapsed ? "Temp passwords" : undefined}
            className={({ isActive }) =>
              cn(
                "relative flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-950",
                collapsed && "justify-center px-0",
                isActive && "bg-blue-50 text-blue-700",
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && <span className="absolute -left-3 h-6 w-1 rounded-r bg-blue-600" />}
                <Settings size={18} />
                {!collapsed && "Temp passwords"}
              </>
            )}
          </NavLink>
        )}
        <div className="mx-1 mt-8 border-t border-slate-200" />
      </nav>

      <div className={cn("flex items-center gap-3 border-t border-slate-200 p-4", collapsed && "justify-center px-2")}>
        <div className="grid h-9 w-9 place-items-center rounded-full bg-blue-100 text-sm font-bold text-blue-700">
          {initials}
        </div>
        {!collapsed && (
          <>
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold">{user.name}</p>
              <p className="text-sm text-slate-500">{user.role === "super_admin" ? "Super admin" : "User"}</p>
            </div>
            <button className="grid h-9 w-9 place-items-center rounded-md text-slate-500 hover:bg-slate-100" aria-label="Settings">
              <Settings size={18} />
            </button>
          </>
        )}
      </div>
    </aside>
  );
}

function Topbar({ user, onLogout }: { user: AuthUser; onLogout: () => void }) {
  const location = useLocation();
  const current = location.pathname === "/ai-usage"
    ? "AI Usage"
    : location.pathname === "/admin/temp-passwords"
      ? "Temporary passwords"
      : navigation.find((item) => location.pathname.startsWith(item.to))?.label ?? "Generate Resume";
  const initials = userInitials(user.name);

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200 bg-white px-5 lg:px-6">
      <div className="flex items-center gap-3 text-sm">
        <span className="text-slate-500">Workspace</span>
        <ChevronRight size={17} className="text-slate-400" />
        <span className="font-semibold">{current}</span>
      </div>
      <div className="flex items-center gap-4">
        <Button variant="secondary" onClick={onLogout}>Logout</Button>
        <div className="grid h-10 w-10 place-items-center rounded-full bg-[#b7dfec] font-bold text-[#07566a]">{initials}</div>
      </div>
    </header>
  );
}

function AuthPage({ onLogin }: { onLogin: (token: string, user: AuthUser) => void }) {
  const [mode, setMode] = useState<"login" | "register" | "setup" | "forgot" | "reset">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [temporaryPassword, setTemporaryPassword] = useState("");
  const [qrDataUrl, setQrDataUrl] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const clearStatus = () => {
    setError("");
    setMessage("");
  };

  const submit = async (path: string, body: Record<string, string>) => {
    setLoading(true);
    clearStatus();
    try {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail ?? "Request failed.");
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed.");
      return null;
    } finally {
      setLoading(false);
    }
  };

  const login = async () => {
    const data = await submit("/api/auth/login", { email, password, code });
    if (data?.token) onLogin(data.token, data.user);
  };

  const register = async () => {
    const data = await submit("/api/auth/register", { name, email, password });
    if (data?.qr_data_url) {
      setQrDataUrl(data.qr_data_url);
      setMode("setup");
      setMessage("Scan the QR code in Microsoft Authenticator, then enter the 6-digit code.");
    }
  };

  const setupTotp = async () => {
    const data = await submit("/api/auth/setup-totp", { email, password });
    if (data?.qr_data_url) {
      setQrDataUrl(data.qr_data_url);
      setMode("setup");
      setMessage("Scan the QR code in Microsoft Authenticator, then enter the 6-digit code.");
    }
  };

  const confirmTotp = async () => {
    const data = await submit("/api/auth/confirm-totp", { email, code });
    if (data?.status === "ok") {
      setMode("login");
      setMessage("Authenticator registered. Sign in with your password and current 6-digit code.");
      setCode("");
    }
  };

  const forgotPassword = async () => {
    const data = await submit("/api/auth/forgot-password", { email, code });
    if (data?.status) {
      setMode("reset");
      setMessage("Temporary password was sent to the super admin. Get it from the admin, then reset your password.");
    }
  };

  const resetPassword = async () => {
    const data = await submit("/api/auth/reset-password", {
      email,
      temporary_password: temporaryPassword,
      code,
      new_password: newPassword,
    });
    if (data?.status === "ok") {
      setMode("login");
      setMessage("Password reset. Sign in with your new password.");
      setPassword("");
      setTemporaryPassword("");
      setNewPassword("");
      setCode("");
    }
  };

  return (
    <div className="grid min-h-screen bg-[#f5f6f8] lg:grid-cols-[1fr_30rem]">
      <section className="flex items-center justify-center bg-[#09111f] p-8 text-white">
        <div className="max-w-xl">
          <div className="mb-8 flex items-center gap-3">
            <img src={jobyroIcon} alt="Jobyro" className="h-11 w-11 rounded-xl object-contain" />
            <h1 className="text-3xl font-bold">Jobyro</h1>
          </div>
          <h2 className="text-4xl font-bold leading-tight">Generate targeted resumes from a protected profile.</h2>
          <p className="mt-5 text-lg leading-8 text-slate-300">
            Sign in with your password and Microsoft Authenticator 6-digit code. New users register their authenticator before first login.
          </p>
        </div>
      </section>

      <section className="flex items-center justify-center p-6">
        <Card className="w-full max-w-md rounded-md p-6">
          <h2 className="text-2xl font-bold">{authTitle(mode)}</h2>
          <p className="mt-2 text-sm text-slate-500">
            Super admin seed: admin@jobyro.local / Admin@12345
          </p>

          <div className="mt-6 space-y-4">
            {mode === "register" && (
              <Field label="Name">
                <Input value={name} onChange={(event) => setName(event.target.value)} />
              </Field>
            )}
            <Field label="Email">
              <Input value={email} onChange={(event) => setEmail(event.target.value)} type="email" />
            </Field>
            {mode !== "forgot" && mode !== "reset" && (
              <Field label="Password">
                <Input value={password} onChange={(event) => setPassword(event.target.value)} type="password" />
              </Field>
            )}
            {(mode === "login" || mode === "setup" || mode === "forgot" || mode === "reset") && (
              <Field label="Authenticator code">
                <Input value={code} onChange={(event) => setCode(event.target.value)} maxLength={6} />
              </Field>
            )}
            {mode === "reset" && (
              <>
                <Field label="Temporary password">
                  <Input value={temporaryPassword} onChange={(event) => setTemporaryPassword(event.target.value)} type="password" />
                </Field>
                <Field label="New password">
                  <Input value={newPassword} onChange={(event) => setNewPassword(event.target.value)} type="password" />
                </Field>
              </>
            )}
            {mode === "setup" && qrDataUrl && (
              <div className="rounded-md border border-slate-200 bg-white p-4 text-center">
                <img className="mx-auto h-48 w-48" src={qrDataUrl} alt="Authenticator QR code" />
                <p className="mt-3 text-sm text-slate-500">Scan this in Microsoft Authenticator.</p>
              </div>
            )}
            {error && <p className="rounded-md bg-rose-50 px-3 py-2 text-sm font-medium text-rose-700">{error}</p>}
            {message && <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-700">{message}</p>}

            <Button className="w-full bg-[#0f7891] hover:bg-[#09677d]" onClick={
              mode === "login" ? login :
              mode === "register" ? register :
              mode === "setup" ? confirmTotp :
              mode === "forgot" ? forgotPassword :
              resetPassword
            } disabled={loading}>
              {loading ? "Working..." : authAction(mode)}
            </Button>
          </div>

          <div className="mt-6 flex flex-wrap gap-3 text-sm">
            <button className="font-semibold text-[#0f7891]" onClick={() => { setMode("login"); clearStatus(); }}>Login</button>
            <button className="font-semibold text-[#0f7891]" onClick={() => { setMode("register"); clearStatus(); }}>Register</button>
            <button className="font-semibold text-[#0f7891]" onClick={() => { setMode("setup"); clearStatus(); }}>Setup authenticator</button>
            <button className="font-semibold text-[#0f7891]" onClick={() => { setMode("forgot"); clearStatus(); }}>Forgot password</button>
            <button className="font-semibold text-[#0f7891]" onClick={() => { setMode("reset"); clearStatus(); }}>Reset password</button>
          </div>
        </Card>
      </section>
    </div>
  );
}

function authTitle(mode: "login" | "register" | "setup" | "forgot" | "reset") {
  return {
    login: "Login",
    register: "Register account",
    setup: "Setup authenticator",
    forgot: "Forgot password",
    reset: "Reset password",
  }[mode];
}

function authAction(mode: "login" | "register" | "setup" | "forgot" | "reset") {
  return {
    login: "Login",
    register: "Register and show QR",
    setup: "Confirm authenticator",
    forgot: "Send temp password to admin",
    reset: "Reset password",
  }[mode];
}

function userInitials(name: string) {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase() || "U";
}

function analysisInputKey(jobDescription: string, targetRole: string, targetCompany: string, level: string) {
  return [jobDescription.trim(), targetRole.trim(), targetCompany.trim(), level].join("|");
}

function removeTermFromAnalysis(analysis: JobAnalysisResponse, term: string): JobAnalysisResponse {
  const matches = (item: JobKeywordAnalysisItem) => item.term.toLowerCase() === term.toLowerCase();
  const filterItems = (items: JobKeywordAnalysisItem[]) => items.filter((item) => !matches(item));
  const technicalSkills = Object.fromEntries(
    Object.entries(analysis.technicalSkills)
      .map(([category, items]) => [category, filterItems(items)])
      .filter(([, items]) => (items as JobKeywordAnalysisItem[]).length > 0),
  );
  const explicitAtsKeywords = filterItems(analysis.explicitAtsKeywords);
  return {
    ...analysis,
    keywords: filterItems(analysis.keywords),
    explicitKeywords: filterItems(analysis.explicitKeywords),
    inferredKeywords: filterItems(analysis.inferredKeywords),
    suggestedKeywords: filterItems(analysis.suggestedKeywords),
    technicalSkills,
    leadershipCompetencies: filterItems(analysis.leadershipCompetencies),
    businessCompetencies: filterItems(analysis.businessCompetencies),
    responsibilities: filterItems(analysis.responsibilities),
    explicitAtsKeywords,
    implicitInferredSkills: filterItems(analysis.implicitInferredSkills),
    hiddenInferredSkills: filterItems(analysis.hiddenInferredSkills),
    totalExtractedKeywords: explicitAtsKeywords.length,
  };
}

function priorityLabel(score: number) {
  if (score >= 70) return "High";
  if (score >= 40) return "Medium";
  return "Low";
}

function priorityToneClass(score: number) {
  if (score >= 70) return "border-emerald-200 bg-emerald-50 text-emerald-800";
  if (score >= 40) return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-slate-200 bg-white text-slate-700";
}

function confidencePercent(confidence: JobKeywordAnalysisItem["confidence"]) {
  if (confidence === "high") return 90;
  if (confidence === "medium") return 65;
  return 35;
}

function titleCase(value: string) {
  return value
    .replace(/([A-Z])/g, " $1")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
    .trim();
}

function formatMoney(value: number) {
  return `$${value.toFixed(value > 0 && value < 0.01 ? 4 : 2)}`;
}

function GeneratePage({
  profile,
  profileRecord,
  authToken,
  onResumeGenerated,
}: {
  profile: CandidateProfileForm;
  profileRecord: CandidateProfileRecord | null;
  authToken: string;
  onResumeGenerated: (generation: GeneratedResumeResponse, target?: { role?: string; company?: string }) => void;
}) {
  const [mode, setMode] = useState<"preview" | "edit">("preview");
  const [jobDescription, setJobDescription] = useState("");
  const [targetRole, setTargetRole] = useState("");
  const [targetCompany, setTargetCompany] = useState("");
  const [experienceLevel, setExperienceLevel] = useState("Senior");
  const [jobAnalysis, setJobAnalysis] = useState<JobAnalysisResponse | null>(null);
  const [analyzedInputKey, setAnalyzedInputKey] = useState("");
  const [generation, setGeneration] = useState<GeneratedResumeResponse | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generateError, setGenerateError] = useState("");
  const [exportingFormat, setExportingFormat] = useState<"pdf" | "docx" | null>(null);
  const currentAnalysisKey = analysisInputKey(jobDescription, targetRole, targetCompany, experienceLevel);
  const hasCurrentAnalysis = Boolean(jobAnalysis && analyzedInputKey === currentAnalysisKey);

  const invalidateAnalysis = () => {
    setJobAnalysis(null);
    setAnalyzedInputKey("");
    setGeneration(null);
  };

  const handleAnalyze = async () => {
    if (jobDescription.trim().length < 20) {
      setGenerateError("Paste a job description before analyzing the role.");
      return;
    }

    setIsAnalyzing(true);
    setGenerateError("");
    try {
      const response = await fetch("/api/resumes/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_description: jobDescription.trim(),
          target_role: targetRole.trim(),
          target_company: targetCompany.trim(),
          level: experienceLevel,
        }),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Job analysis failed.");
      }
      const data = (await response.json()) as JobAnalysisResponse;
      setJobAnalysis(data);
      setAnalyzedInputKey(currentAnalysisKey);
      setGeneration(null);
    } catch (error) {
      setGenerateError(error instanceof Error ? error.message : "Job analysis failed.");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleGenerate = async () => {
    const candidateProfile = buildCandidateProfile(profile);

    if (!candidateProfile.name.trim()) {
      setGenerateError("Add the candidate name before generating a resume.");
      return;
    }

    if (jobDescription.trim().length < 20) {
      setGenerateError("Paste a job description before generating a resume.");
      return;
    }
    if (!hasCurrentAnalysis || !jobAnalysis) {
      setGenerateError("Analyze this job description before generating the resume.");
      return;
    }

    setIsGenerating(true);
    setGenerateError("");

    try {
      const data = await generateStructuredResume(authToken, {
          job_description: jobDescription.trim(),
          target_role: targetRole.trim() || "Target role",
          target_company: targetCompany.trim(),
          level: experienceLevel,
          candidate_profile: candidateProfile,
          profileId: profileRecord?.profileId,
          jobAnalysis,
          templateId: "classic-ats",
          generationSettings: {
            maximumPages: 2,
            bulletsPerRecentRole: 5,
            bulletsPerOlderRole: 3,
            includeProjects: true,
            includeCertifications: true,
            includeUnmatchedKeywords: false,
            writingStyle: "balanced",
          },
      });
      setGeneration(data);
      onResumeGenerated(data, { role: targetRole.trim(), company: targetCompany.trim() });
      setMode("preview");
    } catch (error) {
      setGenerateError(error instanceof Error ? error.message : "Resume generation failed.");
    } finally {
      setIsGenerating(false);
    }
  };

  const removeAnalysisTerm = (term: string) => {
    setJobAnalysis((current) => current ? removeTermFromAnalysis(current, term) : current);
  };

  const updateGeneratedResume = (resume: GeneratedResume) => {
    setGeneration((current) => current ? { ...current, resume } : current);
  };

  const applySuggestion = (suggestionText: string) => {
    setGeneration((current) => {
      if (!current) return current;
      return {
        ...current,
        atsAnalysis: current.atsAnalysis ? {
          ...current.atsAnalysis,
          suggestions: current.atsAnalysis.suggestions.filter((suggestion) => suggestion.text !== suggestionText),
        } : current.atsAnalysis,
        suggestions: (current.atsAnalysis?.suggestions ?? current.suggestions).filter((suggestion) => suggestion.text !== suggestionText),
      };
    });
  };

  const applyMissingKeyword = (keyword: string) => {
    setGeneration((current) => {
      if (!current) return current;
      const existingSkills = current.resume.skills.length
        ? current.resume.skills
        : [{ category: "Technical Skills", items: [] }];
      const hasKeyword = existingSkills.some((group) =>
        group.items.some((item) => item.toLowerCase() === keyword.toLowerCase()),
      );
      const skills = hasKeyword
        ? existingSkills
        : existingSkills.map((group, index) => index === 0 ? { ...group, items: [...group.items, keyword] } : group);

      const nextScore = Math.min(100, (current.atsAnalysis?.score ?? current.atsScore) + 2);
      const nextBreakdown = {
        ...(current.atsAnalysis?.breakdown ?? current.breakdown),
        keywordMatch: Math.min(100, (current.atsAnalysis?.breakdown.keywordMatch ?? current.breakdown.keywordMatch) + 5),
        matchedKeywords: Array.from(new Set([...(current.atsAnalysis?.breakdown.matchedKeywords ?? current.breakdown.matchedKeywords), keyword])),
        missingKeywords: (current.atsAnalysis?.breakdown.missingKeywords ?? current.breakdown.missingKeywords).filter((item) => item !== keyword),
      };
      return {
        ...current,
        atsAnalysis: current.atsAnalysis ? { ...current.atsAnalysis, score: nextScore, breakdown: nextBreakdown } : current.atsAnalysis,
        atsScore: nextScore,
        breakdown: {
          ...current.breakdown,
          ...nextBreakdown,
        },
        resume: {
          ...current.resume,
          skills,
        },
      };
    });
  };

  const applyAllSuggestions = () => {
    setGeneration((current) => current ? {
      ...current,
      atsAnalysis: current.atsAnalysis ? { ...current.atsAnalysis, suggestions: [] } : current.atsAnalysis,
      suggestions: [],
    } : current);
  };

  const downloadResume = async (format: "pdf" | "docx") => {
    if (!generation) return;

    setExportingFormat(format);
    setGenerateError("");
    try {
      const response = await fetch(`/api/resumes/export/${format}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resume: generation.resume }),
      });

      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? `Could not export ${format.toUpperCase()}.`);
      }

      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition") ?? "";
      const filenameMatch = disposition.match(/filename="([^"]+)"/);
      const fallbackName = `${generation.resume.name || "resume"}_${generation.resume.title || "jobyro"}.${format}`
        .replace(/\s+/g, "_")
        .replace(/[^a-zA-Z0-9_.-]/g, "_");
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filenameMatch?.[1] ?? fallbackName;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      setGenerateError(error instanceof Error ? error.message : `Could not export ${format.toUpperCase()}.`);
    } finally {
      setExportingFormat(null);
    }
  };

  return (
    <div className="grid min-h-[calc(100vh-72px)] xl:grid-cols-[440px_minmax(0,1fr)] 2xl:grid-cols-[582px_minmax(0,1fr)]">
      <section className="flex max-h-[calc(100vh-72px)] flex-col border-r border-slate-200 bg-white">
        <div className="flex items-start justify-between border-b border-slate-200 px-6 py-7 2xl:px-8">
          <div>
            <h1 className="text-xl font-bold">Job description</h1>
            <p className="text-slate-500">Paste the role you're targeting</p>
          </div>
          <button
            className="font-semibold text-[#0b718a]"
            onClick={() => {
              setJobDescription(sampleJobDescription);
              invalidateAnalysis();
            }}
          >
            Paste sample
          </button>
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-8 2xl:px-8">
          <textarea
            className="h-[280px] w-full resize-none rounded-md border border-slate-300 bg-white p-5 text-base leading-7 outline-none focus:border-[#0f7891] focus:ring-4 focus:ring-[#0f7891]/10 2xl:h-[374px] 2xl:text-lg"
            placeholder="Paste your job description here..."
            value={jobDescription}
            onChange={(event) => {
              setJobDescription(event.target.value);
              invalidateAnalysis();
            }}
          />

          <div>
            <p className="mb-4 text-sm font-bold uppercase tracking-wider text-slate-500">Resume target</p>
            <div className="grid gap-5 2xl:grid-cols-2">
              <Field label="Target role">
                <Input
                  value={targetRole}
                  onChange={(event) => {
                    setTargetRole(event.target.value);
                    invalidateAnalysis();
                  }}
                  className="h-11 rounded-none text-base"
                  placeholder="Software Engineer III"
                />
              </Field>
              <Field label="Company name">
                <Input
                  value={targetCompany}
                  onChange={(event) => {
                    setTargetCompany(event.target.value);
                    invalidateAnalysis();
                  }}
                  className="h-11 rounded-none text-base"
                  placeholder="Company you are applying to"
                />
              </Field>
              <Field label="Experience level">
                <Select
                  value={experienceLevel}
                  onChange={(event) => {
                    setExperienceLevel(event.target.value);
                    invalidateAnalysis();
                  }}
                  className="h-11 w-full rounded-none text-base"
                >
                  <option>Senior</option>
                  <option>Mid-level</option>
                  <option>Lead</option>
                </Select>
              </Field>
            </div>
          </div>
          {generateError && (
            <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">
              {generateError}
            </div>
          )}
        </div>

        <div className="shrink-0 flex flex-col gap-4 border-t border-slate-200 bg-white px-6 py-4 2xl:flex-row 2xl:items-center 2xl:justify-between 2xl:px-8">
          <span className="text-slate-500">Drafts autosave to history</span>
          <div className="flex items-center gap-5">
            <Button
              variant="secondary"
              onClick={() => {
                setJobDescription("");
                setGenerateError("");
                setGeneration(null);
                setJobAnalysis(null);
                setAnalyzedInputKey("");
              }}
            >
              Clear
            </Button>
            <Button
              variant="secondary"
              onClick={handleAnalyze}
              disabled={isAnalyzing || isGenerating}
            >
              <Sparkles size={16} />
              {isAnalyzing ? "Analyzing..." : hasCurrentAnalysis ? "Re-analyze" : "Analyze"}
            </Button>
            <Button
              className="bg-[#0f7891] px-5 hover:bg-[#09677d]"
              onClick={handleGenerate}
              disabled={isGenerating || isAnalyzing || !hasCurrentAnalysis}
            >
              <Sparkles size={16} />
              {isGenerating ? "Generating..." : "Generate resume"}
            </Button>
          </div>
        </div>
      </section>

      <section className="min-w-0 space-y-5 overflow-y-auto px-6 py-8 2xl:px-8">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <h2 className="text-2xl font-bold">Tailored resume</h2>
            <p className="text-slate-500">
              {generation ? `${generation.resume.title} - generated just now` : "Paste a job description to generate"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="inline-flex overflow-hidden rounded-md border border-slate-300 bg-white">
              <button
                className={cn("h-9 px-4 font-semibold", mode === "preview" && "bg-[#0f7891] text-white")}
                onClick={() => setMode("preview")}
              >
                Preview
              </button>
              <button
                className={cn("h-9 px-4 font-semibold", mode === "edit" && "bg-[#0f7891] text-white")}
                onClick={() => setMode("edit")}
              >
                Edit
              </button>
            </div>
            <Button variant="secondary" onClick={() => downloadResume("pdf")} disabled={!generation || exportingFormat !== null}>
              <Download size={17} />
              {exportingFormat === "pdf" ? "Exporting..." : "PDF"}
            </Button>
            <Button variant="secondary" onClick={() => downloadResume("docx")} disabled={!generation || exportingFormat !== null}>
              <Download size={17} />
              {exportingFormat === "docx" ? "Exporting..." : "Word"}
            </Button>
            <button
              className="grid h-10 w-10 place-items-center rounded-md hover:bg-slate-100 disabled:opacity-50"
              aria-label="Regenerate"
              onClick={handleGenerate}
              disabled={isGenerating || !generation}
            >
              <RefreshCw size={18} />
            </button>
          </div>
        </div>

        {jobAnalysis && (
          <JobAnalysisCard
            analysis={jobAnalysis}
            isStale={!hasCurrentAnalysis}
            onRemoveTerm={removeAnalysisTerm}
          />
        )}
        {isAnalyzing && <AnalyzingState />}
        {isGenerating && <GeneratingState />}
        {!isGenerating && generation && (
          <>
            <AtsCard generation={generation} onApplyKeyword={applyMissingKeyword} />
            <ResumeAiMetricsCard generation={generation} />
            <SuggestionsCard suggestions={generation.atsAnalysis?.suggestions ?? generation.suggestions} onApply={applySuggestion} onApplyAll={applyAllSuggestions} />
            <ResumePreview resume={generation.resume} editable={mode === "edit"} onResumeChange={updateGeneratedResume} />
          </>
        )}
        {!isGenerating && !generation && <EmptyResumeState />}
      </section>
    </div>
  );
}

function JobAnalysisCard({
  analysis,
  isStale,
  onRemoveTerm,
}: {
  analysis: JobAnalysisResponse;
  isStale: boolean;
  onRemoveTerm: (term: string) => void;
}) {
  const technicalGroups = Object.entries(analysis.technicalSkills).filter(([, items]) => items.length > 0);
  const hiddenSkills = analysis.hiddenInferredSkills.length ? analysis.hiddenInferredSkills : analysis.implicitInferredSkills;

  return (
    <Card className="rounded-md p-5">
      <div className="mb-5 flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-xl font-bold">Job analysis</h3>
            {isStale && <Badge tone="amber">Needs re-analysis</Badge>}
            {!isStale && <Badge tone="green">Ready for resume generation</Badge>}
          </div>
          <p className="mt-1 text-sm text-slate-500">
            {analysis.roleInformation.title || "Role analyzed"} · {analysis.roleInformation.seniority || "Seniority not specified"}
            {analysis.roleInformation.experience ? ` · ${analysis.roleInformation.experience}` : ""}
            {analysis.roleInformation.domain ? ` · ${analysis.roleInformation.domain}` : ""}
          </p>
        </div>
        <div className="text-sm text-slate-500">
          <span className="font-semibold text-slate-900">{analysis.totalExtractedKeywords}</span> extracted keywords
        </div>
      </div>

      {analysis.atsFocusAreas.length > 0 && (
        <div className="mb-5">
          <p className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">ATS focus areas</p>
          <div className="flex flex-wrap gap-2">
            {analysis.atsFocusAreas.map((area) => (
              <Badge key={area} tone="blue">{area}</Badge>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        {technicalGroups.map(([category, items]) => (
          <AnalysisGroup
            key={category}
            title={titleCase(category)}
            items={items}
            onRemoveTerm={onRemoveTerm}
          />
        ))}
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <AnalysisGroup title="Leadership expectations" items={analysis.leadershipCompetencies} onRemoveTerm={onRemoveTerm} />
        <AnalysisGroup title="Responsibilities" items={analysis.responsibilities} onRemoveTerm={onRemoveTerm} />
        {hiddenSkills.length > 0 && (
          <AnalysisGroup title="Hidden / inferred skills" items={hiddenSkills} onRemoveTerm={onRemoveTerm} />
        )}
        {analysis.businessCompetencies.length > 0 && (
          <AnalysisGroup title="Business competencies" items={analysis.businessCompetencies} onRemoveTerm={onRemoveTerm} />
        )}
      </div>
    </Card>
  );
}

function AnalysisGroup({
  title,
  items,
  onRemoveTerm,
}: {
  title: string;
  items: JobKeywordAnalysisItem[];
  onRemoveTerm: (term: string) => void;
}) {
  if (!items.length) return null;
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
      <p className="mb-3 text-sm font-bold">{title}</p>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <button
            key={`${title}-${item.term}`}
            className={cn(
              "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold transition hover:bg-white",
              priorityToneClass(item.priorityScore),
            )}
            title={`Priority ${item.priorityScore}/100 · Recruiter weight ${item.recruiterWeight}/10 · Confidence ${confidencePercent(item.confidence)}%`}
            onClick={() => onRemoveTerm(item.term)}
          >
            <span>{item.term}</span>
            <span className="rounded-full bg-white/80 px-1.5 py-0.5 text-[10px] uppercase">{priorityLabel(item.priorityScore)}</span>
            <span aria-hidden="true">x</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function AnalyzingState() {
  return (
    <Card className="grid min-h-[160px] place-items-center rounded-md p-8 text-center">
      <div>
        <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-md bg-cyan-50 text-[#0f7891]">
          <Sparkles size={24} />
        </div>
        <h3 className="text-lg font-bold">Analyzing job description</h3>
        <p className="mt-2 text-slate-500">Finding recruiter-level requirements, ATS keywords, and seniority signals.</p>
      </div>
    </Card>
  );
}

function TempPasswordPage({ token }: { token: string }) {
  const [items, setItems] = useState<Array<Record<string, string>>>([]);
  const [error, setError] = useState("");

  const loadItems = async () => {
    setError("");
    try {
      const response = await fetch("/api/auth/admin/temp-passwords", {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json().catch(() => []);
      if (!response.ok) throw new Error(data.detail ?? "Could not load temporary passwords.");
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load temporary passwords.");
    }
  };

  return (
    <PageFrame>
      <div className="mb-8 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Temporary passwords</h1>
          <p className="mt-3 text-lg text-slate-500">
            Password reset requests and three-attempt lockouts appear here for the super admin.
          </p>
        </div>
        <Button className="bg-[#0f7891] hover:bg-[#09677d]" onClick={loadItems}>Refresh</Button>
      </div>
      {error && <p className="mb-4 rounded-md bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">{error}</p>}
      <Card className="overflow-hidden rounded-md">
        <div className="grid grid-cols-[1fr_1fr_1fr_1fr] border-b border-slate-200 bg-slate-50 px-5 py-4 text-sm font-bold uppercase tracking-wider text-slate-500">
          <span>User</span>
          <span>Reason</span>
          <span>Temporary password</span>
          <span>Created</span>
        </div>
        {items.length === 0 && <p className="p-5 text-slate-500">No temporary passwords loaded.</p>}
        {items.map((item, index) => (
          <div key={`${item.email}-${item.created_at}-${index}`} className="grid grid-cols-[1fr_1fr_1fr_1fr] border-b border-slate-100 px-5 py-4 last:border-b-0">
            <span>{item.email}</span>
            <span>{item.reason}</span>
            <span className="font-mono font-semibold">{item.temporary_password}</span>
            <span className="text-slate-500">{item.created_at}</span>
          </div>
        ))}
      </Card>
    </PageFrame>
  );
}

function ProfilePage({
  profile,
  setProfile,
  getLatestProfile,
  authToken,
  profileRecord,
  setProfileRecord,
  profileLoadError,
}: {
  profile: CandidateProfileForm;
  setProfile: SetProfile;
  getLatestProfile: () => CandidateProfileForm;
  authToken: string;
  profileRecord: CandidateProfileRecord | null;
  setProfileRecord: React.Dispatch<React.SetStateAction<CandidateProfileRecord | null>>;
  profileLoadError: string;
}) {
  const [isEditing, setIsEditing] = useState(true);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [uploadStatus, setUploadStatus] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [profileErrors, setProfileErrors] = useState<string[]>([]);

  const saveProfile = async () => {
    const profileToSave = getLatestProfile();
    const errors = validateProfile(profileToSave);
    if (errors.length > 0) {
      setProfileErrors(errors);
      setSavedAt(null);
      setIsEditing(true);
      return;
    }

    setProfileErrors([]);
    try {
      const payload = buildCandidateProfile(profileToSave);
      const record = profileRecord
        ? await updateProfile(authToken, profileRecord.profileId, payload, profileRecord.profileVersion)
        : await createProfile(authToken, payload);
      setProfileRecord(record);
      const serverProfile = profileFormFromCandidateProfile(record.profileData);
      setProfile(serverProfile);
      saveStoredProfile(serverProfile);
      window.localStorage.setItem(PROFILE_ID_STORAGE_KEY, record.profileId);
      window.localStorage.setItem(PROFILE_MIGRATED_KEY, "true");
      setSavedAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
      setIsEditing(false);
    } catch (error) {
      setProfileErrors([error instanceof Error ? error.message : "Could not save profile."]);
      setSavedAt(null);
      setIsEditing(true);
    }
  };

  const uploadResume = async (file: File | null) => {
    if (!file) return;

    setUploadStatus("Extracting resume details...");
    setUploadError("");

    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch("/api/profile/extract", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Could not extract profile details.");
      }

      const extracted = (await response.json()) as CandidateProfileForm;
      const nextProfile = {
        ...initialProfile,
        ...extracted,
        experience: normalizeExperienceForms(extracted.experience?.length ? extracted.experience : initialProfile.experience),
        projects: normalizeProjectForms(extracted.projects?.length ? extracted.projects : initialProfile.projects),
        education: extracted.education?.length ? extracted.education : initialProfile.education,
        certifications: extracted.certifications?.length ? extracted.certifications : initialProfile.certifications,
      };
      setProfile(nextProfile);
      saveStoredProfile(nextProfile);
      setIsEditing(true);
      setSavedAt(null);
      setProfileErrors([]);
      setUploadStatus("Resume details extracted. Review and save your profile.");
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Could not extract profile details.");
      setUploadStatus("");
    }
  };

  return (
    <PageFrame>
      <div className="mb-8 flex flex-col justify-between gap-4 xl:flex-row xl:items-end">
        <div>
          <h1 className="text-3xl font-bold">Configure profile</h1>
          <p className="mt-3 max-w-3xl text-lg text-slate-500">
            Add your base details and work history. The AI will use these facts with each job description to create the resume points.
          </p>
          {savedAt && (
            <p className="mt-2 inline-flex items-center gap-2 text-sm font-medium text-emerald-700">
              <Check size={16} />
              Profile saved at {savedAt}
            </p>
          )}
          {profileLoadError && (
            <p className="mt-2 text-sm font-medium text-amber-700">{profileLoadError}</p>
          )}
        </div>
        <div className="flex flex-wrap gap-3">
          {!isEditing && (
            <Button variant="secondary" onClick={() => setIsEditing(true)}>
              Edit profile
            </Button>
          )}
          <Button className="bg-[#0f7891] hover:bg-[#09677d]" onClick={saveProfile} disabled={!isEditing}>
            <Check size={17} />
            Save profile
          </Button>
        </div>
      </div>
      <Card className="rounded-md p-6 xl:p-8">
        <div className="mb-6 rounded-md border border-slate-200 bg-slate-50 p-4">
          <div className="flex flex-col justify-between gap-4 xl:flex-row xl:items-center">
            <div>
              <h2 className="text-lg font-bold">Upload existing resume</h2>
              <p className="mt-1 text-sm text-slate-500">
                Upload a PDF, DOCX, TXT, or MD resume and the app will prefill profile details for review.
              </p>
            </div>
            <label className="inline-flex h-10 cursor-pointer items-center justify-center rounded-md border border-slate-200 bg-white px-4 text-sm font-medium shadow-sm hover:bg-slate-50">
              Upload resume
              <input
                className="sr-only"
                type="file"
                accept=".pdf,.docx,.txt,.md"
                onChange={(event) => uploadResume(event.target.files?.[0] ?? null)}
              />
            </label>
          </div>
          {uploadStatus && <p className="mt-3 text-sm font-medium text-emerald-700">{uploadStatus}</p>}
          {uploadError && <p className="mt-3 text-sm font-medium text-rose-700">{uploadError}</p>}
        </div>
        {profileErrors.length > 0 && (
          <div className="mb-5 rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
            <p className="font-semibold">Complete these fields before saving:</p>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              {profileErrors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          </div>
        )}
        {!isEditing && (
          <div className="mb-5 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">
            Profile is saved. Click Edit profile to make changes.
          </div>
        )}
        <CandidateProfilePanel profile={profile} setProfile={setProfile} variant="page" disabled={!isEditing} />
      </Card>
      <div className="fixed bottom-5 left-1/2 z-50 flex w-[calc(100vw-2rem)] max-w-[640px] -translate-x-1/2 items-center justify-between gap-3 rounded-md border border-slate-200 bg-white/95 p-3 shadow-xl backdrop-blur">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-900">{isEditing ? "Profile changes are editable" : "Profile is saved"}</p>
          <p className="hidden text-xs text-slate-500 sm:block">{isEditing ? "Save from anywhere on this page." : "Click Edit profile to make changes."}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button variant="secondary" onClick={() => setIsEditing(true)} disabled={isEditing}>
            <Pencil size={17} />
            Edit profile
          </Button>
          <Button className="bg-[#0f7891] hover:bg-[#09677d]" onClick={saveProfile} disabled={!isEditing}>
            <Check size={17} />
            Save changes
          </Button>
        </div>
      </div>
    </PageFrame>
  );
}

function CandidateProfilePanel({
  profile,
  setProfile,
  variant = "compact",
  disabled = false,
}: {
  profile: CandidateProfileForm;
  setProfile: SetProfile;
  variant?: "compact" | "page";
  disabled?: boolean;
}) {
  const [draggedExperienceId, setDraggedExperienceId] = useState<string | null>(null);

  const updateField = (field: keyof Omit<CandidateProfileForm, "experience" | "projects" | "education" | "certifications">, value: string) => {
    setProfile((current) => {
      const next = { ...current, [field]: value };
      saveStoredProfile(next);
      return next;
    });
  };

  const updateExperience = <K extends keyof Omit<WorkExperienceForm, "id">>(id: string, field: K, value: WorkExperienceForm[K]) => {
    setProfile((current) => {
      const next = {
        ...current,
        experience: current.experience.map((item) => (item.id === id ? { ...item, [field]: value } : item)),
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const addExperience = () => {
    setProfile((current) => {
      const next = {
        ...current,
        experience: [
          ...current.experience,
          {
            id: `exp-${Date.now()}`,
            company: "",
            clientName: "",
            role: "",
            city: "",
            state: "",
            country: "",
            startDate: "",
            endDate: "",
            isCurrentRole: false,
            responsibilities: "",
            achievements: "",
            technologies: "",
            metrics: [],
            legacyNotes: "",
            migrationReviewRequired: false,
          },
        ],
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const removeExperience = (id: string) => {
    setProfile((current) => {
      const next = {
        ...current,
        experience: current.experience.length === 1
          ? current.experience
          : current.experience.filter((item) => item.id !== id),
        projects: current.projects.map((project) => ({
          ...project,
          linkedExperienceIds: project.linkedExperienceIds.filter((experienceId) => experienceId !== id),
        })),
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const moveExperience = (id: string, direction: -1 | 1) => {
    setProfile((current) => {
      const index = current.experience.findIndex((item) => item.id === id);
      const targetIndex = index + direction;
      if (index < 0 || targetIndex < 0 || targetIndex >= current.experience.length) return current;
      const experience = [...current.experience];
      const [item] = experience.splice(index, 1);
      experience.splice(targetIndex, 0, item);
      const next = { ...current, experience };
      saveStoredProfile(next);
      return next;
    });
  };

  const dropExperience = (targetId: string) => {
    if (!draggedExperienceId || draggedExperienceId === targetId) {
      setDraggedExperienceId(null);
      return;
    }

    setProfile((current) => {
      const sourceIndex = current.experience.findIndex((item) => item.id === draggedExperienceId);
      const targetIndex = current.experience.findIndex((item) => item.id === targetId);
      if (sourceIndex < 0 || targetIndex < 0) return current;
      const experience = [...current.experience];
      const [item] = experience.splice(sourceIndex, 1);
      experience.splice(targetIndex, 0, item);
      const next = { ...current, experience };
      saveStoredProfile(next);
      return next;
    });
    setDraggedExperienceId(null);
  };

  const updateExperienceMetric = (experienceId: string, metricId: string, field: keyof Omit<MetricForm, "id">, value: string) => {
    setProfile((current) => {
      const next = {
        ...current,
        experience: current.experience.map((item) => item.id === experienceId
          ? {
              ...item,
              metrics: item.metrics.map((metric) => metric.id === metricId ? { ...metric, [field]: value } : metric),
            }
          : item),
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const addExperienceMetric = (experienceId: string) => {
    setProfile((current) => {
      const next = {
        ...current,
        experience: current.experience.map((item) => item.id === experienceId
          ? { ...item, metrics: [...item.metrics, { id: `metric-${Date.now()}`, label: "", value: "" }] }
          : item),
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const removeExperienceMetric = (experienceId: string, metricId: string) => {
    setProfile((current) => {
      const next = {
        ...current,
        experience: current.experience.map((item) => item.id === experienceId
          ? { ...item, metrics: item.metrics.filter((metric) => metric.id !== metricId) }
          : item),
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const updateProject = <K extends keyof Omit<ProjectForm, "id">>(id: string, field: K, value: ProjectForm[K]) => {
    setProfile((current) => {
      const next = {
        ...current,
        projects: current.projects.map((item) => (item.id === id ? { ...item, [field]: value } : item)),
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const addProject = () => {
    setProfile((current) => {
      const next = {
        ...current,
        projects: [
          ...current.projects,
          {
            id: `project-${Date.now()}`,
            name: "",
            org: "",
            link: "",
            bullets: "",
            technologies: "",
            linkedExperienceIds: [],
          },
        ],
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const removeProject = (id: string) => {
    setProfile((current) => {
      const next = {
        ...current,
        projects: current.projects.filter((item) => item.id !== id),
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const toggleProjectExperienceLink = (projectId: string, experienceId: string) => {
    setProfile((current) => {
      const next = {
        ...current,
        projects: current.projects.map((project) => {
          if (project.id !== projectId) return project;
          const exists = project.linkedExperienceIds.includes(experienceId);
          return {
            ...project,
            linkedExperienceIds: exists
              ? project.linkedExperienceIds.filter((id) => id !== experienceId)
              : [...project.linkedExperienceIds, experienceId],
          };
        }),
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const updateSkillCategory = <K extends keyof SkillCategoryForm>(categoryId: string, field: K, value: SkillCategoryForm[K]) => {
    setProfile((current) => {
      const next = {
        ...current,
        skills: current.skills.map((category) => category.categoryId === categoryId ? { ...category, [field]: value } : category),
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const addSkillCategory = (categoryId: string) => {
    const definition = approvedSkillCategoryDefinition(categoryId);
    if (!definition) return;
    setProfile((current) => {
      if (current.skills.some((item) => item.categoryId === definition.categoryId || item.categoryName.toLowerCase() === definition.categoryName.toLowerCase())) {
        return current;
      }
      const category = createApprovedSkillCategory(definition.categoryId, current.skills.length);
      const next = {
        ...current,
        skills: [
          ...current.skills,
          {
            categoryId: definition.categoryId,
            categoryName: definition.categoryName,
            order: current.skills.length,
            items: [],
            pendingSkill: "",
            pendingCategoryName: "",
            collapsed: false,
            migrationReviewRequired: false,
          },
        ],
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const removeSkillCategory = (categoryId: string) => {
    setProfile((current) => {
      const next = {
        ...current,
        skills: current.skills.filter((category) => category.categoryId !== categoryId).map((category, index) => ({ ...category, order: index })),
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const moveSkillCategory = (categoryId: string, direction: -1 | 1) => {
    setProfile((current) => {
      const index = current.skills.findIndex((category) => category.categoryId === categoryId);
      const targetIndex = index + direction;
      if (index < 0 || targetIndex < 0 || targetIndex >= current.skills.length) return current;
      const skills = [...current.skills];
      const [category] = skills.splice(index, 1);
      skills.splice(targetIndex, 0, category);
      const next = { ...current, skills: skills.map((item, itemIndex) => ({ ...item, order: itemIndex })) };
      saveStoredProfile(next);
      return next;
    });
  };

  const addSkillToCategory = (categoryId: string, rawValue?: string) => {
    setProfile((current) => {
      const next = {
        ...current,
        skills: current.skills.map((category) => {
          if (category.categoryId !== categoryId) return category;
          const values = splitSkillValues(rawValue ?? category.pendingSkill);
          const existing = new Set(category.items.map((item) => item.toLowerCase()));
          const additions = values.filter((item) => !hasCategoryPrefix(item) && !existing.has(item.toLowerCase()));
          return {
            ...category,
            items: [...category.items, ...additions],
            pendingSkill: "",
            migrationReviewRequired: category.migrationReviewRequired || values.some((item) => hasCategoryPrefix(item)),
          };
        }),
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const updateSkillInCategory = (categoryId: string, previousSkill: string, nextSkill: string) => {
    const normalizedNext = normalizeSkillName(nextSkill);
    if (!normalizedNext) return;
    setProfile((current) => {
      const next = {
        ...current,
        skills: current.skills.map((category) => {
          if (category.categoryId !== categoryId) return category;
          const existing = new Set(category.items.filter((item) => item !== previousSkill).map((item) => item.toLowerCase()));
          if (existing.has(normalizedNext.toLowerCase())) return category;
          return {
            ...category,
            items: category.items.map((item) => item === previousSkill ? normalizedNext : item),
            migrationReviewRequired: category.migrationReviewRequired || hasCategoryPrefix(normalizedNext),
          };
        }),
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const removeSkillFromCategory = (categoryId: string, skill: string) => {
    setProfile((current) => {
      const next = {
        ...current,
        skills: current.skills.map((category) => category.categoryId === categoryId
          ? { ...category, items: category.items.filter((item) => item !== skill) }
          : category),
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const fixMigratedSkillLabels = () => {
    setProfile((current) => {
      const repaired = repairCategoryLabelSkills(current.skills.map(skillFormToProfileCategory));
      const next = { ...current, skills: normalizeSkillCategoryForms(repaired) };
      saveStoredProfile(next);
      return next;
    });
  };

  const duplicateSkillWarnings = categoryDuplicateWarnings(profile.skills.map(skillFormToProfileCategory));
  const migratedSkillLabelCount = categoryLabelIssueCount(profile.skills.map(skillFormToProfileCategory));

  const updateEducation = (id: string, field: keyof Omit<EducationForm, "id">, value: string) => {
    setProfile((current) => {
      const next = {
        ...current,
        education: current.education.map((item) => (item.id === id ? { ...item, [field]: value } : item)),
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const addEducation = () => {
    setProfile((current) => {
      const next = {
        ...current,
        education: [
          ...current.education,
          { id: `edu-${Date.now()}`, degree: "", institution: "", location: "", gradYear: "", gpa: "" },
        ],
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const removeEducation = (id: string) => {
    setProfile((current) => {
      const next = {
        ...current,
        education: current.education.length === 1 ? current.education : current.education.filter((item) => item.id !== id),
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const updateCertification = (id: string, field: keyof Omit<CertificationForm, "id">, value: string) => {
    setProfile((current) => {
      const next = {
        ...current,
        certifications: current.certifications.map((item) => (item.id === id ? { ...item, [field]: value } : item)),
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const addCertification = () => {
    setProfile((current) => {
      const next = {
        ...current,
        certifications: [
          ...current.certifications,
          { id: `cert-${Date.now()}`, name: "", issuer: "", issuedDate: "", expiryDate: "" },
        ],
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const removeCertification = (id: string) => {
    setProfile((current) => {
      const next = {
        ...current,
        certifications: current.certifications.length === 1
          ? current.certifications
          : current.certifications.filter((item) => item.id !== id),
      };
      saveStoredProfile(next);
      return next;
    });
  };

  const experienceLinkOptions = profile.experience
    .filter((experience) => experience.id && (experience.company.trim() || experience.role.trim()))
    .map((experience, index) => ({
      id: experience.id,
      label: [
        experience.role.trim() || `Work experience ${index + 1}`,
        experience.company.trim(),
        experience.clientName.trim() ? `(${experience.clientName.trim()})` : "",
      ].filter(Boolean).join(" - "),
    }));

  return (
    <div>
      <div className="mb-4">
        <p className="text-sm font-bold uppercase tracking-wider text-slate-500">Candidate profile</p>
        <p className="mt-1 text-sm text-slate-500">Add facts only. Resume points will be generated.</p>
      </div>

      <fieldset disabled={disabled} className={cn(disabled && "opacity-70")}>
      <div className={cn("grid gap-4", variant === "page" ? "lg:grid-cols-2 xl:grid-cols-3" : "2xl:grid-cols-2")}>
        <Field label="First name">
          <Input value={profile.firstName} onChange={(event) => updateField("firstName", event.target.value)} className="h-11 rounded-none text-base" />
        </Field>
        <Field label="Last name">
          <Input value={profile.lastName} onChange={(event) => updateField("lastName", event.target.value)} className="h-11 rounded-none text-base" />
        </Field>
        <Field label="Current title">
          <Input value={profile.title} onChange={(event) => updateField("title", event.target.value)} className="h-11 rounded-none text-base" />
        </Field>
        <Field label="City">
          <Input value={profile.locationCity} onChange={(event) => updateField("locationCity", event.target.value)} className="h-11 rounded-none text-base" />
        </Field>
        <Field label="State / Province">
          <Input value={profile.locationState} onChange={(event) => updateField("locationState", event.target.value)} className="h-11 rounded-none text-base" />
        </Field>
        <Field label="Country">
          <Input value={profile.locationCountry} onChange={(event) => updateField("locationCountry", event.target.value)} className="h-11 rounded-none text-base" />
        </Field>
        <Field label="Email">
          <Input value={profile.email} onChange={(event) => updateField("email", event.target.value)} className="h-11 rounded-none text-base" type="email" />
        </Field>
        <Field label="Phone">
          <Input value={profile.phone} onChange={(event) => updateField("phone", event.target.value)} className="h-11 rounded-none text-base" />
        </Field>
        <Field label="LinkedIn">
          <Input value={profile.linkedin} onChange={(event) => updateField("linkedin", event.target.value)} className="h-11 rounded-none text-base" />
        </Field>
        <Field label="GitHub">
          <Input value={profile.github} onChange={(event) => updateField("github", event.target.value)} className="h-11 rounded-none text-base" />
        </Field>
        <Field label="Portfolio">
          <Input value={profile.portfolio} onChange={(event) => updateField("portfolio", event.target.value)} className="h-11 rounded-none text-base" />
        </Field>
      </div>

      <SkillsCategoryEditor
        categories={profile.skills}
        duplicateWarnings={duplicateSkillWarnings}
        migratedSkillLabelCount={migratedSkillLabelCount}
        disabled={disabled}
        onFixMigratedSkillLabels={fixMigratedSkillLabels}
        onAddCategory={addSkillCategory}
        onMoveCategory={moveSkillCategory}
        onRemoveCategory={removeSkillCategory}
        onUpdateCategory={updateSkillCategory}
        onAddSkill={addSkillToCategory}
        onUpdateSkill={updateSkillInCategory}
        onRemoveSkill={removeSkillFromCategory}
      />

      <div className="mt-5 space-y-4">
        {profile.experience.map((experience, index) => (
          <div
            key={experience.id}
            className={cn(
              "rounded-md border border-slate-200 bg-slate-50 p-4 transition",
              draggedExperienceId === experience.id && "border-[#0f7891] bg-[#e6f4f8]",
            )}
            draggable={!disabled}
            onDragStart={(event) => {
              event.dataTransfer.effectAllowed = "move";
              setDraggedExperienceId(experience.id);
            }}
            onDragOver={(event) => {
              if (!disabled) event.preventDefault();
            }}
            onDrop={() => dropExperience(experience.id)}
            onDragEnd={() => setDraggedExperienceId(null)}
          >
            <div className="mb-3 flex items-center justify-between">
              <p className="flex items-center gap-2 font-semibold">
                <GripVertical size={17} className="cursor-grab text-slate-400" />
                Work experience {index + 1}
              </p>
              <div className="flex items-center gap-2">
                <button
                  className="grid h-8 w-8 place-items-center rounded-md border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  type="button"
                  aria-label="Move work experience up"
                  title="Move up"
                  onClick={() => moveExperience(experience.id, -1)}
                  disabled={disabled || index === 0}
                >
                  <ArrowUp size={15} />
                </button>
                <button
                  className="grid h-8 w-8 place-items-center rounded-md border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  type="button"
                  aria-label="Move work experience down"
                  title="Move down"
                  onClick={() => moveExperience(experience.id, 1)}
                  disabled={disabled || index === profile.experience.length - 1}
                >
                  <ArrowDown size={15} />
                </button>
                <button
                  className="grid h-8 w-8 place-items-center rounded-md border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  type="button"
                  aria-label="Add work experience"
                  title="Add work experience"
                  onClick={addExperience}
                  disabled={disabled}
                >
                  <Plus size={16} />
                </button>
                <button
                  className="grid h-8 w-8 place-items-center rounded-md border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  type="button"
                  aria-label="Remove work experience"
                  title="Remove work experience"
                  onClick={() => removeExperience(experience.id)}
                  disabled={disabled || profile.experience.length === 1}
                >
                  <span className="text-xl leading-none">-</span>
                </button>
              </div>
            </div>
            <div className="grid gap-4 2xl:grid-cols-2">
              <Field label="Company">
                <Input value={experience.company} onChange={(event) => updateExperience(experience.id, "company", event.target.value)} className="h-11 rounded-none text-base" />
              </Field>
              <Field label="Client">
                <Input value={experience.clientName} onChange={(event) => updateExperience(experience.id, "clientName", event.target.value)} className="h-11 rounded-none text-base" placeholder="Optional client name" />
              </Field>
              <Field label="Role">
                <Input value={experience.role} onChange={(event) => updateExperience(experience.id, "role", event.target.value)} className="h-11 rounded-none text-base" />
              </Field>
              <Field label="City">
                <Input value={experience.city} onChange={(event) => updateExperience(experience.id, "city", event.target.value)} className="h-11 rounded-none text-base" />
              </Field>
              <Field label="State / Province">
                <Input value={experience.state} onChange={(event) => updateExperience(experience.id, "state", event.target.value)} className="h-11 rounded-none text-base" />
              </Field>
              <Field label="Country">
                <Input value={experience.country} onChange={(event) => updateExperience(experience.id, "country", event.target.value)} className="h-11 rounded-none text-base" />
              </Field>
              <Field label="Start date">
                <Input type="month" value={experience.startDate} onChange={(event) => updateExperience(experience.id, "startDate", event.target.value)} className="h-11 rounded-none text-base" placeholder="YYYY-MM" />
              </Field>
              <Field label="End date">
                <Input type="month" value={experience.endDate} onChange={(event) => updateExperience(experience.id, "endDate", event.target.value)} className="h-11 rounded-none text-base" placeholder="YYYY-MM" disabled={disabled || experience.isCurrentRole} />
              </Field>
            </div>
            <label className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-slate-800">
              <input
                type="checkbox"
                checked={experience.isCurrentRole}
                onChange={(event) => {
                  updateExperience(experience.id, "isCurrentRole", event.target.checked);
                  if (event.target.checked) updateExperience(experience.id, "endDate", "");
                }}
                disabled={disabled}
              />
              Current role / Present
            </label>
            <div className="mt-4 grid gap-4 xl:grid-cols-3">
              <label className="block text-sm font-semibold">
                Responsibilities
                <textarea
                  className="mt-2 h-24 w-full resize-none rounded-none border border-slate-300 bg-white px-3 py-2 text-base outline-none focus:border-[#0f7891] focus:ring-4 focus:ring-[#0f7891]/10 disabled:bg-slate-100"
                  value={experience.responsibilities}
                  onChange={(event) => updateExperience(experience.id, "responsibilities", event.target.value)}
                  disabled={disabled}
                  placeholder="One responsibility per line"
                />
              </label>
              <label className="block text-sm font-semibold">
                Achievements
                <textarea
                  className="mt-2 h-24 w-full resize-none rounded-none border border-slate-300 bg-white px-3 py-2 text-base outline-none focus:border-[#0f7891] focus:ring-4 focus:ring-[#0f7891]/10 disabled:bg-slate-100"
                  value={experience.achievements}
                  onChange={(event) => updateExperience(experience.id, "achievements", event.target.value)}
                  disabled={disabled}
                  placeholder="One factual achievement per line"
                />
              </label>
              <label className="block text-sm font-semibold">
                Technologies
                <textarea
                  className="mt-2 h-24 w-full resize-none rounded-none border border-slate-300 bg-white px-3 py-2 text-base outline-none focus:border-[#0f7891] focus:ring-4 focus:ring-[#0f7891]/10 disabled:bg-slate-100"
                  value={experience.technologies}
                  onChange={(event) => updateExperience(experience.id, "technologies", event.target.value)}
                  disabled={disabled}
                  placeholder="C#, ASP.NET Core, SQL Server"
                />
              </label>
            </div>
            <div className="mt-4 rounded-md border border-slate-200 bg-white p-3">
              <div className="mb-3 flex items-center justify-between">
                <p className="text-sm font-semibold text-slate-800">Metrics</p>
                <button
                  type="button"
                  className="inline-flex h-8 items-center gap-1 rounded-md border border-slate-200 px-3 text-sm font-medium shadow-sm hover:bg-slate-50 disabled:opacity-40"
                  onClick={() => addExperienceMetric(experience.id)}
                  disabled={disabled}
                >
                  <Plus size={14} /> Metric
                </button>
              </div>
              {experience.metrics.length === 0 && <p className="text-sm text-slate-500">No metrics added.</p>}
              <div className="space-y-2">
                {experience.metrics.map((metric) => (
                  <div key={metric.id} className="grid gap-2 xl:grid-cols-[1fr_160px_40px]">
                    <Input value={metric.label} onChange={(event) => updateExperienceMetric(experience.id, metric.id, "label", event.target.value)} placeholder="Metric label" className="h-10 rounded-none" />
                    <Input value={metric.value} onChange={(event) => updateExperienceMetric(experience.id, metric.id, "value", event.target.value)} placeholder="Value" className="h-10 rounded-none" />
                    <button
                      type="button"
                      className="grid h-10 place-items-center rounded-md border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-40"
                      onClick={() => removeExperienceMetric(experience.id, metric.id)}
                      disabled={disabled}
                      aria-label="Remove metric"
                    >
                      -
                    </button>
                  </div>
                ))}
              </div>
            </div>
            {experience.legacyNotes && (
              <label className="mt-4 block text-sm font-semibold">
                Legacy notes needing review
                <textarea
                  className="mt-2 h-20 w-full resize-none rounded-none border border-amber-300 bg-amber-50 px-3 py-2 text-base outline-none disabled:bg-amber-50"
                  value={experience.legacyNotes}
                  onChange={(event) => updateExperience(experience.id, "legacyNotes", event.target.value)}
                  disabled={disabled}
                  placeholder="Legacy free-text preserved for review."
                />
              </label>
            )}
            {experience.migrationReviewRequired && (
              <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-800">
                Review migrated legacy location or notes before relying on this experience as structured evidence.
              </p>
            )}
          </div>
        ))}
      </div>

      <div className="mt-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-bold uppercase tracking-wider text-slate-500">Projects</p>
            <p className="mt-1 text-sm text-slate-500">
              Link a project to work experience only when that project can support resume evidence for that role.
            </p>
          </div>
          <button
            className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm font-medium shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
            type="button"
            onClick={addProject}
            disabled={disabled}
          >
            <Plus size={16} /> Project
          </button>
        </div>
        {profile.projects.length === 0 && (
          <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 px-4 py-5 text-sm text-slate-500">
            No projects added. Unmapped projects can still appear in the Projects section later, but they will not support employment bullets.
          </div>
        )}
        {profile.projects.map((project, index) => (
          <div key={project.id} className="rounded-md border border-slate-200 bg-slate-50 p-4">
            <div className="mb-3 flex items-center justify-between">
              <p className="font-semibold">Project {index + 1}</p>
              <button
                className="grid h-8 w-8 place-items-center rounded-md border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                type="button"
                aria-label="Remove project"
                title="Remove project"
                onClick={() => removeProject(project.id)}
                disabled={disabled}
              >
                <span className="text-xl leading-none">-</span>
              </button>
            </div>
            <div className="grid gap-4 2xl:grid-cols-2">
              <Field label="Project name">
                <Input value={project.name} onChange={(event) => updateProject(project.id, "name", event.target.value)} className="h-11 rounded-none text-base" />
              </Field>
              <Field label="Organization">
                <Input value={project.org} onChange={(event) => updateProject(project.id, "org", event.target.value)} className="h-11 rounded-none text-base" />
              </Field>
              <Field label="Link">
                <Input value={project.link} onChange={(event) => updateProject(project.id, "link", event.target.value)} className="h-11 rounded-none text-base" />
              </Field>
              <Field label="Technologies">
                <Input value={project.technologies} onChange={(event) => updateProject(project.id, "technologies", event.target.value)} className="h-11 rounded-none text-base" placeholder="Python, Spark, Databricks" />
              </Field>
            </div>
            <label className="mt-4 block text-sm font-semibold">
              Project bullets
              <textarea
                className="mt-2 h-24 w-full resize-none rounded-none border border-slate-300 bg-white px-3 py-2 text-base outline-none focus:border-[#0f7891] focus:ring-4 focus:ring-[#0f7891]/10 disabled:bg-slate-100"
                value={project.bullets}
                onChange={(event) => updateProject(project.id, "bullets", event.target.value)}
                disabled={disabled}
                placeholder="One project fact per line"
              />
            </label>
            <div className="mt-4 rounded-md border border-slate-200 bg-white p-3">
              <p className="text-sm font-semibold text-slate-800">Related Work Experience</p>
              <p className="mt-1 text-xs text-slate-500">
                Linking allows the resume generator to use this project as supporting evidence for the selected employment.
              </p>
              {experienceLinkOptions.length === 0 ? (
                <p className="mt-3 text-sm text-slate-500">Add work experience before linking projects.</p>
              ) : (
                <div className="mt-3 grid gap-2 xl:grid-cols-2">
                  {experienceLinkOptions.map((option) => (
                    <label key={option.id} className="flex items-start gap-2 rounded-md border border-slate-200 px-3 py-2 text-sm">
                      <input
                        type="checkbox"
                        className="mt-1"
                        checked={project.linkedExperienceIds.includes(option.id)}
                        onChange={() => toggleProjectExperienceLink(project.id, option.id)}
                        disabled={disabled}
                      />
                      <span>{option.label}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 space-y-4">
        {profile.education.map((education, index) => (
          <div key={education.id} className="rounded-md border border-slate-200 bg-slate-50 p-4">
            <div className="mb-3 flex items-center justify-between">
              <p className="font-semibold">Education {index + 1}</p>
              <div className="flex items-center gap-2">
                <button
                  className="grid h-8 w-8 place-items-center rounded-md border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  type="button"
                  aria-label="Add education"
                  title="Add education"
                  onClick={addEducation}
                  disabled={disabled}
                >
                  <Plus size={16} />
                </button>
                <button
                  className="grid h-8 w-8 place-items-center rounded-md border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  type="button"
                  aria-label="Remove education"
                  title="Remove education"
                  onClick={() => removeEducation(education.id)}
                  disabled={disabled || profile.education.length === 1}
                >
                  <span className="text-xl leading-none">-</span>
                </button>
              </div>
            </div>
            <div className="grid gap-4 2xl:grid-cols-2">
              <Field label="Degree">
                <Input value={education.degree} onChange={(event) => updateEducation(education.id, "degree", event.target.value)} className="h-11 rounded-none text-base" />
              </Field>
              <Field label="Institution">
                <Input value={education.institution} onChange={(event) => updateEducation(education.id, "institution", event.target.value)} className="h-11 rounded-none text-base" />
              </Field>
              <Field label="Location">
                <Input value={education.location} onChange={(event) => updateEducation(education.id, "location", event.target.value)} className="h-11 rounded-none text-base" />
              </Field>
              <Field label="Graduation year">
                <Input value={education.gradYear} onChange={(event) => updateEducation(education.id, "gradYear", event.target.value)} className="h-11 rounded-none text-base" placeholder="YYYY" />
              </Field>
              <Field label="GPA">
                <Input value={education.gpa} onChange={(event) => updateEducation(education.id, "gpa", event.target.value)} className="h-11 rounded-none text-base" />
              </Field>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 space-y-4">
        {profile.certifications.map((certification, index) => (
          <div key={certification.id} className="rounded-md border border-slate-200 bg-slate-50 p-4">
            <div className="mb-3 flex items-center justify-between">
              <p className="font-semibold">Certification {index + 1}</p>
              <div className="flex items-center gap-2">
                <button
                  className="grid h-8 w-8 place-items-center rounded-md border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  type="button"
                  aria-label="Add certification"
                  title="Add certification"
                  onClick={addCertification}
                  disabled={disabled}
                >
                  <Plus size={16} />
                </button>
                <button
                  className="grid h-8 w-8 place-items-center rounded-md border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  type="button"
                  aria-label="Remove certification"
                  title="Remove certification"
                  onClick={() => removeCertification(certification.id)}
                  disabled={disabled || profile.certifications.length === 1}
                >
                  <span className="text-xl leading-none">-</span>
                </button>
              </div>
            </div>
            <div className="grid gap-4 2xl:grid-cols-2">
              <Field label="Certification name">
                <Input value={certification.name} onChange={(event) => updateCertification(certification.id, "name", event.target.value)} className="h-11 rounded-none text-base" />
              </Field>
              <Field label="Issuer">
                <Input value={certification.issuer} onChange={(event) => updateCertification(certification.id, "issuer", event.target.value)} className="h-11 rounded-none text-base" />
              </Field>
              <Field label="Issued date">
                <Input value={certification.issuedDate} onChange={(event) => updateCertification(certification.id, "issuedDate", event.target.value)} className="h-11 rounded-none text-base" placeholder="YYYY-MM or YYYY" />
              </Field>
              <Field label="Expiration date">
                <Input value={certification.expiryDate} onChange={(event) => updateCertification(certification.id, "expiryDate", event.target.value)} className="h-11 rounded-none text-base" placeholder="YYYY-MM, YYYY, or No expiration" />
              </Field>
            </div>
          </div>
        ))}
      </div>
      </fieldset>
    </div>
  );
}

export function SkillsCategoryEditor({
  categories,
  duplicateWarnings,
  migratedSkillLabelCount,
  disabled,
  onFixMigratedSkillLabels,
  onAddCategory,
  onMoveCategory,
  onRemoveCategory,
  onUpdateCategory,
  onAddSkill,
  onUpdateSkill,
  onRemoveSkill,
}: {
  categories: SkillCategoryForm[];
  duplicateWarnings: string[];
  migratedSkillLabelCount: number;
  disabled: boolean;
  onFixMigratedSkillLabels: () => void;
  onAddCategory: (categoryId: string) => void;
  onMoveCategory: (categoryId: string, direction: -1 | 1) => void;
  onRemoveCategory: (categoryId: string) => void;
  onUpdateCategory: <K extends keyof SkillCategoryForm>(categoryId: string, field: K, value: SkillCategoryForm[K]) => void;
  onAddSkill: (categoryId: string, rawValue?: string) => void;
  onUpdateSkill: (categoryId: string, previousSkill: string, nextSkill: string) => void;
  onRemoveSkill: (categoryId: string, skill: string) => void;
}) {
  const [isCreatingCategory, setIsCreatingCategory] = useState(false);
  const [categorySearch, setCategorySearch] = useState("");
  const [selectedCategoryId, setSelectedCategoryId] = useState("");
  const [highlightedCategoryIndex, setHighlightedCategoryIndex] = useState(0);
  const [addingSkillCategoryId, setAddingSkillCategoryId] = useState<string | null>(null);
  const [editingSkillKey, setEditingSkillKey] = useState<string | null>(null);
  const [editingSkillValue, setEditingSkillValue] = useState("");

  const existingCategoryIds = useMemo(() => new Set(categories.map((category) => category.categoryId)), [categories]);
  const availableCategories = useMemo(() => {
    const query = categorySearch.trim().toLowerCase();
    return SKILL_CATEGORY_REGISTRY
      .filter((category) => !existingCategoryIds.has(category.categoryId))
      .filter((category) => {
        if (!query) return true;
        return [
          category.categoryName,
          category.description,
          category.group,
          ...category.examples,
        ].some((value) => value.toLowerCase().includes(query));
      });
  }, [categorySearch, existingCategoryIds]);
  const selectedCategory = approvedSkillCategoryDefinition(selectedCategoryId);

  const resetCategorySelector = () => {
    setIsCreatingCategory(false);
    setCategorySearch("");
    setSelectedCategoryId("");
    setHighlightedCategoryIndex(0);
  };

  const createCategory = () => {
    if (!selectedCategory || existingCategoryIds.has(selectedCategory.categoryId)) return;
    onAddCategory(selectedCategory.categoryId);
    resetCategorySelector();
  };

  const selectCategory = (categoryId: string) => {
    setSelectedCategoryId(categoryId);
    const definition = approvedSkillCategoryDefinition(categoryId);
    setCategorySearch(definition?.categoryName ?? "");
  };

  const groupedAvailableCategories = {
    technical: availableCategories.filter((category) => category.group === "technical"),
    professional: availableCategories.filter((category) => category.group === "professional"),
  };

  const highlightedCategory = availableCategories[Math.min(highlightedCategoryIndex, Math.max(availableCategories.length - 1, 0))];

  useEffect(() => {
    setHighlightedCategoryIndex(0);
  }, [categorySearch]);

  const onCategoryComboboxKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      resetCategorySelector();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlightedCategoryIndex((index) => Math.min(index + 1, Math.max(availableCategories.length - 1, 0)));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlightedCategoryIndex((index) => Math.max(index - 1, 0));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (highlightedCategory) {
        selectCategory(highlightedCategory.categoryId);
        return;
      }
      createCategory();
    }
  };

  return (
    <div className="mt-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-bold uppercase tracking-wider text-slate-500">Skills</p>
          <p className="mt-1 text-sm text-slate-500">Manage your technical skills by category.</p>
        </div>
        <Button type="button" variant="secondary" onClick={() => {
          setIsCreatingCategory(true);
          setCategorySearch("");
          setSelectedCategoryId("");
          setHighlightedCategoryIndex(0);
        }} disabled={disabled || SKILL_CATEGORY_REGISTRY.every((category) => existingCategoryIds.has(category.categoryId))}>
          <Plus size={16} /> Add Category
        </Button>
      </div>
      {isCreatingCategory && (
        <div className="mb-3 max-w-3xl rounded-md border border-slate-200 bg-white p-4 shadow-sm">
          <div className="grid gap-3">
            <label className="text-sm font-semibold text-slate-800" htmlFor="skill-category-selector">
              Category
            </label>
            <div className="relative">
              <Input
                id="skill-category-selector"
                role="combobox"
                aria-label="Search or select a skill category"
                aria-controls="skill-category-options"
                aria-expanded={isCreatingCategory}
                aria-autocomplete="list"
                aria-activedescendant={highlightedCategory ? `skill-category-option-${highlightedCategory.categoryId}` : undefined}
                value={categorySearch}
                placeholder="Search or select a category"
                onChange={(event) => {
                  setCategorySearch(event.target.value);
                  setSelectedCategoryId("");
                }}
                onKeyDown={onCategoryComboboxKeyDown}
                className="h-10 rounded-none"
                autoFocus
              />
              <div
                id="skill-category-options"
                role="listbox"
                aria-label="Approved skill categories"
                className="mt-2 max-h-80 overflow-y-auto rounded-md border border-slate-200 bg-white shadow-sm"
              >
                {availableCategories.length === 0 && (
                  <p className="px-3 py-3 text-sm text-slate-500">No available approved categories match your search.</p>
                )}
                {(["technical", "professional"] as const).map((group) => {
                  const options = groupedAvailableCategories[group];
                  if (!options.length) return null;
                  return (
                    <div key={group}>
                      <p className="bg-slate-50 px-3 py-2 text-xs font-bold uppercase tracking-wider text-slate-500">
                        {group === "technical" ? "Technical" : "Professional"}
                      </p>
                      {options.map((category) => {
                        const globalIndex = availableCategories.findIndex((item) => item.categoryId === category.categoryId);
                        const isHighlighted = globalIndex === highlightedCategoryIndex;
                        const isSelected = selectedCategoryId === category.categoryId;
                        return (
                          <button
                            key={category.categoryId}
                            id={`skill-category-option-${category.categoryId}`}
                            role="option"
                            aria-selected={isSelected}
                            type="button"
                            className={cn(
                              "block w-full border-t border-slate-100 px-3 py-2 text-left transition",
                              isHighlighted && "bg-slate-50",
                              isSelected && "bg-[#e6f4f8]",
                            )}
                            onMouseEnter={() => setHighlightedCategoryIndex(globalIndex)}
                            onClick={() => selectCategory(category.categoryId)}
                          >
                            <span className="block text-sm font-semibold text-slate-900">{category.categoryName}</span>
                            <span className="mt-0.5 block text-xs text-slate-500">{category.description}</span>
                            <span className="mt-1 block text-xs text-slate-400">Examples: {category.examples.slice(0, 4).join(", ")}</span>
                          </button>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            </div>
            {selectedCategory && (
              <p className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-600">
                {selectedCategory.description}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <Button type="button" onClick={createCategory} disabled={!selectedCategory || existingCategoryIds.has(selectedCategory.categoryId)}>
                Create Category
              </Button>
              <Button type="button" variant="secondary" onClick={resetCategorySelector}>
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}
      {duplicateWarnings.length > 0 && (
        <div className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Duplicate skills across categories: {duplicateWarnings.join(", ")}. You can save, but choose the best category later.
        </div>
      )}
      {migratedSkillLabelCount > 0 && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <span>We found {migratedSkillLabelCount} migrated skills that still contain category labels.</span>
          <div className="flex items-center gap-2">
            <Button type="button" size="sm" onClick={onFixMigratedSkillLabels} disabled={disabled}>
              Fix Automatically
            </Button>
            <Button type="button" size="sm" variant="secondary" disabled={disabled}>
              Review Manually
            </Button>
          </div>
        </div>
      )}
      {categories.length === 0 && (
        <div className="rounded-md border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-500">
          No skill categories yet.
        </div>
      )}
      <div className="space-y-3">
        {categories.map((category, index) => {
          const duplicateItems = category.items.filter((item) => duplicateWarnings.some((warning) => warning.toLowerCase() === item.toLowerCase()));
          const isAddingSkill = addingSkillCategoryId === category.categoryId;
          return (
            <div key={category.categoryId} className="overflow-hidden rounded-md border border-slate-200 bg-white">
              <div className="group flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-3">
                <button
                  className="grid h-8 w-8 place-items-center rounded-md text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                  type="button"
                  aria-label={category.collapsed ? `Expand ${category.categoryName}` : `Collapse ${category.categoryName}`}
                  title={category.collapsed ? "Expand" : "Collapse"}
                  onClick={() => onUpdateCategory(category.categoryId, "collapsed", !category.collapsed)}
                  disabled={disabled}
                >
                  <ChevronRight size={18} className={cn("transition-transform", !category.collapsed && "rotate-90")} />
                </button>
                <label className="min-w-56 flex-1 text-sm font-semibold text-slate-800">
                  <span className="sr-only">Category name</span>
                  <span className="block px-1 py-2 text-base font-bold text-slate-800">{category.categoryName}</span>
                </label>
                <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">
                  {category.items.length}
                </span>
                <button
                  type="button"
                  className="grid h-8 w-8 place-items-center rounded-md text-slate-600 opacity-100 hover:bg-slate-50 disabled:opacity-40 sm:opacity-0 sm:group-hover:opacity-100"
                  aria-label="Move skill category up"
                  title="Move up"
                  onClick={() => onMoveCategory(category.categoryId, -1)}
                  disabled={disabled || index === 0}
                >
                  <ArrowUp size={15} />
                </button>
                <button
                  type="button"
                  className="grid h-8 w-8 place-items-center rounded-md text-slate-600 opacity-100 hover:bg-slate-50 disabled:opacity-40 sm:opacity-0 sm:group-hover:opacity-100"
                  aria-label="Move skill category down"
                  title="Move down"
                  onClick={() => onMoveCategory(category.categoryId, 1)}
                  disabled={disabled || index === categories.length - 1}
                >
                  <ArrowDown size={15} />
                </button>
                <button
                  type="button"
                  className="grid h-8 w-8 place-items-center rounded-md text-slate-600 opacity-100 hover:bg-rose-50 hover:text-rose-700 disabled:opacity-40 sm:opacity-0 sm:group-hover:opacity-100"
                  aria-label="Delete skill category"
                  title="Delete category"
                  onClick={() => onRemoveCategory(category.categoryId)}
                  disabled={disabled}
                >
                  <span className="text-xl leading-none">-</span>
                </button>
              </div>
              {!category.collapsed && (
                <div className="px-4 py-3">
                  {category.items.length === 0 && (
                    <p className="rounded-md bg-slate-50 px-3 py-3 text-sm text-slate-500">No skills added yet.</p>
                  )}
                  <div className="divide-y divide-slate-100">
                    {category.items.map((skill) => {
                      const skillKey = `${category.categoryId}:${skill}`;
                      const isEditing = editingSkillKey === skillKey;
                      const flagged = duplicateItems.includes(skill) || hasCategoryPrefix(skill);
                      return (
                        <div key={skill} className={cn("grid min-h-10 items-center gap-2 py-1.5 sm:grid-cols-[1fr_auto_auto]", flagged && "rounded-md bg-amber-50 px-2")}>
                          {isEditing ? (
                            <Input
                              aria-label={`Edit ${skill}`}
                              value={editingSkillValue}
                              className="h-9 rounded-none"
                              autoFocus
                              onChange={(event) => setEditingSkillValue(event.target.value)}
                              onKeyDown={(event) => {
                                if (event.key === "Enter") {
                                  event.preventDefault();
                                  onUpdateSkill(category.categoryId, skill, editingSkillValue);
                                  setEditingSkillKey(null);
                                }
                                if (event.key === "Escape") setEditingSkillKey(null);
                              }}
                              onBlur={() => {
                                onUpdateSkill(category.categoryId, skill, editingSkillValue);
                                setEditingSkillKey(null);
                              }}
                            />
                          ) : (
                            <span className={cn("text-sm text-slate-800", flagged && "text-amber-900")}>{skill}</span>
                          )}
                          <button
                            type="button"
                            className="grid h-8 w-8 place-items-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-900"
                            aria-label={`Edit ${skill}`}
                            title={`Edit ${skill}`}
                            onClick={() => {
                              setEditingSkillKey(skillKey);
                              setEditingSkillValue(skill);
                            }}
                            disabled={disabled}
                          >
                            <Pencil size={15} />
                          </button>
                          <button
                            type="button"
                            className="grid h-8 w-8 place-items-center rounded-md text-slate-400 hover:bg-rose-50 hover:text-rose-700"
                            aria-label={`Delete ${skill}`}
                            title={`Delete ${skill}`}
                            onClick={() => onRemoveSkill(category.categoryId, skill)}
                            disabled={disabled}
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                  {isAddingSkill ? (
                    <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_auto_auto]">
                      <Input
                        aria-label={`Add skill to ${category.categoryName || "category"}`}
                        value={category.pendingSkill}
                        placeholder="Add a skill..."
                        className="h-10 rounded-none"
                        onChange={(event) => onUpdateCategory(category.categoryId, "pendingSkill", event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") {
                            event.preventDefault();
                            onAddSkill(category.categoryId);
                            setAddingSkillCategoryId(null);
                          }
                          if (event.key === "Escape") setAddingSkillCategoryId(null);
                        }}
                        disabled={disabled}
                        autoFocus
                      />
                      <Button type="button" onClick={() => {
                        onAddSkill(category.categoryId);
                        setAddingSkillCategoryId(null);
                      }} disabled={disabled || !category.pendingSkill.trim()}>
                        Add
                      </Button>
                      <Button type="button" variant="secondary" onClick={() => setAddingSkillCategoryId(null)} disabled={disabled}>
                        Cancel
                      </Button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="mt-3 inline-flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-[#0f7891] hover:bg-[#e6f4f8]"
                      onClick={() => setAddingSkillCategoryId(category.categoryId)}
                      disabled={disabled}
                    >
                      <Plus size={15} /> Add Skill
                    </button>
                  )}
                  {category.migrationReviewRequired && (
                    <p className="mt-2 text-sm text-amber-700">Review migrated skills before relying on this category.</p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function buildCandidateProfile(profile: CandidateProfileForm): GeneratedResume {
  const name = [profile.firstName, profile.lastName].map((part) => part.trim()).filter(Boolean).join(" ");
  const candidateLocation = {
    city: profile.locationCity.trim(),
    state: profile.locationState.trim() || null,
    country: profile.locationCountry.trim(),
  };
  const skillCategories = profile.skills
    .map(skillFormToProfileCategory)
    .filter((category) => category.category.trim())
    .map((category, index) => ({ ...category, order: index }));

  return {
    name,
    firstName: profile.firstName.trim(),
    lastName: profile.lastName.trim(),
    title: profile.title.trim(),
    contact: {
      phone: profile.phone.trim(),
      email: profile.email.trim(),
      location: formatLocationDisplay(candidateLocation),
      locationData: candidateLocation,
      linkedin: profile.linkedin.trim(),
      github: profile.github.trim(),
      portfolio: profile.portfolio.trim(),
    },
    summary: "",
    skills: skillCategories,
    experience: profile.experience
      .filter((item) => item.company.trim() || item.role.trim())
      .map((item) => ({
        experienceId: item.id,
        company: item.company.trim(),
        clientName: item.clientName.trim() || null,
        role: item.role.trim(),
        location: formatLocationDisplay({ city: item.city.trim(), state: item.state.trim() || null, country: item.country.trim() }),
        locationData: { city: item.city.trim(), state: item.state.trim() || null, country: item.country.trim() },
        startDate: item.startDate.trim(),
        startDateData: parseProfileDate(item.startDate) ?? undefined,
        endDate: item.isCurrentRole ? "Present" : item.endDate.trim(),
        endDateData: item.isCurrentRole ? null : parseProfileDate(item.endDate),
        isCurrentRole: item.isCurrentRole,
        rawNotes: item.legacyNotes.trim(),
        bullets: [],
        responsibilities: splitLines(item.responsibilities),
        achievements: splitLines(item.achievements),
        technologies: splitLines(item.technologies).flatMap((value) => value.split(",").map((item) => item.trim())).filter(Boolean),
        metrics: normalizeMetricForms(item.metrics),
        metricFlags: normalizeMetricForms(item.metrics).map((metric) => `${metric.label}: ${metric.value}`),
        legacyNotes: item.legacyNotes.trim(),
        migrationReviewRequired: item.migrationReviewRequired,
      })),
    projects: profile.projects
      .filter((item) => item.name.trim() || item.org.trim() || item.bullets.trim() || item.technologies.trim())
      .map((item) => ({
        projectId: item.id,
        name: item.name.trim(),
        org: item.org.trim(),
        link: item.link.trim(),
        bullets: splitLines(item.bullets),
        technologies: splitLines(item.technologies).flatMap((value) => value.split(",").map((item) => item.trim())).filter(Boolean),
        linkedExperienceIds: dedupeStrings(item.linkedExperienceIds),
      })),
    education: profile.education
      .filter((item) => item.degree.trim() || item.institution.trim())
      .map((item) => ({
        educationId: item.id,
        degree: item.degree.trim(),
        institution: item.institution.trim(),
        location: item.location.trim(),
        gradYear: item.gradYear.trim(),
        gpa: item.gpa.trim(),
      })),
    certifications: profile.certifications
      .filter((item) => item.name.trim() || item.issuer.trim())
      .map((item) => ({
        certificationId: item.id,
        name: item.name.trim(),
        issuer: item.issuer.trim(),
        issuedDate: item.issuedDate.trim(),
        expiryDate: item.expiryDate.trim(),
      })),
  };

}

export function profileFormFromCandidateProfile(profile: GeneratedResume): CandidateProfileForm {
  const [fallbackFirstName = "", ...fallbackLastParts] = profile.name.trim().split(/\s+/).filter(Boolean);
  const candidateLocation = migrateLegacyLocation(profile.contact.locationData ?? profile.contact.location ?? "");
  return {
    ...initialProfile,
    firstName: (profile.firstName ?? "").trim() || fallbackFirstName,
    lastName: (profile.lastName ?? "").trim() || fallbackLastParts.join(" "),
    title: profile.title ?? "",
    email: profile.contact.email ?? "",
    phone: profile.contact.phone ?? "",
    locationCity: candidateLocation.location.city,
    locationState: candidateLocation.location.state ?? "",
    locationCountry: candidateLocation.location.country,
    linkedin: profile.contact.linkedin ?? "",
    github: profile.contact.github ?? "",
    portfolio: profile.contact.portfolio ?? "",
    skills: normalizeSkillCategoryForms(profile.skills),
    experience: profile.experience.length
      ? profile.experience.map((item, index) => ({
          id: item.experienceId ?? `exp-${index + 1}`,
          company: item.company,
          clientName: getExperienceClientName(item as typeof item & { client_name?: string | null }, item.legacyNotes ?? item.rawNotes ?? "", (item as typeof item & { client_name?: string | null }).client_name),
          role: item.role,
          city: migrateLegacyLocation(item.locationData ?? item.location ?? "").location.city,
          state: migrateLegacyLocation(item.locationData ?? item.location ?? "").location.state ?? "",
          country: migrateLegacyLocation(item.locationData ?? item.location ?? "").location.country,
          startDate: profileDateInputValue(item.startDateData ?? parseProfileDate(item.startDate ?? "")),
          endDate: item.isCurrentRole || item.endDate === "Present" ? "" : profileDateInputValue(item.endDateData ?? parseProfileDate(item.endDate ?? "")),
          isCurrentRole: Boolean(item.isCurrentRole ?? item.endDate === "Present"),
          responsibilities: (item.responsibilities ?? []).join("\n"),
          achievements: (item.achievements ?? []).join("\n"),
          technologies: (item.technologies ?? []).join(", "),
          metrics: (item.metrics ?? []).map((metric) => ({ id: metric.metricId, label: metric.label, value: metric.value })),
          legacyNotes: item.legacyNotes ?? item.rawNotes ?? "",
          migrationReviewRequired: Boolean(item.migrationReviewRequired),
        }))
      : initialProfile.experience,
    projects: profile.projects.length
      ? normalizeProjectForms(profile.projects.map((item, index) => ({
          id: item.projectId ?? `project-${index + 1}`,
          name: item.name,
          org: item.org ?? "",
          link: item.link ?? "",
          bullets: item.bullets,
          technologies: item.technologies,
          linkedExperienceIds: item.linkedExperienceIds ?? [],
        })))
      : initialProfile.projects,
    education: profile.education.length
      ? profile.education.map((item, index) => ({
          id: item.educationId ?? `edu-${index + 1}`,
          degree: item.degree,
          institution: item.institution,
          location: item.location ?? "",
          gradYear: item.gradYear ?? "",
          gpa: item.gpa ?? "",
        }))
      : initialProfile.education,
    certifications: profile.certifications.length
      ? profile.certifications.map((item, index) => ({
          id: item.certificationId ?? `cert-${index + 1}`,
          name: item.name,
          issuer: item.issuer ?? "",
          issuedDate: item.issuedDate ?? "",
          expiryDate: item.expiryDate ?? "",
        }))
      : initialProfile.certifications,
  };
}

function normalizeMetricForms(metrics: MetricForm[]): ExperienceMetric[] {
  return metrics
    .map((metric, index) => ({
      metricId: metric.id || `metric-${index + 1}`,
      label: metric.label.trim(),
      value: metric.value.trim(),
    }))
    .filter((metric) => metric.label || metric.value);
}

export function validateProfile(profile: CandidateProfileForm) {
  const errors: string[] = [];
  const firstExperience = profile.experience.find((item) =>
    item.company.trim() || item.role.trim() || item.startDate.trim() || item.endDate.trim(),
  );

  if (!profile.firstName.trim()) errors.push("First name is required.");
  if (!profile.lastName.trim()) errors.push("Last name is required.");
  if (!profile.title.trim()) errors.push("Current title is required.");
  if (!profile.email.trim()) {
    errors.push("Email is required.");
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(profile.email.trim())) {
    errors.push("Enter a valid email address.");
  }
  if (!profile.phone.trim()) errors.push("Phone is required.");
  errors.push(...validateStructuredLocation({
    city: profile.locationCity,
    state: profile.locationState || null,
    country: profile.locationCountry,
  }, "Candidate location"));
  const savedSkillCategories = profile.skills
    .map(skillFormToProfileCategory)
    .filter((category) => category.category.trim() && category.items.length > 0);
  if (!savedSkillCategories.length) errors.push("At least one skill category with one skill is required.");
  const categoryIds = new Set<string>();
  const categoryNames = new Set<string>();
  savedSkillCategories.forEach((category, index) => {
    const label = `Skill category ${index + 1}`;
    if (categoryIds.has(category.categoryId ?? "")) errors.push(`${label} category ID must be unique.`);
    categoryIds.add(category.categoryId ?? "");
    const nameKey = category.category.trim().toLowerCase();
    if (!nameKey) errors.push(`${label} name is required.`);
    if (categoryNames.has(nameKey)) errors.push(`${label} duplicates another category name.`);
    categoryNames.add(nameKey);
    const itemKeys = new Set<string>();
    category.items.forEach((item) => {
      const key = item.toLowerCase();
      if (itemKeys.has(key)) errors.push(`${label} contains duplicate skill ${item}.`);
      if (hasCategoryPrefix(item)) errors.push(`${label} skill "${item}" still contains a category label.`);
      itemKeys.add(key);
    });
  });
  if (!firstExperience) {
    errors.push("At least one work experience is required.");
  } else {
    profile.experience
      .filter((item) => item.company.trim() || item.role.trim() || item.startDate.trim() || item.endDate.trim() || item.city.trim() || item.country.trim())
      .forEach((item, index) => {
        const label = `Work experience ${index + 1}`;
        if (!item.company.trim()) errors.push(`${label} company is required.`);
        if (!item.role.trim()) errors.push(`${label} role is required.`);
        errors.push(...validateStructuredLocation({ city: item.city, state: item.state || null, country: item.country }, `${label} location`));
        if (!item.startDate.trim()) errors.push(`${label} start date is required.`);
        if (!item.isCurrentRole && !item.endDate.trim()) errors.push(`${label} end date is required.`);
        const start = parseProfileDate(item.startDate);
        const end = item.isCurrentRole ? null : parseProfileDate(item.endDate);
        if (!item.isCurrentRole && end && start && datePrecedes(end, start)) errors.push(`${label} end date cannot be before start date.`);
        item.metrics.forEach((metric, metricIndex) => {
          if ((metric.label.trim() && !metric.value.trim()) || (!metric.label.trim() && metric.value.trim())) {
            errors.push(`${label} metric ${metricIndex + 1} requires both label and value.`);
          }
        });
      });
  }

  profile.education
    .filter((item) => item.degree.trim() || item.institution.trim() || item.gradYear.trim() || item.location.trim() || item.gpa.trim())
    .forEach((item, index) => {
      const label = `Education ${index + 1}`;
      if (!item.degree.trim()) errors.push(`${label} degree is required.`);
      if (!item.institution.trim()) errors.push(`${label} institution is required.`);
      if (!item.gradYear.trim()) errors.push(`${label} graduation year is required.`);
    });

  const validExperienceIds = new Set(profile.experience.map((item) => item.id).filter(Boolean));
  profile.projects
    .filter((item) => item.name.trim() || item.org.trim() || item.link.trim() || item.bullets.trim() || item.technologies.trim() || item.linkedExperienceIds.length)
    .forEach((item, index) => {
      const label = `Project ${index + 1}`;
      if (!item.name.trim()) errors.push(`${label} name is required.`);
      const linkIds = item.linkedExperienceIds.map((id) => id.trim());
      if (linkIds.some((id) => !id)) errors.push(`${label} related work experience cannot contain blank IDs.`);
      if (new Set(linkIds).size !== linkIds.length) errors.push(`${label} related work experience cannot contain duplicate IDs.`);
      linkIds.forEach((experienceId) => {
        if (!validExperienceIds.has(experienceId)) errors.push(`${label} references a work experience that no longer exists.`);
      });
    });

  profile.certifications
    .filter((item) => item.name.trim() || item.issuer.trim() || item.issuedDate.trim() || item.expiryDate.trim())
    .forEach((item, index) => {
      const label = `Certification ${index + 1}`;
      if (!item.name.trim()) errors.push(`${label} name is required.`);
      if (!item.issuer.trim()) errors.push(`${label} issuer is required.`);
    });

  return errors;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm font-semibold text-slate-800">
      {label}
      <div className="mt-2">{children}</div>
    </label>
  );
}

function EmptyResumeState() {
  return (
    <Card className="grid min-h-[420px] place-items-center rounded-md p-8 text-center">
      <div className="max-w-md">
        <div className="mx-auto mb-5 grid h-12 w-12 place-items-center rounded-md bg-[#e6f4f8] text-[#0f7891]">
          <Sparkles size={22} />
        </div>
        <h3 className="text-xl font-bold">Ready to tailor a resume</h3>
        <p className="mt-3 text-slate-500">
          Paste a job description, confirm the target role, then generate an ATS-friendly resume preview.
        </p>
      </div>
    </Card>
  );
}

function GeneratingState() {
  return (
    <Card className="rounded-md p-8">
      <div className="mb-6 flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-md bg-[#e6f4f8] text-[#0f7891]">
          <Sparkles size={18} />
        </div>
        <div>
          <h3 className="text-xl font-bold">Generating resume</h3>
          <p className="text-slate-500">Matching the job description and applying the resume format rules.</p>
        </div>
      </div>
      <div className="space-y-4">
        <div className="h-5 w-3/4 animate-pulse rounded bg-slate-200" />
        <div className="h-5 w-11/12 animate-pulse rounded bg-slate-200" />
        <div className="h-5 w-2/3 animate-pulse rounded bg-slate-200" />
        <div className="mt-8 h-40 animate-pulse rounded bg-slate-100" />
      </div>
    </Card>
  );
}

function AtsCard({
  generation,
  onApplyKeyword,
}: {
  generation: GeneratedResumeResponse;
  onApplyKeyword: (keyword: string) => void;
}) {
  const score = generation.atsAnalysis?.score ?? generation.atsScore;
  const breakdown = generation.atsAnalysis?.breakdown ?? generation.breakdown;
  const suggestions = generation.atsAnalysis?.suggestions ?? generation.suggestions;
  const scoreTone = score >= 85 ? "Strong" : score >= 75 ? "Good" : "Needs work";

  return (
    <Card className="rounded-md p-8">
      <div className="grid gap-8 xl:grid-cols-[190px_1fr]">
        <div className="flex flex-col items-center justify-center gap-5">
          <div
            className="grid h-36 w-36 place-items-center rounded-full p-[14px]"
            style={{
              background: `conic-gradient(#bb7200 ${score * 3.6}deg, #e2e8f0 0deg)`,
            }}
          >
            <div className="grid h-full w-full place-items-center rounded-full bg-white text-center">
              <div>
                <p className="text-5xl font-bold">{score}</p>
              <p className="text-sm text-slate-500">out of 100</p>
              </div>
            </div>
          </div>
          <Badge tone="amber" className="rounded-full px-4">
            {scoreTone}
          </Badge>
        </div>
        <div>
          <div className="mb-6 flex items-center justify-between">
            <h3 className="text-xl font-bold">ATS match score</h3>
            <span className="text-slate-500">{suggestions.length} suggestions left</span>
          </div>
          <ScoreRow label="Keyword match" value={breakdown.keywordMatch} color="bg-[#0f7891]" />
          <ScoreRow label="Formatting" value={breakdown.formatting} color="bg-emerald-600" />
          <ScoreRow label="Readability" value={breakdown.readability} color="bg-emerald-600" />
          <div className="mt-6 border-t border-slate-200 pt-5">
            <p className="mb-4 text-slate-500">Keywords from the job description</p>
            <div className="flex flex-wrap gap-2">
              {breakdown.matchedKeywords.map((keyword) => (
                <Badge key={keyword} tone="green" className="rounded-full px-3">
                  <Check size={13} />
                  {keyword}
                </Badge>
              ))}
              {breakdown.missingKeywords.map((keyword) => (
                <button
                  key={keyword}
                  type="button"
                  className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-sm text-slate-700 transition hover:border-[#0f7891] hover:bg-[#e6f4f8] hover:text-[#07566a]"
                  onClick={() => onApplyKeyword(keyword)}
                  title={`Add ${keyword} to resume skills`}
                >
                  <Plus size={13} />
                  {keyword}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}

function ResumeAiMetricsCard({ generation }: { generation: GeneratedResumeResponse }) {
  const metrics = generation.aiMetrics;
  const metadata = generation.generationMetadata;
  if (!metrics && !metadata) return null;
  const generationTimeMs = metadata?.durationMs ?? metrics?.generationTimeMs ?? 0;
  const modelsUsed = metadata?.model ? [metadata.model] : metrics?.modelsUsed ?? [];

  return (
    <Card className="rounded-md p-5">
      <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
        <MiniMetric label="Generation time" value={`${Math.max(1, Math.round(generationTimeMs / 1000))}s`} />
        <MiniMetric label="AI cost" value={formatMoney(metrics?.aiCost ?? 0)} />
        <MiniMetric label="Tokens used" value={(metrics?.tokensUsed ?? 0).toLocaleString()} />
        <MiniMetric label="Models used" value={modelsUsed.length ? modelsUsed.join(", ") : "None"} />
        <MiniMetric label="Cache used" value={metrics?.cacheUsed ? "Yes" : "No"} />
        <MiniMetric label="Validation score" value={`${metrics?.validationScore ?? 100}/100`} />
      </div>
    </Card>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-bold uppercase tracking-wider text-slate-500">{label}</p>
      <p className="mt-1 truncate text-base font-semibold text-slate-900" title={value}>{value}</p>
    </div>
  );
}

function ScoreRow({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="mb-4 grid grid-cols-[160px_1fr_40px] items-center gap-4">
      <span className="text-slate-700">{label}</span>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div className={cn("h-full rounded-full", color)} style={{ width: `${value}%` }} />
      </div>
      <span className="text-right text-sm">{value}</span>
    </div>
  );
}

function SuggestionsCard({
  suggestions,
  onApply,
  onApplyAll,
}: {
  suggestions: Array<{ text: string; points: number }>;
  onApply: (suggestionText: string) => void;
  onApplyAll: () => void;
}) {
  return (
    <Card className="rounded-md p-8">
      <div className="mb-6 flex items-center justify-between">
        <h3 className="text-xl font-bold">Improve your score</h3>
        <button className="font-semibold text-[#0b718a] disabled:cursor-not-allowed disabled:opacity-40" onClick={onApplyAll} disabled={suggestions.length === 0}>
          Apply all
        </button>
      </div>
      <div className="divide-y divide-slate-200">
        {suggestions.length === 0 && <p className="text-slate-500">No suggestions returned for this resume.</p>}
        {suggestions.map((suggestion) => (
          <div key={suggestion.text} className="grid grid-cols-[40px_1fr_auto_auto] items-center gap-4 py-4">
            <div className="grid h-9 w-9 place-items-center rounded-md bg-[#e6f4f8] text-[#0f7891]">
              <Sparkles size={15} />
            </div>
            <p className="text-slate-800">{suggestion.text}</p>
            <span className="text-sm text-emerald-700">+{suggestion.points}</span>
            <Button variant="secondary" size="sm" onClick={() => onApply(suggestion.text)}>
              Apply
            </Button>
          </div>
        ))}
      </div>
    </Card>
  );
}

function ResumePreview({
  resume,
  editable,
  onResumeChange,
}: {
  resume: GeneratedResumeResponse["resume"];
  editable: boolean;
  onResumeChange: (resume: GeneratedResume) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-md border border-slate-200 bg-slate-100 px-4 py-6">
      <ResumeDocument resume={resume} editable={editable} onResumeChange={onResumeChange} />
    </div>
  );
}

function HistoryPage({
  resumes,
  updateStatus,
}: {
  resumes: ResumeRow[];
  updateStatus: (id: string, status: ResumeStatus) => void;
}) {
  const navigate = useNavigate();

  return (
    <PageFrame>
      <div className="mb-7 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">
            Resume history <span className="ml-3 text-base text-slate-500">{resumes.length}</span>
          </h1>
          <p className="mt-8 text-lg text-slate-500">
            Every resume you generate is saved here. Update the application status to track where each one stands.
          </p>
        </div>
        <Button className="bg-[#0f7891] hover:bg-[#09677d]" onClick={() => navigate("/generate")}>
          <Plus size={18} />
          New resume
        </Button>
      </div>
      <Card className="overflow-hidden rounded-md">
        <div className="grid grid-cols-[1.25fr_0.6fr_0.35fr_0.9fr_0.7fr_80px] border-b border-slate-200 bg-slate-50 px-5 py-4 text-sm font-bold uppercase tracking-wider text-slate-500">
          <span>Role</span>
          <span>Company</span>
          <span>ATS</span>
          <span>Application status</span>
          <span>Created</span>
          <span />
        </div>
        {resumes.length === 0 && (
          <div className="p-8 text-slate-500">
            No generated resumes yet. Generate a resume to create the first ATS score record.
          </div>
        )}
        {resumes.map((resume) => (
          <div key={resume.id} className="grid grid-cols-[1.25fr_0.6fr_0.35fr_0.9fr_0.7fr_80px] items-center border-b border-slate-200 px-5 py-4 last:border-b-0">
            <span className="font-semibold">{resume.role}</span>
            <span>{resume.company}</span>
            <span className={cn("font-semibold", resume.ats >= 80 ? "text-emerald-700" : resume.ats >= 70 ? "text-amber-700" : "text-red-700")}>{resume.ats}</span>
            <Select value={resume.status} onChange={(event) => updateStatus(resume.id, event.target.value as ResumeStatus)} className="w-48 rounded-none">
              {["Draft", "Applied", "Interview", "Offer", "Rejected"].map((status) => (
                <option key={status}>{status}</option>
              ))}
            </Select>
            <span className="text-slate-500">{resume.created}</span>
            <div className="flex items-center justify-end gap-4 text-slate-700">
              <Eye size={17} />
              <Download size={17} />
            </div>
          </div>
        ))}
      </Card>
    </PageFrame>
  );
}

function AnalyticsPage({ resumes }: { resumes: ResumeRow[] }) {
  const stats = useMemo(() => {
    const applications = resumes.filter((resume) => resume.status !== "Draft").length;
    const interviews = resumes.filter((resume) => ["Interview", "Offer"].includes(resume.status)).length;
    const offers = resumes.filter((resume) => resume.status === "Offer").length;
    const avg = resumes.length ? Math.round(resumes.reduce((sum, resume) => sum + resume.ats, 0) / resumes.length) : 0;
    return { applications, interviews, offers, avg };
  }, [resumes]);
  const avgDetail = resumes.length ? (stats.avg >= 85 ? "strong" : stats.avg >= 75 ? "good" : "needs work") : "generate first";

  return (
    <PageFrame>
      <h1 className="mb-8 text-3xl font-bold">Analytics</h1>
      <div className="grid gap-5 xl:grid-cols-4">
        <StatCard label="Resumes generated" value={resumes.length} detail="across all roles" />
        <StatCard label="Applications sent" value={stats.applications} detail="tracked in history" />
        <StatCard label="Interviews" value={stats.interviews} detail="reached interview stage" />
        <StatCard label="Average ATS" value={stats.avg} detail={avgDetail} />
      </div>
      <div className="mt-8 grid gap-5 xl:grid-cols-[1fr_1fr]">
        <Card className="rounded-md p-8">
          <h2 className="mb-6 text-xl font-bold">ATS score by resume</h2>
          <div className="space-y-5">
            {resumes.length === 0 && <p className="text-slate-500">Generated resume scores will appear here.</p>}
            {resumes.map((resume) => (
              <ScoreBar key={resume.id} label={resume.company} value={resume.ats} />
            ))}
          </div>
        </Card>
        <Card className="rounded-md p-8">
          <h2 className="mb-6 text-xl font-bold">Application funnel</h2>
          <FunnelRow label="Resumes generated" value={resumes.length} max={resumes.length} />
          <FunnelRow label="Applied" value={stats.applications} max={resumes.length} />
          <FunnelRow label="Interview stage" value={stats.interviews} max={resumes.length} />
          <FunnelRow label="Offers" value={stats.offers} max={resumes.length} />
        </Card>
      </div>
    </PageFrame>
  );
}

function AiUsagePage() {
  const [dashboard, setDashboard] = useState<AiUsageDashboard | null>(null);
  const [filters, setFilters] = useState({ date: "", user: "", model: "", feature: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const chartColors = ["#0f7891", "#0f9f86", "#bb7200", "#4f46e5", "#dc2626"];

  const loadDashboard = async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams(
        Object.entries(filters).filter(([, value]) => value.trim()) as Array<[string, string]>,
      );
      const response = await fetch(`/api/ai-usage/dashboard?${params.toString()}`);
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(data?.detail ?? "Could not load AI usage.");
      setDashboard(data as AiUsageDashboard);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load AI usage.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadDashboard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const exportCsv = () => {
    const params = new URLSearchParams(
      Object.entries(filters).filter(([, value]) => value.trim()) as Array<[string, string]>,
    );
    window.location.href = `/api/ai-usage/export.csv?${params.toString()}`;
  };

  return (
    <PageFrame>
      <div className="mb-8 flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h1 className="text-3xl font-bold">AI Usage</h1>
          <p className="mt-3 text-lg text-slate-500">
            Monitor request volume, cache hit rate, token usage, latency, and estimated billing.
          </p>
        </div>
        <div className="flex gap-3">
          <Button variant="secondary" onClick={loadDashboard} disabled={loading}>
            {loading ? "Refreshing..." : "Refresh"}
          </Button>
          <Button className="bg-[#0f7891] hover:bg-[#09677d]" onClick={exportCsv}>Export CSV</Button>
        </div>
      </div>

      <Card className="mb-6 rounded-md p-5">
        <div className="grid gap-4 xl:grid-cols-4">
          <Field label="Date">
            <Input type="date" value={filters.date} onChange={(event) => setFilters({ ...filters, date: event.target.value })} />
          </Field>
          <Field label="User">
            <Input value={filters.user} onChange={(event) => setFilters({ ...filters, user: event.target.value })} placeholder="local-user" />
          </Field>
          <Field label="Model">
            <Input value={filters.model} onChange={(event) => setFilters({ ...filters, model: event.target.value })} placeholder="gpt-5.5" />
          </Field>
          <Field label="Feature">
            <Input value={filters.feature} onChange={(event) => setFilters({ ...filters, feature: event.target.value })} placeholder="resume_generation" />
          </Field>
        </div>
        <div className="mt-5 flex justify-end">
          <Button variant="secondary" onClick={loadDashboard}>Apply filters</Button>
        </div>
      </Card>

      {error && <p className="mb-4 rounded-md bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">{error}</p>}

      <div className="grid gap-5 xl:grid-cols-4">
        <StatCard label="Today's requests" value={dashboard?.cards.todayRequests ?? 0} detail="AI calls and cache hits" />
        <StatCard label="Today's cost" value={Number((dashboard?.cards.todayCost ?? 0).toFixed(4))} detail="estimated API spend" />
        <StatCard label="This month cost" value={Number((dashboard?.cards.monthCost ?? 0).toFixed(4))} detail="estimated API spend" />
        <StatCard label="Total tokens" value={dashboard?.cards.totalTokens ?? 0} detail="tracked tokens" />
      </div>
      <div className="mt-5 grid gap-5 xl:grid-cols-4">
        <StatCard label="Avg cost / resume" value={Number((dashboard?.cards.averageCostPerResume ?? 0).toFixed(4))} detail="generated resumes" />
        <StatCard label="Cache hit rate" value={dashboard?.cards.cacheHitRate ?? 0} detail="percent avoided calls" />
        <StatCard label="Avg response time" value={dashboard?.cards.averageResponseTimeMs ?? 0} detail="milliseconds" />
        <StatCard label="Billable requests" value={dashboard?.cards.billableRequests ?? 0} detail="excluding local cache hits" />
      </div>

      <div className="mt-8 grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
        <Card className="rounded-md p-6">
          <h2 className="mb-5 text-xl font-bold">Usage by model</h2>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={dashboard?.usageByModel ?? []} dataKey="tokens" nameKey="model" outerRadius={100} label>
                  {(dashboard?.usageByModel ?? []).map((item, index) => (
                    <Cell key={item.model} fill={chartColors[index % chartColors.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card className="rounded-md p-6">
          <h2 className="mb-5 text-xl font-bold">Cost by day</h2>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dashboard?.costByDay ?? []}>
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="cost" fill="#0f7891" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <Card className="mt-8 overflow-hidden rounded-md">
        <div className="grid grid-cols-[1.1fr_0.8fr_1fr_0.8fr_0.5fr_0.7fr_0.6fr_0.6fr_0.6fr] border-b border-slate-200 bg-slate-50 px-4 py-3 text-xs font-bold uppercase tracking-wider text-slate-500">
          <span>Date</span>
          <span>User</span>
          <span>Feature</span>
          <span>Model</span>
          <span>Tokens</span>
          <span>Cost</span>
          <span>Latency</span>
          <span>Status</span>
          <span>Cache</span>
        </div>
        {(dashboard?.events ?? []).length === 0 && <p className="p-5 text-slate-500">No AI usage events yet.</p>}
        {(dashboard?.events ?? []).map((event) => (
          <div key={event.id} className="grid grid-cols-[1.1fr_0.8fr_1fr_0.8fr_0.5fr_0.7fr_0.6fr_0.6fr_0.6fr] items-center border-b border-slate-100 px-4 py-3 text-sm last:border-b-0">
            <span className="text-slate-500">{new Date(event.timestamp).toLocaleString()}</span>
            <span>{event.user}</span>
            <span className="truncate" title={event.feature}>{event.feature}</span>
            <span>{event.model}</span>
            <span>{event.totalTokens.toLocaleString()}</span>
            <span>{formatMoney(event.estimatedCost)}</span>
            <span>{event.latencyMs}ms</span>
            <Badge tone={event.status === "success" ? "green" : event.cacheHit ? "blue" : "amber"}>{event.status}</Badge>
            <span>{event.cacheHit ? "Yes" : "No"}</span>
          </div>
        ))}
      </Card>
    </PageFrame>
  );
}

function StatCard({ label, value, detail }: { label: string; value: number; detail: string }) {
  return (
    <Card className="rounded-md p-5">
      <p className="text-sm font-bold uppercase tracking-wider text-slate-500">{label}</p>
      <p className="mt-3 text-3xl font-bold">{value}</p>
      <p className={cn("mt-3 text-slate-500", detail === "strong" && "font-semibold text-emerald-700")}>{detail}</p>
    </Card>
  );
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const color = value >= 80 ? "bg-emerald-700" : value >= 70 ? "bg-[#bb7200]" : "bg-red-700";
  return (
    <div className="grid grid-cols-[140px_1fr_40px] items-center gap-6">
      <span>{label}</span>
      <Progress value={value} className="[&>div]:bg-transparent" />
      <span className="text-sm">{value}</span>
      <div className="col-start-2 row-start-1 h-2 overflow-hidden rounded-full bg-slate-100">
        <div className={cn("h-full rounded-full", color)} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

function FunnelRow({ label, value, max }: { label: string; value: number; max: number }) {
  const width = max > 0 ? (value / max) * 100 : 0;

  return (
    <div className="mb-7">
      <div className="mb-3 flex justify-between">
        <span>{label}</span>
        <span className="font-bold">{value}</span>
      </div>
      <div className="h-3 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-[#0f7891]" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function InterviewPage() {
  const [practiced, setPracticed] = useState<string[]>([]);
  const progress = (practiced.length / questions.length) * 100;

  return (
    <PageFrame>
      <h1 className="mb-8 text-3xl font-bold">Interview prep</h1>
      <Card className="mb-7 rounded-md p-8">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold">Practice for Senior Frontend Engineer</h2>
            <p className="mt-3 text-lg text-slate-500">Questions tailored to your target role and the job descriptions you've used.</p>
            <div className="mt-5 flex items-center gap-4">
              <Progress value={progress} className="w-80" />
              <span className="text-slate-500">
                {practiced.length} of {questions.length} practiced
              </span>
            </div>
          </div>
          <Button className="bg-[#0f7891] hover:bg-[#09677d]">
            <Play size={17} />
            Start mock interview
          </Button>
        </div>
      </Card>
      <Card className="rounded-md px-8 py-4">
        <div className="divide-y divide-slate-200">
          {questions.map(([category, question]) => {
            const isPracticed = practiced.includes(question);
            return (
              <div key={question} className="grid grid-cols-[120px_1fr_auto] items-center gap-5 py-5">
                <QuestionBadge category={category} />
                <p className="text-lg">{question}</p>
                <Button
                  variant={isPracticed ? "default" : "secondary"}
                  className={cn(isPracticed && "bg-emerald-700 hover:bg-emerald-800")}
                  onClick={() =>
                    setPracticed((current) =>
                      current.includes(question) ? current.filter((item) => item !== question) : [...current, question],
                    )
                  }
                >
                  {isPracticed ? "Practiced" : "Mark practiced"}
                </Button>
              </div>
            );
          })}
        </div>
      </Card>
    </PageFrame>
  );
}

function QuestionBadge({ category }: { category: string }) {
  const styles =
    category === "Behavioral"
      ? "border-[#87c5d7] bg-[#e6f4f8] text-[#07566a]"
      : category === "Design"
        ? "border-amber-300 bg-amber-50 text-amber-800"
        : "border-slate-200 bg-slate-100 text-slate-700";
  return <span className={cn("rounded-full border px-4 py-1 text-center font-medium", styles)}>{category}</span>;
}

function PageFrame({ children }: { children: React.ReactNode }) {
  return <div className="px-8 py-10 lg:px-12">{children}</div>;
}

function PlaceholderPage({ title, description }: { title: string; description: string }) {
  return (
    <PageFrame>
      <Card className="max-w-3xl p-8">
        <h1 className="text-2xl font-bold">{title}</h1>
        <p className="mt-3 text-slate-500">{description}</p>
      </Card>
    </PageFrame>
  );
}
