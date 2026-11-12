/** Fiyox API client — one place for base URL, token handling, and fetch. */

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type User = {
  id: string;
  email: string;
  role: "super_admin" | "school_admin" | "principal" | "bursar" | "teacher" | "student" | "parent";
  first_name: string;
  last_name: string;
  school_id: string | null;
  phone?: string | null;
  phone_verified?: boolean;
  email_verified?: boolean;
  must_change_password?: boolean;
  last_login_at?: string | null;
  two_factor_enabled?: boolean;
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

export type LoginResult =
  | { twoFactor: false }
  | { twoFactor: true; challenge: string };

/** Login uses OAuth2 form encoding (username = email), per the backend.
 * If the account has 2FA on, no token is set — the caller must collect the
 * emailed code and call verifyTwoFactor with the returned challenge. */
export async function login(email: string, password: string): Promise<LoginResult> {
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
  const data = (await res.json()) as
    | { access_token: string; token_type: string }
    | { two_factor_required: true; challenge: string };
  if ("two_factor_required" in data && data.two_factor_required) {
    return { twoFactor: true, challenge: data.challenge };
  }
  setToken((data as { access_token: string }).access_token);
  return { twoFactor: false };
}

/** Second step of a 2FA login: exchange the emailed code for a token. */
export async function verifyTwoFactor(challenge: string, code: string): Promise<void> {
  const res = await fetch(`${API}/api/auth/login/2fa`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ challenge, code }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: "Verification failed" }));
    throw new ApiError(res.status, data.detail ?? "Verification failed");
  }
  const data = (await res.json()) as { access_token: string };
  setToken(data.access_token);
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

export async function downloadFile(path: string, fallbackName: string): Promise<void> {
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
  // honour the server's filename if it sent one
  const dispo = res.headers.get("content-disposition") ?? "";
  const match = /filename="?([^";]+)"?/.exec(dispo);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = match?.[1] ?? fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export const ROLE_LABEL: Record<User["role"], string> = {
  super_admin: "Platform owner",
  school_admin: "School admin",
  principal: "Principal",
  bursar: "Bursar",
  teacher: "Teacher",
  student: "Student",
  parent: "Parent",
};
