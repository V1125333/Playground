import {
  ArrowDown,
  ArrowUp,
  BarChart3,
  Check,
  ChevronRight,
  ClipboardList,
  Download,
  Eye,
  FileText,
  History,
  Mic,
  Play,
  Plus,
  UserRound,
  RefreshCw,
  Settings,
  Sparkles,
  GripVertical,
  WandSparkles,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
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
  GeneratedResume,
  GeneratedResumeResponse,
  JobAnalysisResponse,
  JobKeywordAnalysisItem,
} from "./resume/types";
import { createProfile, getPrimaryProfile, updateProfile } from "./services/profileService";
import { generateResume as generateStructuredResume } from "./services/resumeService";

type ResumeStatus = "Draft" | "Applied" | "Interview" | "Offer" | "Rejected";

type ResumeRow = {
  id: string;
  role: string;
  company: string;
  ats: number;
  status: ResumeStatus;
  created: string;
};

type CandidateProfileForm = {
  firstName: string;
  lastName: string;
  title: string;
  email: string;
  phone: string;
  location: string;
  linkedin: string;
  github: string;
  portfolio: string;
  skills: string;
  experience: WorkExperienceForm[];
  education: EducationForm[];
  certifications: CertificationForm[];
};

type SetProfile = React.Dispatch<React.SetStateAction<CandidateProfileForm>>;

type WorkExperienceForm = {
  id: string;
  company: string;
  role: string;
  location: string;
  startDate: string;
  endDate: string;
  impactMetrics: string;
};

type EducationForm = {
  id: string;
  degree: string;
  institution: string;
  location: string;
  gradYear: string;
  gpa: string;
};

type CertificationForm = {
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
  location: "",
  linkedin: "",
  github: "",
  portfolio: "",
  skills: "",
  experience: [
    {
      id: "exp-1",
      company: "",
      role: "",
      location: "",
      startDate: "",
      endDate: "",
      impactMetrics: "",
    },
  ],
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
    return {
      ...initialProfile,
      ...parsed,
      experience: parsed.experience?.length
        ? normalizeExperienceForms(parsed.experience as WorkExperienceForm[])
        : initialProfile.experience,
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
    || profile.skills.trim()
    || profile.experience.some((item) => item.company.trim() || item.role.trim()),
  );
}

