"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { login, verifyTwoFactor, ApiError } from "@/lib/api";
import FiyoxLoader from "@/components/FiyoxLoader";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // second factor
  const [challenge, setChallenge] = useState<string | null>(null);
  const [code, setCode] = useState("");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = await login(email.trim().toLowerCase(), password);
      if (r.twoFactor) {
        setChallenge(r.challenge);
        setBusy(false);
        return;
      }
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server");
      setBusy(false);
    }
  }

  async function onVerify(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await verifyTwoFactor(challenge!, code.trim());
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
          <img src="/fiyox-logo-white.png" alt="Fiyox School Management System" className="mt-1" style={{ height: 64, width: "auto" }} />
          <p className="text-white/70 text-sm mt-1">
            Results · Fees · Attendance
          </p>
        </div>

        {/* ruled page */}
        {challenge ? (
          <form
            onSubmit={onVerify}
            className="bg-card register-rules rounded-b-xl border border-line border-t-0 px-6 py-7 space-y-5 shadow-sm"
          >
            <p className="text-sm text-ink-soft">
              We emailed a 6-digit sign-in code to{" "}
              <span className="font-medium text-ink break-all">{email}</span>.
              Enter it to finish signing in.
            </p>
            <div>
              <label htmlFor="code" className="block text-xs font-medium text-ink-soft mb-1">
                Sign-in code
              </label>
              <input id="code" inputMode="numeric" maxLength={6} required
                     value={code} onChange={(e) => setCode(e.target.value)}
                     className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm tracking-widest text-center" />
            </div>
            {error && <p role="alert" className="text-sanction text-sm">{error}</p>}
            <button type="submit" disabled={busy}
                    className="w-full rounded-md bg-ink text-white py-2.5 text-sm font-medium hover:bg-ink-soft disabled:opacity-70 flex items-center justify-center gap-2">
              {busy ? (<><FiyoxLoader size={18} tone="dark" /> Verifying…</>) : "Verify & sign in"}
            </button>
            <button type="button"
                    onClick={() => { setChallenge(null); setCode(""); setError(null); }}
                    className="w-full text-xs text-ink-soft hover:text-ink underline underline-offset-2">
              Back
            </button>
          </form>
        ) : (
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
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              inputMode="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm"
              placeholder="you@school.ng"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label htmlFor="password" className="block text-xs font-medium text-ink-soft">
                Password
              </label>
              <button
                type="button"
                onClick={() => setShowPassword((s) => !s)}
                className="text-[11px] text-ink-soft/80 hover:text-ink"
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              suppressHydrationWarning
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm"
            />
            <div className="mt-1.5 text-right">
              <a href="/forgot-password" className="text-xs text-ink-soft hover:text-ink underline underline-offset-2">
                Forgot password?
              </a>
            </div>
          </div>

          {error && (
            <p role="alert" className="text-sanction text-sm">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-md bg-ink text-white py-2.5 text-sm font-medium hover:bg-ink-soft disabled:opacity-70 flex items-center justify-center gap-2 transition-colors"
          >
            {busy ? (<><FiyoxLoader size={18} tone="dark" /> Signing in…</>) : "Sign in"}
          </button>
        </form>
        )}

        {!challenge && (
          <p className="text-center text-xs text-ink-soft/70 mt-4">
            Your school admin creates accounts. Use “Forgot password?” to reset yours by email.
          </p>
        )}
      </div>
    </main>
  );
}
