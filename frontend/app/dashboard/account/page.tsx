"use client";

import { useEffect, useState } from "react";
import { api, me, ApiError, User, ROLE_LABEL } from "@/lib/api";
import PasswordStrength from "@/components/PasswordStrength";

type Availability = { phone: boolean; email: boolean; online_payments: boolean };

export default function AccountPage() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  // --- email verification ---
  const [user, setUser] = useState<User | null>(null);
  const [avail, setAvail] = useState<Availability | null>(null);
  const [codeSent, setCodeSent] = useState(false);
  const [code, setCode] = useState("");
  const [vBusy, setVBusy] = useState(false);
  const [vNotice, setVNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  useEffect(() => {
    me().then(setUser).catch(() => {});
    api<Availability>("/api/verify/availability").then(setAvail).catch(() => {});
  }, []);

  // --- two-factor ---
  const [tfaBusy, setTfaBusy] = useState(false);
  const [tfaNotice, setTfaNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  async function toggleTwoFactor(enable: boolean) {
    setTfaBusy(true); setTfaNotice(null);
    try {
      await api(`/api/auth/2fa/${enable ? "enable" : "disable"}`, { method: "POST" });
      setUser((u) => (u ? { ...u, two_factor_enabled: enable } : u));
      setTfaNotice({
        kind: "ok",
        text: enable
          ? "Two-factor sign-in is on. You'll enter an emailed code at each login."
          : "Two-factor sign-in is off.",
      });
    } catch (e) {
      setTfaNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not update two-factor." });
    } finally { setTfaBusy(false); }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (next.length < 8) {
      setNotice({ kind: "err", text: "New password must be at least 8 characters." });
      return;
    }
    if (next !== confirm) {
      setNotice({ kind: "err", text: "New passwords do not match." });
      return;
    }
    setSaving(true); setNotice(null);
    try {
      await api("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      setNotice({ kind: "ok", text: "Password changed. Use it the next time you sign in." });
      setCurrent(""); setNext(""); setConfirm("");
    } catch (e) {
      setNotice({
        kind: "err",
        text: e instanceof ApiError ? e.message : "Could not change the password.",
      });
    } finally { setSaving(false); }
  }

  async function sendCode() {
    setVBusy(true); setVNotice(null);
    try {
      const r = await api<{ sent: boolean; note: string }>("/api/verify/request", {
        method: "POST", body: JSON.stringify({ channel: "email" }),
      });
      setCodeSent(r.sent);
      setVNotice({ kind: r.sent ? "ok" : "err", text: r.note });
    } catch (e) {
      setVNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not send the code." });
    } finally { setVBusy(false); }
  }

  async function confirmCode() {
    if (!code.trim()) return;
    setVBusy(true); setVNotice(null);
    try {
      await api("/api/verify/confirm", {
        method: "POST", body: JSON.stringify({ channel: "email", code: code.trim() }),
      });
      setVNotice({ kind: "ok", text: "Email verified. Thank you." });
      setCodeSent(false); setCode("");
      setUser((u) => (u ? { ...u, email_verified: true } : u));
    } catch (e) {
      setVNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not verify the code." });
    } finally { setVBusy(false); }
  }

  return (
    <div className="space-y-5 max-w-md">
      <header>
        <h1 className="text-2xl font-semibold">Account</h1>
        <p className="text-sm text-ink-soft mt-1">
          Verify your email and change your password.
        </p>
      </header>

      {/* ---- profile header ---- */}
      {user && (
        <div className="rounded-xl bg-ink text-white p-5 flex items-center gap-4 relative overflow-hidden fiyox-rise">
          <div className="absolute top-0 right-0 w-20 h-20 bg-brass/80 [clip-path:polygon(100%_0,0_0,100%_100%)]" />
          <div className="grid h-14 w-14 shrink-0 place-items-center rounded-full bg-brass text-ink text-xl font-bold">
            {(user.first_name?.[0] ?? "") + (user.last_name?.[0] ?? "")}
          </div>
          <div className="min-w-0">
            <p className="text-lg font-semibold truncate">{user.first_name} {user.last_name}</p>
            <p className="text-sm text-white/70 truncate">{user.email}</p>
            <span className="inline-block mt-1 rounded-full bg-white/10 px-2.5 py-0.5 text-xs text-brass">
              {ROLE_LABEL[user.role] ?? user.role}
            </span>
            {user.last_login_at && (
              <p className="text-[11px] text-white/50 mt-1.5">
                Last signed in: {new Date(user.last_login_at).toLocaleString()}
              </p>
            )}
          </div>
        </div>
      )}

      {/* ---- email verification ---- */}
      {user && (
        <section className="rounded-lg border border-line bg-card p-4 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-medium">Email address</p>
              <p className="text-sm text-ink-soft break-all">{user.email}</p>
            </div>
            {user.email_verified ? (
              <span className="shrink-0 inline-flex items-center gap-1.5 rounded-full bg-ledger/10 text-ledger px-3 py-1 text-xs font-medium">
                <span className="h-1.5 w-1.5 rounded-full bg-ledger" /> Verified
              </span>
            ) : (
              <span className="shrink-0 inline-flex items-center gap-1.5 rounded-full bg-brass/15 text-brass-ink px-3 py-1 text-xs font-medium">
                <span className="h-1.5 w-1.5 rounded-full bg-brass" /> Not verified
              </span>
            )}
          </div>

          {!user.email_verified && avail && !avail.email && (
            <p className="text-xs text-ink-soft border border-dashed border-line rounded-md p-3">
              Email verification isn&apos;t switched on yet. It becomes available once
              your school connects an email service. If this address is wrong, ask
              your school admin to correct it.
            </p>
          )}

          {!user.email_verified && avail && avail.email && (
            <div className="space-y-3">
              {!codeSent ? (
                <button onClick={sendCode} disabled={vBusy}
                        className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
                  {vBusy ? "Sending…" : "Send verification code"}
                </button>
              ) : (
                <div className="flex flex-wrap items-end gap-2">
                  <label className="block">
                    <span className="block text-xs text-ink-soft mb-1">6-digit code from your email</span>
                    <input inputMode="numeric" value={code} maxLength={6}
                           onChange={(e) => setCode(e.target.value)}
                           className="w-32 rounded border border-line px-3 py-2 text-sm tracking-widest text-center" />
                  </label>
                  <button onClick={confirmCode} disabled={vBusy || !code.trim()}
                          className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
                    {vBusy ? "Checking…" : "Verify"}
                  </button>
                  <button onClick={sendCode} disabled={vBusy}
                          className="text-sm text-ink-soft underline underline-offset-2">
                    Resend
                  </button>
                </div>
              )}
            </div>
          )}

          {vNotice && (
            <p role="status" className={`text-sm ${vNotice.kind === "ok" ? "text-ledger" : "text-sanction"}`}>
              {vNotice.text}
            </p>
          )}
        </section>
      )}

      {/* ---- two-factor authentication ---- */}
      {user && user.role !== "super_admin" && (
        <section className="rounded-lg border border-line bg-card p-4 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-medium">Two-factor sign-in</p>
              <p className="text-sm text-ink-soft mt-0.5">
                Adds a one-time code, emailed at each login, on top of your password.
              </p>
            </div>
            {user.two_factor_enabled ? (
              <span className="shrink-0 inline-flex items-center gap-1.5 rounded-full bg-ledger/10 text-ledger px-3 py-1 text-xs font-medium">
                <span className="h-1.5 w-1.5 rounded-full bg-ledger" /> On
              </span>
            ) : (
              <span className="shrink-0 inline-flex items-center gap-1.5 rounded-full bg-line text-ink-soft px-3 py-1 text-xs font-medium">
                <span className="h-1.5 w-1.5 rounded-full bg-ink-soft/50" /> Off
              </span>
            )}
          </div>

          {!user.email_verified ? (
            <p className="text-xs text-ink-soft border border-dashed border-line rounded-md p-3">
              Verify your email above first — two-factor codes are sent there.
            </p>
          ) : user.two_factor_enabled ? (
            <button onClick={() => toggleTwoFactor(false)} disabled={tfaBusy}
                    className="rounded-md border border-line px-4 py-2 text-sm font-medium hover:bg-paper disabled:opacity-50">
              {tfaBusy ? "Saving…" : "Turn off"}
            </button>
          ) : (
            <button onClick={() => toggleTwoFactor(true)} disabled={tfaBusy}
                    className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
              {tfaBusy ? "Saving…" : "Turn on two-factor"}
            </button>
          )}

          {tfaNotice && (
            <p role="status" className={`text-sm ${tfaNotice.kind === "ok" ? "text-ledger" : "text-sanction"}`}>
              {tfaNotice.text}
            </p>
          )}
        </section>
      )}

      {/* ---- change password ---- */}
      <form onSubmit={submit} className="rounded-lg border border-line bg-card p-4 space-y-3">
        <p className="text-sm font-medium">Change password</p>
        <label className="block">
          <span className="block text-xs text-ink-soft mb-1">Current password</span>
          <input type="password" required value={current} autoComplete="current-password"
                 onChange={(e) => setCurrent(e.target.value)}
                 className="w-full rounded border border-line px-3 py-2 text-sm" />
        </label>
        <label className="block">
          <span className="block text-xs text-ink-soft mb-1">New password</span>
          <input type="password" required value={next} autoComplete="new-password"
                 onChange={(e) => setNext(e.target.value)}
                 className="w-full rounded border border-line px-3 py-2 text-sm" />
          <PasswordStrength value={next} />
        </label>
        <label className="block">
          <span className="block text-xs text-ink-soft mb-1">Confirm new password</span>
          <input type="password" required value={confirm} autoComplete="new-password"
                 onChange={(e) => setConfirm(e.target.value)}
                 className="w-full rounded border border-line px-3 py-2 text-sm" />
        </label>
        <div className="flex items-center gap-3">
          <button type="submit" disabled={saving}
                  className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
            {saving ? "Saving…" : "Change password"}
          </button>
          {notice && (
            <span role="status"
                  className={`text-sm ${notice.kind === "ok" ? "text-ledger" : "text-sanction"}`}>
              {notice.text}
            </span>
          )}
        </div>
      </form>
    </div>
  );
}
