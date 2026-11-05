"use client";

import { useCallback, useEffect, useState } from "react";
import { discard, flush, isOnline, onSyncChange, pendingOps } from "@/lib/offline/sync";
import type { OutboxOp } from "@/lib/offline/db";

function timeAgo(ts: number): string {
  const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} hr${h === 1 ? "" : "s"} ago`;
  const d = Math.round(h / 24);
  return `${d} day${d === 1 ? "" : "s"} ago`;
}

export default function PendingChangesPage() {
  const [ops, setOps] = useState<OutboxOp[] | null>(null);
  const [online, setOnline] = useState(true);
  const [syncing, setSyncing] = useState(false);

  const refresh = useCallback(() => {
    setOnline(isOnline());
    pendingOps().then(setOps).catch(() => setOps([]));
  }, []);

  useEffect(() => {
    refresh();
    const off = onSyncChange(refresh);
    const on = () => refresh();
    window.addEventListener("online", on);
    window.addEventListener("offline", on);
    const t = setInterval(refresh, 8000);
    return () => { off(); window.removeEventListener("online", on); window.removeEventListener("offline", on); clearInterval(t); };
  }, [refresh]);

  async function syncNow() {
    setSyncing(true);
    try { await flush(); } finally { setSyncing(false); refresh(); }
  }

  const count = ops?.length ?? 0;

  return (
    <div className="space-y-5 max-w-2xl">
      <header>
        <h1 className="text-2xl font-semibold">Pending changes</h1>
        <p className="text-sm text-ink-soft mt-1">
          Work you saved while offline waits here and syncs automatically when
          you&apos;re back online — even if you close the app. You can also sync now.
        </p>
      </header>

      <div className="flex items-center gap-3">
        <span
          className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ${
            online ? "bg-ledger/10 text-ledger" : "bg-brass/15 text-brass-ink"
          }`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${online ? "bg-ledger" : "bg-brass"}`} />
          {online ? "Online" : "Offline"}
        </span>
        {online && count > 0 && (
          <button
            onClick={syncNow}
            disabled={syncing}
            className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50"
          >
            {syncing ? "Syncing…" : `Sync now (${count})`}
          </button>
        )}
      </div>

      {ops === null && <p className="text-sm text-ink-soft">Checking…</p>}

      {ops !== null && count === 0 && (
        <div className="rounded-lg border border-dashed border-line p-8 text-center">
          <p className="text-sm font-medium text-ink">Everything is synced</p>
          <p className="text-sm text-ink-soft mt-1">
            Nothing is waiting. Scores and attendance you enter offline will appear
            here until they reach the server.
          </p>
        </div>
      )}

      {ops !== null && count > 0 && (
        <ul className="rounded-lg border border-line bg-card divide-y divide-line">
          {ops.map((op) => (
            <li key={op.id} className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="text-sm font-medium truncate">{op.label}</p>
                <p className="text-xs text-ink-soft mt-0.5">
                  Queued {timeAgo(op.createdAt)}
                  {op.tries > 0 && ` · ${op.tries} failed attempt${op.tries === 1 ? "" : "s"}`}
                </p>
              </div>
              <button
                onClick={() => discard(op.id)}
                className="shrink-0 rounded-md border border-line px-3 py-1.5 text-xs font-medium text-ink-soft hover:border-sanction hover:text-sanction"
              >
                Discard
              </button>
            </li>
          ))}
        </ul>
      )}

      {count > 0 && (
        <p className="text-xs text-ink-soft">
          Discarding a change removes it permanently — the data will not be saved.
          Only discard a change you entered by mistake.
        </p>
      )}
    </div>
  );
}
