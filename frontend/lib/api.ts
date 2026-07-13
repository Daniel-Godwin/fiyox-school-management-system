/** Fiyox API client — one place for base URL, token handling, and fetch. */

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type User = {
  id: string;
  email: string;
  role: "super_admin" | "school_admin" | "bursar" | "teacher" | "student" | "parent";
  first_name: string;
  last_name: string;
  school_id: string | null;
};

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("fiyox_token");
}

export function setToken(token: string) {
  localStorage.setItem("fiyox_token", token);
}

export function clearToken() {
  localStorage.removeItem("fiyox_token");
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Authenticated JSON fetch. Throws ApiError with the API's detail message. */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type") && !(init.body instanceof FormData)) {
    // FormData must set its own multipart boundary — never override it
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${API}${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

/** Login uses OAuth2 form encoding (username = email), per the backend. */
export async function login(email: string, password: string): Promise<string> {
  const body = new URLSearchParams({ username: email, password });
  const res = await fetch(`${API}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: "Login failed" }));
    throw new ApiError(res.status, data.detail ?? "Login failed");
  }
  const data = (await res.json()) as { access_token: string };
  setToken(data.access_token);
  return data.access_token;
}

export function me(): Promise<User> {
  return api<User>("/api/auth/me");
}

/** Fetch a binary (e.g. a report-card PDF) with the auth token and open it. */
export async function openPdf(path: string): Promise<void> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${API}${path}`, { headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : detail;
    } catch { /* non-JSON */ }
    throw new ApiError(res.status, detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export const ROLE_LABEL: Record<User["role"], string> = {
  super_admin: "Platform owner",
  school_admin: "School admin",
  bursar: "Bursar",
  teacher: "Teacher",
  student: "Student",
  parent: "Parent",
};
