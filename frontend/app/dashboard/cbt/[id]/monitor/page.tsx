"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";

type Row = {
  student_id: string; name: string; attempt_id: string | null;
  status: "not_started" | "in_progress" | "submitted";
  answered: number; total: number; remaining: number | null;
  violations: number; flagged: boolean;
};
type Monitor = {
  exam: { id: string; title: string; duration_minutes: number; proctored: boolean };
  server_now: string;
  counts: { total: number; in_progress: number; submitted: number; not_started: number; flagged: number };
  students: Row[];
};

function clock(sec: number | null) {
  if (sec === null) return "—";
  const m = Math.floor(sec / 60), s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

const STATUS: Record<string, { label: string; cls: string }> = {
  not_started: { label: "Not started", cls: "bg-line text-ink-soft" },
  in_progress: { label: "In progress", cls: "bg-brass/15 text-brass-ink" },
  submitted: { label: "Submitted", cls: "bg-ledger/10 text-ledger" },
};

export default function ProctorMonitor() {
  const { id } = useParams<{ id: string }>();
  const { ok, err } = useToast();
  const [mon, setMon] = useState<Monitor | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      setMon(await api<Monitor>(`/api/cbt/exams/${id}/monitor`));
    } catch (e) {
      setFatal(e instanceof ApiError ? e.message : "Could not load the monitor.");
      if (timer.current) clearInterval(timer.current);
    }
  }, [id]);

  useEffect(() => {
    load();
    timer.current = setInterval(load, 4000);   // poll (one-way, low-frequency → SSE-ready)
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [load]);

  async function extend(attemptId: string) {
    setBusy(attemptId);
    try {
      await api(`/api/cbt/attempts/${attemptId}/extend`, {
        method: "POST", body: JSON.stringify({ minutes: 5 }) });
      ok("Added 5 minutes");
      await load();
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not extend time"); }
    finally { setBusy(null); }
  }

  async function forceSubmit(attemptId: string, name: string) {
    if (!confirm(`End ${name}'s test now and grade what they have?`)) return;
    setBusy(attemptId);
    try {
      await api(`/api/cbt/attempts/${attemptId}/force-submit`, { method: "POST" });
      ok(`${name}'s test was submitted`);
      await load();
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not submit"); }
    finally { setBusy(null); }
  }

  if (fatal) {
    return (
      <div className="max-w-xl space-y-4">
        <p className="text-sm text-sanction border border-sanction/30 bg-sanction/5 rounded-lg p-4">{fatal}</p>
        <Link href="/dashboard/cbt" className="text-sm text-ink font-medium hover:underline">← Back to tests</Link>
      </div>
    );
  }
  if (!mon) return <div className="grid place-items-center py-20 text-ink-soft text-sm"><span className="spinner" /> Loading…</div>;

  const stat = (n: number, l: string, c: string) => (
    <div className="rounded-lg border border-line bg-card px-4 py-3 text-center">
      <div className="text-2xl font-bold" style={{ color: c }}>{n}</div>
      <div className="text-xs text-ink-soft">{l}</div>
    </div>
  );

  return (
    <div className="max-w-4xl space-y-5">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{mon.exam.title}</h1>
          <p className="text-ink-soft text-sm mt-1">
            Live monitor · refreshes automatically
            {mon.exam.proctored && <span className="text-sanction"> · proctored</span>}
          </p>
        </div>
        <Link href={`/dashboard/cbt/${id}/results`}
              className="shrink-0 rounded-md border border-line px-4 py-2 text-sm font-medium hover:border-ink">
          Results
        </Link>
      </header>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {stat(mon.counts.total, "Students", "#0b1f3a")}
        {stat(mon.counts.in_progress, "In progress", "#c8a24b")}
        {stat(mon.counts.submitted, "Submitted", "#1e7a4f")}
        {stat(mon.counts.not_started, "Not started", "#274264")}
        {stat(mon.counts.flagged, "Flagged", "#b4232a")}
      </div>

      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full text-sm">
          <thead className="bg-paper text-ink-soft text-left">
            <tr>
              <th className="px-3 py-2 font-medium">Student</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium text-right">Progress</th>
              <th className="px-3 py-2 font-medium text-right">Time left</th>
              <th className="px-3 py-2 font-medium text-right">Flags</th>
              <th className="px-3 py-2 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {mon.students.map((r) => (
              <tr key={r.student_id}
                  className={`border-t border-line ${r.flagged ? "bg-sanction/5" : ""}`}>
                <td className="px-3 py-2 font-medium">{r.name}</td>
                <td className="px-3 py-2">
                  <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS[r.status].cls}`}>
                    {STATUS[r.status].label}
                  </span>
                </td>
                <td className="px-3 py-2 text-right tabular">
                  {r.status === "not_started" ? "—" : `${r.answered}/${r.total}`}
                </td>
                <td className={`px-3 py-2 text-right tabular ${r.remaining !== null && r.remaining <= 60 ? "text-sanction font-semibold" : ""}`}>
                  {clock(r.remaining)}
                </td>
                <td className="px-3 py-2 text-right">
                  {r.violations > 0
                    ? <span className="text-sanction font-semibold">{r.violations}</span>
                    : <span className="text-ink-soft">0</span>}
                </td>
                <td className="px-3 py-2 text-right whitespace-nowrap">
                  {r.status === "in_progress" && r.attempt_id ? (
                    <>
                      <button onClick={() => extend(r.attempt_id!)} disabled={busy === r.attempt_id}
                              className="text-ink underline underline-offset-2 text-xs mr-3 disabled:opacity-50">
                        +5 min
                      </button>
                      <button onClick={() => forceSubmit(r.attempt_id!, r.name)} disabled={busy === r.attempt_id}
                              className="text-sanction underline underline-offset-2 text-xs disabled:opacity-50">
                        Submit now
                      </button>
                    </>
                  ) : <span className="text-ink-soft text-xs">—</span>}
                </td>
              </tr>
            ))}
            {mon.students.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-ink-soft">No students in this class.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
