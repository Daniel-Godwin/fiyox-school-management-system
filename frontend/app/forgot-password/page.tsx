"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import FiyoxLoader from "@/components/FiyoxLoader";
import PasswordStrength from "@/components/PasswordStrength";

type Stage = "request" | "reset" | "done";

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("request");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function requestCode(e: FormEvent) {
    e.preventDefault();
    setError(null); setBusy(true);
    try {
      const r = await api<{ sent: boolean; note: string }>("/api/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      });
      setNote(r.note);
      setStage("reset");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server");
    } finally { setBusy(false); }
  }

  async function doReset(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (next.length < 8) { setError("New password must be at least 8 characters."); return; }
    if (next !== confirm) { setError("New passwords do not match."); return; }
    setBusy(true);
    try {
      await api("/api/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({
          email: email.trim().toLowerCase(), code: code.trim(), new_password: next,
        }),
      });
      setStage("done");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reset the password");
    } finally { setBusy(false); }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="bg-ink text-white rounded-t-xl px-6 pt-6 pb-5 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-16 h-16 bg-brass/90 [clip-path:polygon(100%_0,0_0,100%_100%)]" />
          <p className="text-brass text-[11px] tracking-[0.25em] uppercase">Password reset</p>
          <img src="/fiyox-logo-white.png" alt="Fiyox School Management System" className="mt-1" style={{ height: 64, width: "auto" }} />
          <p className="text-white/70 text-sm mt-1">Reset yours by email</p>
        </div>

        <div className="bg-card register-rules rounded-b-xl border border-line border-t-0 px-6 py-7 shadow-sm">
          {stage === "request" && (
            <form onSubmit={requestCode} className="space-y-5">
              <p className="text-sm text-ink-soft">
                Enter your email and we&apos;ll send you a 6-digit reset code.
              </p>
              <div>
                <label htmlFor="email" className="block text-xs font-medium text-ink-soft mb-1">Email</label>
                <input id="email" type="email" required autoComplete="email" autoCapitalize="none"
                       autoCorrect="off" spellCheck={false} inputMode="email"
                       value={email} onChange={(e) => setEmail(e.target.value)}
                       className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm"
                       placeholder="you@school.ng" />
              </div>
              {error && <p role="alert" className="text-sanction text-sm">{error}</p>}
              <button type="submit" disabled={busy}
                      className="w-full rounded-md bg-ink text-white py-2.5 text-sm font-medium hover:bg-ink-soft disabled:opacity-70 flex items-center justify-center gap-2">
                {busy ? (<><FiyoxLoader size={18} tone="dark" /> Sending…</>) : "Send reset code"}
              </button>
            </form>
          )}

          {stage === "reset" && (
            <form onSubmit={doReset} className="space-y-4">
              {note && (
                <p className="text-sm text-ink-soft border border-dashed border-line rounded-md p-3">
                  {note}
                </p>
              )}
              <div>
                <label htmlFor="code" className="block text-xs font-medium text-ink-soft mb-1">6-digit code</label>
                <input id="code" inputMode="numeric" maxLength={6} required value={code}
                       onChange={(e) => setCode(e.target.value)}
                       className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm tracking-widest text-center" />
              </div>
              <div>
                <label htmlFor="new" className="block text-xs font-medium text-ink-soft mb-1">New password</label>
                <input id="new" type="password" required autoComplete="new-password" value={next}
                       onChange={(e) => setNext(e.target.value)}
                       className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm" />
                <PasswordStrength value={next} />
              </div>
              <div>
                <label htmlFor="confirm" className="block text-xs font-medium text-ink-soft mb-1">Confirm new password</label>
                <input id="confirm" type="password" required autoComplete="new-password" value={confirm}
                       onChange={(e) => setConfirm(e.target.value)}
                       className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm" />
              </div>
              {error && <p role="alert" className="text-sanction text-sm">{error}</p>}
              <button type="submit" disabled={busy}
                      className="w-full rounded-md bg-ink text-white py-2.5 text-sm font-medium hover:bg-ink-soft disabled:opacity-70 flex items-center justify-center gap-2">
                {busy ? (<><FiyoxLoader size={18} tone="dark" /> Resetting…</>) : "Set new password"}
              </button>
              <button type="button" onClick={() => { setStage("request"); setError(null); }}
                      className="w-full text-xs text-ink-soft hover:text-ink underline underline-offset-2">
                Use a different email
              </button>
            </form>
          )}

          {stage === "done" && (
            <div className="space-y-5 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-ledger/10">
                <span className="h-2.5 w-2.5 rounded-full bg-ledger" />
              </div>
              <p className="text-sm text-ink">
                Your password has been reset. You can now sign in with your new password.
              </p>
              <button onClick={() => router.replace("/login")}
                      className="w-full rounded-md bg-ink text-white py-2.5 text-sm font-medium hover:bg-ink-soft">
                Back to sign in
              </button>
            </div>
          )}
        </div>

        {stage !== "done" && (
          <p className="text-center text-xs text-ink-soft/70 mt-4">
            Remembered it? <a href="/login" className="underline underline-offset-2 hover:text-ink">Sign in</a>
          </p>
        )}
      </div>
    </main>
  );
}
