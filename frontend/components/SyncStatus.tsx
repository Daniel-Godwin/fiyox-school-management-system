"use client";

import { useCallback, useEffect, useState } from "react";
import { flush, isOnline, onSyncChange, pendingCount } from "@/lib/offline/sync";

/** A small chip showing offline state and any unsynced changes, with a manual sync. */
export default function SyncStatus() {
  const [online, setOnline] = useState(true);
  const [pending, setPending] = useState(0);
  const [syncing, setSyncing] = useState(false);

  const refresh = useCallback(() => {
    setOnline(isOnline());
    pendingCount().then(setPending).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const off = onSyncChange(refresh);
    const on = () => refresh();
    window.addEventListener("online", on);
    window.addEventListener("offline", on);
    // try to clear anything left from a previous session
    void flush().finally(refresh);
    const t = setInterval(refresh, 8000);
    return () => { off(); window.removeEventListener("online", on); window.removeEventListener("offline", on); clearInterval(t); };
  }, [refresh]);

  async function syncNow() {
    setSyncing(true);
    try { await flush(); } finally { setSyncing(false); refresh(); }
  }

  // nothing to show when online and everything is synced
  if (online && pending === 0) return null;

  if (!online) {
    return (
      <div className="flex items-center gap-2 rounded-full bg-brass/15 text-brass-ink px-3 py-1 text-xs font-medium">
        <span className="h-1.5 w-1.5 rounded-full bg-brass" />
        Offline{pending > 0 ? ` · ${pending} to sync` : ""}
      </div>
    );
  }
  return (
    <button onClick={syncNow} disabled={syncing}
            className="flex items-center gap-2 rounded-full border border-brass/40 bg-brass/10 text-brass-ink px-3 py-1 text-xs font-medium hover:bg-brass/20 disabled:opacity-60">
      <span className="h-1.5 w-1.5 rounded-full bg-brass animate-pulse" />
      {syncing ? "Syncing…" : `${pending} unsynced · Sync now`}
    </button>
  );
}