function normalizeExperienceForms(experience: WorkExperienceForm[]) {
  return experience.map((item) => ({
    ...initialProfile.experience[0],
    ...item,
    impactMetrics: item.impactMetrics ?? "",
  }));
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

export default function App() {
  const navigate = useNavigate();
  const [resumes, setResumes] = useState<ResumeRow[]>(() => loadStoredResumes());
  const [profile, setProfile] = useState<CandidateProfileForm>(() => loadStoredProfile());
  const [profileRecord, setProfileRecord] = useState<CandidateProfileRecord | null>(null);
  const [profileLoadError, setProfileLoadError] = useState("");
  const [authToken, setAuthToken] = useState(() => window.localStorage.getItem(AUTH_TOKEN_KEY) ?? "");
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
        ats: generation.atsScore,
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

  if (!authToken || !authUser) {
    return <AuthPage onLogin={completeLogin} />;
  }

  return (
    <div className="min-h-screen bg-[#f5f6f8] text-[#020817]">
      <Sidebar user={authUser} />
      <div className="min-h-screen lg:pl-[240px]">
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

function Sidebar({ user }: { user: AuthUser }) {
  const initials = userInitials(user.name);

  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-[240px] flex-col border-r border-slate-200 bg-white text-slate-950 lg:flex">
      <div className="flex h-16 items-center gap-3 px-5">
        <img src={jobyroIcon} alt="Jobyro" className="h-9 w-9 rounded-lg object-contain" />
        <span className="text-lg font-semibold">Jobyro</span>
      </div>

      <nav className="flex-1 space-y-1 px-3 pt-2">
        {navigation.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                "relative flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-blue-500",
                isActive && "bg-blue-50 text-blue-700",
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && <span className="absolute -left-3 h-6 w-1 rounded-r bg-blue-600" />}
                <item.icon size={18} />
                {item.label}
              </>
            )}
          </NavLink>
        ))}
        {user.role === "super_admin" && (
          <NavLink
            to="/ai-usage"
            className={({ isActive }) =>
              cn(
                "relative flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-950",
                isActive && "bg-blue-50 text-blue-700",
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && <span className="absolute -left-3 h-6 w-1 rounded-r bg-blue-600" />}
                <ClipboardList size={18} />
                AI Usage
              </>
            )}
          </NavLink>
        )}
        {user.role === "super_admin" && (
          <NavLink
            to="/admin/temp-passwords"
            className={({ isActive }) =>
              cn(
                "relative flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-950",
                isActive && "bg-blue-50 text-blue-700",
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && <span className="absolute -left-3 h-6 w-1 rounded-r bg-blue-600" />}
                <Settings size={18} />
                Temp passwords
              </>
            )}
          </NavLink>
        )}
        <div className="mx-1 mt-8 border-t border-slate-200" />
      </nav>

      <div className="flex items-center gap-3 border-t border-slate-200 p-4">
        <div className="grid h-9 w-9 place-items-center rounded-full bg-blue-100 text-sm font-bold text-blue-700">
          {initials}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold">{user.name}</p>
          <p className="text-sm text-slate-500">{user.role === "super_admin" ? "Super admin" : "User"}</p>
        </div>
        <button className="grid h-9 w-9 place-items-center rounded-md text-slate-500 hover:bg-slate-100" aria-label="Settings">
          <Settings size={18} />
        </button>
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
        suggestions: current.suggestions.filter((suggestion) => suggestion.text !== suggestionText),
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

      return {
        ...current,
        atsScore: Math.min(100, current.atsScore + 2),
        breakdown: {
          ...current.breakdown,
          keywordMatch: Math.min(100, current.breakdown.keywordMatch + 5),
          matchedKeywords: Array.from(new Set([...current.breakdown.matchedKeywords, keyword])),
          missingKeywords: current.breakdown.missingKeywords.filter((item) => item !== keyword),
        },
        resume: {
          ...current.resume,
          skills,
        },
      };
    });
  };

  const applyAllSuggestions = () => {
    setGeneration((current) => current ? { ...current, suggestions: [] } : current);
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
            <SuggestionsCard suggestions={generation.suggestions} onApply={applySuggestion} onApplyAll={applyAllSuggestions} />
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
  authToken,
  profileRecord,
  setProfileRecord,
  profileLoadError,
}: {
  profile: CandidateProfileForm;
  setProfile: SetProfile;
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
    const errors = validateProfile(profile);
    if (errors.length > 0) {
      setProfileErrors(errors);
      setSavedAt(null);
      setIsEditing(true);
      return;
    }

    setProfileErrors([]);
    try {
      const payload = buildCandidateProfile(profile);
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

  const updateField = (field: keyof Omit<CandidateProfileForm, "experience" | "education" | "certifications">, value: string) => {
    setProfile((current) => {
      const next = { ...current, [field]: value };
      saveStoredProfile(next);
      return next;
    });
  };

  const updateExperience = (id: string, field: keyof Omit<WorkExperienceForm, "id">, value: string) => {
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
            role: "",
            location: "",
            startDate: "",
            endDate: "",
            impactMetrics: "",
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
        <Field label="Location">
          <Input value={profile.location} onChange={(event) => updateField("location", event.target.value)} className="h-11 rounded-none text-base" />
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

      <label className="mt-4 block text-sm font-semibold text-slate-800">
        Skills
        <textarea
          className="mt-2 h-24 w-full resize-none rounded-none border border-slate-300 bg-white px-3 py-2 text-base outline-none focus:border-[#0f7891] focus:ring-4 focus:ring-[#0f7891]/10"
          placeholder="React, TypeScript, GraphQL, WCAG, CI/CD"
          value={profile.skills}
          onChange={(event) => updateField("skills", event.target.value)}
        />
      </label>

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
              <Field label="Role">
                <Input value={experience.role} onChange={(event) => updateExperience(experience.id, "role", event.target.value)} className="h-11 rounded-none text-base" />
              </Field>
              <Field label="Location">
                <Input value={experience.location} onChange={(event) => updateExperience(experience.id, "location", event.target.value)} className="h-11 rounded-none text-base" />
              </Field>
              <Field label="Start date">
                <Input value={experience.startDate} onChange={(event) => updateExperience(experience.id, "startDate", event.target.value)} className="h-11 rounded-none text-base" placeholder="YYYY-MM" />
              </Field>
              <Field label="End date">
                <Input value={experience.endDate} onChange={(event) => updateExperience(experience.id, "endDate", event.target.value)} className="h-11 rounded-none text-base" placeholder="YYYY-MM or Present" />
              </Field>
            </div>
            <label className="mt-4 block text-sm font-semibold">
              Impact metrics
              <textarea
                className="mt-2 h-20 w-full resize-none rounded-none border border-slate-300 bg-white px-3 py-2 text-base outline-none focus:border-[#0f7891] focus:ring-4 focus:ring-[#0f7891]/10 disabled:bg-slate-100"
                value={experience.impactMetrics}
                onChange={(event) => updateExperience(experience.id, "impactMetrics", event.target.value)}
                disabled={disabled}
                placeholder="Examples: supported 5 applications; reviewed 20 PRs/month; reduced defects by 15%; handled 30 tickets/month; delivered 8 releases"
              />
            </label>
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

function buildCandidateProfile(profile: CandidateProfileForm): GeneratedResume {
  const name = [profile.firstName, profile.lastName].map((part) => part.trim()).filter(Boolean).join(" ");
  const skillItems = profile.skills
    .split(/[,\n]/)
    .map((skill) => skill.trim())
    .filter(Boolean);

  return {
    name,
    title: profile.title.trim(),
    contact: {
      phone: profile.phone.trim(),
      email: profile.email.trim(),
      location: profile.location.trim(),
      linkedin: profile.linkedin.trim(),
      github: profile.github.trim(),
      portfolio: profile.portfolio.trim(),
    },
    summary: "",
    skills: skillItems.length ? [{ category: "Technical Skills", items: skillItems }] : [],
    experience: profile.experience
      .filter((item) => item.company.trim() || item.role.trim())
      .map((item) => ({
        experienceId: item.id,
        company: item.company.trim(),
        role: item.role.trim(),
        location: item.location.trim(),
        startDate: item.startDate.trim(),
        endDate: item.endDate.trim(),
        rawNotes: item.impactMetrics.trim(),
        bullets: [],
      })),
    projects: [],
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

function profileFormFromCandidateProfile(profile: GeneratedResume): CandidateProfileForm {
  const [firstName = "", ...lastParts] = profile.name.trim().split(/\s+/).filter(Boolean);
  return {
    ...initialProfile,
    firstName,
    lastName: lastParts.join(" "),
    title: profile.title ?? "",
    email: profile.contact.email ?? "",
    phone: profile.contact.phone ?? "",
    location: profile.contact.location ?? "",
    linkedin: profile.contact.linkedin ?? "",
    github: profile.contact.github ?? "",
    portfolio: profile.contact.portfolio ?? "",
    skills: profile.skills.flatMap((group) => group.items).join(", "),
    experience: profile.experience.length
      ? profile.experience.map((item, index) => ({
          id: item.experienceId ?? `exp-${index + 1}`,
          company: item.company,
          role: item.role,
          location: item.location ?? "",
          startDate: item.startDate ?? "",
          endDate: item.endDate ?? "",
          impactMetrics: item.rawNotes ?? item.metricFlags?.join("\n") ?? "",
        }))
      : initialProfile.experience,
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

function validateProfile(profile: CandidateProfileForm) {
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
  if (!profile.location.trim()) errors.push("Location is required.");
  if (!profile.skills.trim()) errors.push("Skills are required.");
  if (!firstExperience) {
    errors.push("At least one work experience is required.");
  } else {
    profile.experience
      .filter((item) => item.company.trim() || item.role.trim() || item.startDate.trim() || item.endDate.trim())
      .forEach((item, index) => {
        const label = `Work experience ${index + 1}`;
        if (!item.company.trim()) errors.push(`${label} company is required.`);
        if (!item.role.trim()) errors.push(`${label} role is required.`);
        if (!item.startDate.trim()) errors.push(`${label} start date is required.`);
        if (!item.endDate.trim()) errors.push(`${label} end date is required.`);
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
  const score = generation.atsScore;
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
            <span className="text-slate-500">{generation.suggestions.length} suggestions left</span>
          </div>
          <ScoreRow label="Keyword match" value={generation.breakdown.keywordMatch} color="bg-[#0f7891]" />
          <ScoreRow label="Formatting" value={generation.breakdown.formatting} color="bg-emerald-600" />
          <ScoreRow label="Readability" value={generation.breakdown.readability} color="bg-emerald-600" />
          <div className="mt-6 border-t border-slate-200 pt-5">
            <p className="mb-4 text-slate-500">Keywords from the job description</p>
            <div className="flex flex-wrap gap-2">
              {generation.breakdown.matchedKeywords.map((keyword) => (
                <Badge key={keyword} tone="green" className="rounded-full px-3">
                  <Check size={13} />
                  {keyword}
                </Badge>
              ))}
              {generation.breakdown.missingKeywords.map((keyword) => (
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
  if (!metrics) return null;

  return (
    <Card className="rounded-md p-5">
      <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
        <MiniMetric label="Generation time" value={`${Math.max(1, Math.round(metrics.generationTimeMs / 1000))}s`} />
        <MiniMetric label="AI cost" value={formatMoney(metrics.aiCost)} />
        <MiniMetric label="Tokens used" value={metrics.tokensUsed.toLocaleString()} />
        <MiniMetric label="Models used" value={metrics.modelsUsed.length ? metrics.modelsUsed.join(", ") : "None"} />
        <MiniMetric label="Cache used" value={metrics.cacheUsed ? "Yes" : "No"} />
        <MiniMetric label="Validation score" value={`${metrics.validationScore}/100`} />
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
