"use client";

import { FormEvent, useState } from "react";
import { api, ApiError, clearToken } from "@/lib/api";
import { useRouter } from "next/navigation";
import FiyoxLoader from "./FiyoxLoader";

/**
 * Hard gate shown across the whole dashboard while a user is still on an
 * admin-issued temporary password. They cannot reach any page until they set
 * their own. On success, `onDone` refreshes the session so the gate lifts.
 */
export default function ForcePasswordChange({ onDone }: { onDone: () => void }) {
  const router = useRouter();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (next.length < 8) { setError("New password must be at least 8 characters."); return; }
    if (next !== confirm) { setError("New passwords do not match."); return; }
    setBusy(true);
    try {
      await api("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change the password.");
    } finally { setBusy(false); }
  }

  function signOut() {
    clearToken();
    router.replace("/login");
  }

  return (
    <div className="mx-auto max-w-md">
      <div className="rounded-xl border border-brass/40 bg-brass/10 p-4 mb-4">
        <p className="text-sm font-medium text-ink">Set your own password to continue</p>
        <p className="text-sm text-ink-soft mt-1">
          Your account is still using the temporary password your school issued.
          For your security, please choose your own password before using Fiyox.
        </p>
      </div>

      <form onSubmit={submit} className="rounded-xl border border-line bg-card p-5 space-y-4 shadow-sm">
        <label className="block">
          <span className="block text-xs text-ink-soft mb-1">Current (temporary) password</span>
          <input type="password" required autoComplete="current-password" value={current}
                 onChange={(e) => setCurrent(e.target.value)}
                 className="w-full rounded border border-line px-3 py-2 text-sm" />
        </label>
        <label className="block">
          <span className="block text-xs text-ink-soft mb-1">New password</span>
          <input type="password" required autoComplete="new-password" value={next}
                 onChange={(e) => setNext(e.target.value)}
                 className="w-full rounded border border-line px-3 py-2 text-sm" />
          <span className="block text-[11px] text-ink-soft/70 mt-1">At least 8 characters.</span>
        </label>
        <label className="block">
          <span className="block text-xs text-ink-soft mb-1">Confirm new password</span>
          <input type="password" required autoComplete="new-password" value={confirm}
                 onChange={(e) => setConfirm(e.target.value)}
                 className="w-full rounded border border-line px-3 py-2 text-sm" />
        </label>
        {error && <p role="alert" className="text-sanction text-sm">{error}</p>}
        <div className="flex items-center justify-between gap-3">
          <button type="submit" disabled={busy}
                  className="rounded-md bg-ink text-white px-4 py-2.5 text-sm font-medium hover:bg-ink-soft disabled:opacity-60 flex items-center gap-2">
            {busy ? (<><FiyoxLoader size={16} tone="dark" /> Saving…</>) : "Set password & continue"}
          </button>
          <button type="button" onClick={signOut}
                  className="text-sm text-ink-soft underline underline-offset-2 hover:text-ink">
            Sign out
          </button>
        </div>
      </form>
    </div>
  );
}
