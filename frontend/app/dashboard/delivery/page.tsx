"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError, me } from "@/lib/api";
import { Kpi, BRAND as C } from "@/components/Panels";

type ChannelStatus = { provider: string; live: boolean; message: string;
                       sender_id?: string | null; sender?: string | null };
type Status = {
  sms: ChannelStatus;
  email: ChannelStatus;
  online_payments: { live: boolean; message: string };
};
type LogRow = {
  id: string; channel: string; recipient: string; body: string;
  purpose: string; status: "sent" | "failed" | "mock"; provider: string;
  error: string | null; created_at: string;
};

function statusPill(live: boolean) {
  return live
    ? <span className="inline-flex items-center gap-1.5 rounded-full bg-ledger/10 text-ledger px-2.5 py-0.5 text-xs font-medium"><span className="h-1.5 w-1.5 rounded-full bg-ledger" />Live</span>
    : <span className="inline-flex items-center gap-1.5 rounded-full bg-brass/15 text-brass-ink px-2.5 py-0.5 text-xs font-medium"><span className="h-1.5 w-1.5 rounded-full bg-brass" />Preview</span>;
}

function rowBadge(s: LogRow["status"]) {
  const map: Record<LogRow["status"], string> = {
    sent: "bg-ledger/10 text-ledger",
    failed: "bg-sanction/10 text-sanction",
    mock: "bg-brass/15 text-brass-ink",
  };
  const label = { sent: "Delivered", failed: "Failed", mock: "Not sent (preview)" }[s];
  return <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${map[s]}`}>{label}</span>;
}

export default function DeliveryLogPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [rows, setRows] = useState<LogRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [role, setRole] = useState("");
  const [clearOpen, setClearOpen] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    setErr(null);
    api<Status>("/api/notifications/status").then(setStatus).catch(() => {});
    api<LogRow[]>("/api/notifications/logs?limit=200")
      .then(setRows)
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Could not load the delivery log."));
  }, []);

  useEffect(load, [load]);
  useEffect(() => { me().then((u) => setRole(u.role)).catch(() => {}); }, []);

  const isAdmin = role === "school_admin" || role === "super_admin";

  const counts = useMemo(() => {
    const r = rows ?? [];
    return {
      total: r.length,
      sent: r.filter((x) => x.status === "sent").length,
      failed: r.filter((x) => x.status === "failed").length,
      mock: r.filter((x) => x.status === "mock").length,
    };
  }, [rows]);

  async function clearLogs(query: string, label: string) {
    setClearing(true); setNotice(null);
    try {
      const r = await api<{ deleted: number }>(`/api/notifications/logs${query}`, { method: "DELETE" });
      setNotice(`Cleared ${r.deleted} ${label} log entr${r.deleted === 1 ? "y" : "ies"}.`);
      setClearOpen(false);
      load();
    } catch (e) {
      setNotice(e instanceof ApiError ? e.message : "Could not clear the log.");
    } finally { setClearing(false); }
  }

  return (
    <div className="space-y-5 max-w-3xl">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Delivery log</h1>
          <p className="text-sm text-ink-soft mt-1">
            Every SMS and email the system tries to send, and what happened to it.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={load} className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-paper">
            Refresh
          </button>
          {isAdmin && rows && rows.length > 0 && (
            <button onClick={() => { setClearOpen((o) => !o); setNotice(null); }}
                    className="rounded-md border border-sanction/40 text-sanction px-3 py-1.5 text-sm font-medium hover:bg-sanction hover:text-white transition-colors">
              Clear log
            </button>
          )}
        </div>
      </header>

      {clearOpen && (
        <div className="rounded-xl border border-sanction/30 bg-sanction/5 p-4 space-y-3">
          <p className="text-sm font-medium text-ink">Clear the delivery log?</p>
          <p className="text-xs text-ink-soft">
            This permanently removes delivery-log entries. It does <strong>not</strong> touch
            results, fees, students or any school records — only the record of messages sent.
          </p>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => clearLogs("", "")} disabled={clearing}
                    className="rounded-md bg-sanction text-white px-4 py-2 text-sm font-medium hover:opacity-90 disabled:opacity-50">
              {clearing ? "Clearing…" : "Clear everything"}
            </button>
            <button onClick={() => clearLogs("?status=failed", "failed")} disabled={clearing}
                    className="rounded-md border border-line px-4 py-2 text-sm font-medium hover:border-ink disabled:opacity-50">
              Clear failed only
            </button>
            <button onClick={() => clearLogs("?older_than_days=30", "older")} disabled={clearing}
                    className="rounded-md border border-line px-4 py-2 text-sm font-medium hover:border-ink disabled:opacity-50">
              Clear older than 30 days
            </button>
            <button onClick={() => setClearOpen(false)} disabled={clearing}
                    className="ml-auto text-sm text-ink-soft underline underline-offset-2">Cancel</button>
          </div>
        </div>
      )}

      {notice && <p className="text-sm text-ledger">{notice}</p>}

      {rows && rows.length > 0 && (
        <div className="grid grid-cols-3 gap-3 fiyox-rise">
          <Kpi label="Delivered" value={counts.sent.toString()} accent={C.ledger} />
          <Kpi label="Failed" value={counts.failed.toString()} accent={counts.failed > 0 ? C.sanction : C.inkSoft} />
          <Kpi label="Not sent (preview)" value={counts.mock.toString()} accent={C.brass} />
        </div>
      )}

      {status && (
        <div className="grid sm:grid-cols-2 gap-3">
          <div className="rounded-lg border border-line bg-card p-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">Email</p>
              {statusPill(status.email.live)}
            </div>
            <p className="text-xs text-ink-soft mt-1">{status.email.message}</p>
            {status.email.sender && (
              <p className="text-xs text-ink-soft mt-1">Sending as: {status.email.sender}</p>
            )}
          </div>
          <div className="rounded-lg border border-line bg-card p-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">SMS</p>
              {statusPill(status.sms.live)}
            </div>
            <p className="text-xs text-ink-soft mt-1">{status.sms.message}</p>
          </div>
        </div>
      )}

      {err && <p className="text-sm text-sanction">{err}</p>}

      {rows !== null && rows.length === 0 && (
        <div className="rounded-lg border border-dashed border-line p-8 text-center">
          <p className="text-sm font-medium">No messages yet</p>
          <p className="text-sm text-ink-soft mt-1">
            Verification codes, fee reminders and announcements will appear here once sent.
          </p>
        </div>
      )}

      {rows && rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-line bg-card">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-ink text-white text-left">
                <th className="px-3 py-2 font-medium">Time</th>
                <th className="px-3 py-2 font-medium">Channel</th>
                <th className="px-3 py-2 font-medium">Recipient</th>
                <th className="px-3 py-2 font-medium">Result</th>
                <th className="px-3 py-2 font-medium">Detail</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.id} className={i % 2 ? "bg-paper" : "bg-card"}>
                  <td className="px-3 py-2 whitespace-nowrap text-ink-soft">
                    {new Date(r.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2 capitalize">{r.channel}</td>
                  <td className="px-3 py-2 break-all">{r.recipient}</td>
                  <td className="px-3 py-2">{rowBadge(r.status)}</td>
                  <td className="px-3 py-2 text-ink-soft">
                    {r.status === "failed" && r.error
                      ? <span className="text-sanction">{r.error}</span>
                      : r.purpose.replace("_", " ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
