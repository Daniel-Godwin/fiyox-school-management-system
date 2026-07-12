"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { login, ApiError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server");
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* register cover */}
        <div className="bg-ink text-white rounded-t-xl px-6 pt-6 pb-5 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-16 h-16 bg-brass/90 [clip-path:polygon(100%_0,0_0,100%_100%)]" />
          <p className="text-brass text-[11px] tracking-[0.25em] uppercase">
            School register
          </p>
          <h1 className="text-3xl font-semibold mt-1">Fiyox</h1>
          <p className="text-white/70 text-sm mt-1">
            Results · Fees · Attendance
          </p>
        </div>

        {/* ruled page */}
        <form
          onSubmit={onSubmit}
          className="bg-card register-rules rounded-b-xl border border-line border-t-0 px-6 py-7 space-y-5 shadow-sm"
        >
          <div>
            <label htmlFor="email" className="block text-xs font-medium text-ink-soft mb-1">
              Email
            </label>
            <input
              id="email"
              type="email"
              suppressHydrationWarning
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm"
              placeholder="you@school.ng"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-xs font-medium text-ink-soft mb-1">
              Password
            </label>
            <input
              id="password"
              type="password"
              suppressHydrationWarning
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm"
            />
          </div>

          {error && (
            <p role="alert" className="text-sanction text-sm">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-md bg-ink text-white py-2.5 text-sm font-medium hover:bg-ink-soft disabled:opacity-60"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="text-center text-xs text-ink-soft/70 mt-4">
          Your school admin creates accounts. Forgot your password? Ask them to reset it.
        </p>
      </div>
    </main>
  );
}
