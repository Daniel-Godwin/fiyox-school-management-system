"use client";

import { useCallback, useEffect, useState } from "react";
import { api, openPdf, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";

type Session = { id: string; name: string; is_current: boolean };
type Arm = { id: string; label: string };
type Row = {
  student_id: string; name: string; admission_number: string;
  per_term: (number | null)[]; cumulative_average: number | null;
  terms_counted: number; position: number; computed: boolean;
};
type Broadsheet = {
  session: string; class: string; terms: string[];
  terms_in_session: number; class_size: number; rows: Row[];
};

const pct = (v: number | null) => (v === null || v === undefined ? "—" : `${v}%`);

export default function AnnualReportsPage() {
  const { err } = useToast();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [arms, setArms] = useState<Arm[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [armId, setArmId] = useState("");
  const [data, setData] = useState<Broadsheet | null>(null);
  const [busy, setBusy] = useState(false);
  const [pdfBusy, setPdfBusy] = useState<string | null>(null);

  useEffect(() => {
    api<Session[]>("/api/academics/sessions").then((s) => {
      setSessions(s);
      const cur = s.find((x) => x.is_current) ?? s[0];
      if (cur) setSessionId(cur.id);
    }).catch(() => {});
    api<Arm[]>("/api/academics/arms").then(setArms).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    if (!sessionId || !armId) return;
    setBusy(true); setData(null);
    try {
      const r = await api<Broadsheet>(`/api/results/annual?arm_id=${armId}&session_id=${sessionId}`);
      setData(r);
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not load the broadsheet"); }
    setBusy(false);
  }, [sessionId, armId, err]);

  async function openAnnual(r: Row) {
    setPdfBusy(r.student_id);
    try { await openPdf(`/api/results/annual/${r.student_id}/pdf?session_id=${sessionId}`); }
    catch (e) { err(e instanceof ApiError ? e.message : "Could not open the report"); }
    setPdfBusy(null);
  }

  return (
    <div className="max-w-4xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Annual reports</h1>
        <p className="text-ink-soft text-sm mt-1">
          The cumulative end-of-session result — each term combined into one annual average, grade and position.
        </p>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <label className="block">
          <span className="block text-xs font-medium text-ink-soft mb-1">Session</span>
          <select value={sessionId} onChange={(e) => { setSessionId(e.target.value); setData(null); }}
                  className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm">
            <option value="">Select session…</option>
            {sessions.map((s) => <option key={s.id} value={s.id}>{s.name}{s.is_current ? " (current)" : ""}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="block text-xs font-medium text-ink-soft mb-1">Class</span>
          <select value={armId} onChange={(e) => { setArmId(e.target.value); setData(null); }}
                  className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm">
            <option value="">Select class…</option>
            {arms.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
          </select>
        </label>
        <div className="flex items-end">
          <button onClick={load} disabled={!sessionId || !armId || busy}
                  className="rounded-md bg-ink text-white px-5 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
            {busy ? "Loading…" : "Load broadsheet"}
          </button>
        </div>
      </div>

      {!data && !busy && (
        <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-6">
          Pick a session and class to see the cumulative standings.
        </p>
      )}

      {data && (
        <>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-semibold">{data.class} · {data.session}</h2>
            <p className="text-sm text-ink-soft">{data.class_size} students · {data.terms.join(" / ")}</p>
          </div>

          {data.rows.length === 0 ? (
            <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-6">No students in this class.</p>
          ) : (
            <>
              {/* phone: a card per student */}
              <div className="md:hidden space-y-2">
                {data.rows.map((r) => (
                  <div key={r.student_id} className="rounded-xl border border-line bg-card p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-medium truncate">
                          {r.computed && <span className="tabular text-ink-soft mr-1">{r.position}.</span>}{r.name}
                        </p>
                        <p className="text-xs text-ink-soft tabular">{r.admission_number}</p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="tabular font-semibold">{pct(r.cumulative_average)}</p>
                        <p className="text-xs text-ink-soft">{r.computed ? `${r.position} of ${data.class_size}` : "—"}</p>
                      </div>
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <p className="text-xs text-ink-soft tabular">
                        {data.terms.map((t, i) => `${t[0]}: ${pct(r.per_term[i])}`).join("  ·  ")}
                      </p>
                      {r.computed && (
                        <button onClick={() => openAnnual(r)} disabled={pdfBusy === r.student_id}
                                className="shrink-0 rounded-md border border-ink text-ink px-3 py-1 text-xs font-medium hover:bg-ink hover:text-white disabled:opacity-50">
                          {pdfBusy === r.student_id ? "Opening…" : "Annual PDF"}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* desktop: the broadsheet */}
              <div className="hidden md:block overflow-x-auto rounded-lg border border-line bg-card">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-ink text-white text-left">
                      <th className="px-3 py-2 font-medium">Pos.</th>
                      <th className="px-3 py-2 font-medium">Student</th>
                      {data.terms.map((t) => <th key={t} className="px-3 py-2 font-medium text-right">{t}</th>)}
                      <th className="px-3 py-2 font-medium text-right">Cumulative</th>
                      <th className="px-3 py-2 font-medium text-right">Report</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((r, i) => (
                      <tr key={r.student_id} className={i % 2 ? "bg-paper/60" : ""}>
                        <td className="px-3 py-2 tabular">{r.computed ? `${r.position}` : "—"}</td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          <span className="tabular text-ink-soft mr-2">{r.admission_number}</span>{r.name}
                        </td>
                        {r.per_term.map((v, j) => <td key={j} className="px-3 py-2 text-right tabular text-ink-soft">{pct(v)}</td>)}
                        <td className="px-3 py-2 text-right tabular font-semibold">{pct(r.cumulative_average)}</td>
                        <td className="px-3 py-2 text-right">
                          {r.computed ? (
                            <button onClick={() => openAnnual(r)} disabled={pdfBusy === r.student_id}
                                    className="text-ink underline underline-offset-2 hover:text-ink-soft disabled:opacity-50">
                              {pdfBusy === r.student_id ? "Opening…" : "Annual PDF"}
                            </button>
                          ) : <span className="text-ink-soft text-xs">no result</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
