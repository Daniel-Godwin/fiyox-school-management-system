"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";

export default function AccountPage() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (next.length < 6) {
      setNotice({ kind: "err", text: "New password must be at least 6 characters." });
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

  return (
    <div className="space-y-5 max-w-md">
      <header>
        <h1 className="text-2xl font-semibold">Account</h1>
        <p className="text-sm text-ink-soft mt-1">
          Change your password — do this after your first sign-in with a temporary password.
        </p>
      </header>

      <form onSubmit={submit} className="rounded-lg border border-line bg-card p-4 space-y-3">
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
