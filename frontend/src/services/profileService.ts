import type { CandidateProfileRecord, GeneratedResume } from "../resume/types";

const jsonHeaders = (token: string) => ({
  "Content-Type": "application/json",
  Authorization: `Bearer ${token}`,
});

async function requestProfile<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      Authorization: `Bearer ${token}`,
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    const detail = error?.detail;
    throw new Error(typeof detail === "string" ? detail : detail?.message ?? "Profile request failed.");
  }
  return (await response.json()) as T;
}

export async function getPrimaryProfile(token: string): Promise<CandidateProfileRecord | null> {
  return requestProfile<CandidateProfileRecord | null>("/api/profiles/primary", token);
}

export async function listProfiles(token: string): Promise<CandidateProfileRecord[]> {
  return requestProfile<CandidateProfileRecord[]>("/api/profiles", token);
}

export async function getProfile(token: string, profileId: string): Promise<CandidateProfileRecord> {
  return requestProfile<CandidateProfileRecord>(`/api/profiles/${profileId}`, token);
}

export async function createProfile(
  token: string,
  profileData: GeneratedResume,
  profileName = "Primary Profile",
): Promise<CandidateProfileRecord> {
  return requestProfile<CandidateProfileRecord>("/api/profiles", token, {
    method: "POST",
    headers: jsonHeaders(token),
    body: JSON.stringify({ profileName, profileData }),
  });
}

export async function updateProfile(
  token: string,
  profileId: string,
  profileData: GeneratedResume,
  expectedProfileVersion?: number,
  profileName = "Primary Profile",
): Promise<CandidateProfileRecord> {
  return requestProfile<CandidateProfileRecord>(`/api/profiles/${profileId}`, token, {
    method: "PUT",
    headers: jsonHeaders(token),
    body: JSON.stringify({ profileName, profileData, expectedProfileVersion }),
  });
}

export async function deleteProfile(token: string, profileId: string): Promise<void> {
  const response = await fetch(`/api/profiles/${profileId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? "Profile delete failed.");
  }
}
