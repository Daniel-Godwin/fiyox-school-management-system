"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "@/lib/api";
import { cachedGet, queuedPost, putCache } from "@/lib/offline/offlineApi";
import { BRAND as C } from "@/components/Panels";

type Arm = { id: string; label: string };
type Student = {
  id: string; admission_number: string; first_name: string; last_name: string;
  current_arm_id: string | null;
};
type RegisterRow = { student_id: string; status: Status };
type Status = "present" | "absent" | "late" | "excused";

const STATUSES: { value: Status; label: string; on: string }[] = [
  { value: "present", label: "Present", on: "bg-ledger text-white border-ledger" },
  { value: "absent",  label: "Absent",  on: "bg-sanction text-white border-sanction" },
  { value: "late",    label: "Late",    on: "bg-brass text-ink border-brass" },
  { value: "excused", label: "Excused", on: "bg-ink text-white border-ink" },
];

const today = () => new Date().toISOString().slice(0, 10);

export default function AttendancePage() {
  const [arms, setArms] = useState<Arm[]>([]);
  const [armId, setArmId] = useState("");
  const [date, setDate] = useState(today());
  const [students, setStudents] = useState<Student[]>([]);
  const [marks, setMarks] = useState<Record<string, Status>>({});
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  useEffect(() => {
    cachedGet<Arm[]>("/api/academics/arms")
      .then((a) => setArms(a.data))
      .catch(() => setNotice({ kind: "err", text: "Could not load classes. Open this page once while online so it can be used offline later." }));
  }, []);

  const load = useCallback(async () => {
    if (!armId || !date) return;
    setNotice(null);
    const registerPath = `/api/attendance/register?arm_id=${armId}&date=${date}`;
    try {
      const [all, register] = await Promise.all([
        cachedGet<Student[]>("/api/students"),
        cachedGet<RegisterRow[]>(registerPath),
      ]);
      setStudents(
        all.data.filter((s) => s.current_arm_id === armId)
           .sort((a, b) => a.admission_number.localeCompare(b.admission_number)),
      );
      setMarks(Object.fromEntries(register.data.map((r) => [r.student_id, r.status])));
      if (all.stale || register.stale) {
        setNotice({ kind: "ok", text: "You're offline — showing the last saved copy. Marks you take will sync automatically." });
      }
    } catch {
      setNotice({ kind: "err", text: "Could not load the register. Open it once while online to use it offline." });
    }
  }, [armId, date]);

  useEffect(() => { load(); }, [load]);

  function allPresent() {
    setMarks(Object.fromEntries(students.map((s) => [s.id, "present" as Status])));
  }

  async function save() {
    const records = students
      .filter((s) => marks[s.id])
      .map((s) => ({ student_id: s.id, status: marks[s.id] }));
    if (records.length === 0) {
      setNotice({ kind: "err", text: "Mark at least one student first." });
      return;
    }
    setSaving(true); setNotice(null);
    try {
      const label = `Attendance — ${arms.find((a) => a.id === armId)?.label ?? "class"}, ${date}`;
      const r = await queuedPost<{ created: number; updated: number; unchanged: number }>(
        "/api/attendance/mark",
        { arm_id: armId, date, records },
        label,
      );
      if (r.queued) {
        // keep the marks in the offline cache so reopening this day shows them
        void putCache(
          `/api/attendance/register?arm_id=${armId}&date=${date}`,
          records.map((rec) => ({ student_id: rec.student_id, status: rec.status })),
        );
        setNotice({ kind: "ok", text: "Saved on this device — it will sync automatically when you're back online." });
      } else {
        const res = r.result ?? { created: 0, updated: 0, unchanged: 0 };
        const parts = [];
        if (res.created) parts.push(`${res.created} marked`);
        if (res.updated) parts.push(`${res.updated} corrected`);
        if (res.unchanged) parts.push(`${res.unchanged} unchanged`);
        setNotice({ kind: "ok", text: `Register saved — ${parts.join(", ")}.` });
      }
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Save failed. Check your connection and try again." });
    } finally { setSaving(false); }
  }

  const marked = Object.keys(marks).length;

  const summary = useMemo(() => {
    const c: Record<Status, number> = { present: 0, absent: 0, late: 0, excused: 0 };
    students.forEach((s) => { const m = marks[s.id]; if (m) c[m] += 1; });
    const total = students.length || 1;
    const seen = c.present + c.absent + c.late + c.excused;
    return {
      ...c, seen,
      rate: seen ? Math.round((c.present / seen) * 100) : 0,
      segs: [
        { key: "present", color: C.ledger, pct: (c.present / total) * 100 },
        { key: "late", color: C.brass, pct: (c.late / total) * 100 },
        { key: "excused", color: C.ink, pct: (c.excused / total) * 100 },
        { key: "absent", color: C.sanction, pct: (c.absent / total) * 100 },
      ],
    };
  }, [students, marks]);

  const chips: { label: string; key: Status; color: string }[] = [
    { label: "Present", key: "present", color: C.ledger },
    { label: "Absent", key: "absent", color: C.sanction },
    { label: "Late", key: "late", color: C.brass },
    { label: "Excused", key: "excused", color: C.ink },
  ];

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">Attendance</h1>
        <p className="text-sm text-ink-soft mt-1">
          Take the daily register. Re-saving a day corrects it — every correction
          is recorded in the audit trail.
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="block text-xs font-medium text-ink-soft mb-1">Class</span>
          <select value={armId} onChange={(e) => setArmId(e.target.value)}
                  className="rounded-md border border-line bg-white px-3 py-2 text-sm">
            <option value="">Select class…</option>
            {arms.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="block text-xs font-medium text-ink-soft mb-1">Date</span>
          <input type="date" value={date} max={today()}
                 onChange={(e) => setDate(e.target.value)}
                 className="rounded-md border border-line bg-white px-3 py-2 text-sm" />
        </label>
        {students.length > 0 && (
          <button onClick={allPresent}
                  className="rounded-md border border-ink text-ink px-4 py-2 text-sm font-medium hover:bg-ink hover:text-white">
            Mark all present
          </button>
        )}
        {notice && (
          <span role="status"
                className={`text-sm ${notice.kind === "ok" ? "text-ledger" : "text-sanction"}`}>
            {notice.text}
          </span>
        )}
      </div>

      {!armId && (
        <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-6 max-w-xl">
          The register appears once a class is selected.
        </p>
      )}

      {armId && students.length === 0 && (
        <p className="text-sm text-ink-soft">No students in this class yet.</p>
      )}

      {students.length > 0 && (
        <>
          {/* live register summary — updates as you mark */}
          <div className="rounded-xl border border-line bg-card p-4 fiyox-rise">
            <div className="flex items-center justify-between gap-3 mb-2.5">
              <p className="text-xs uppercase tracking-wide text-ink-soft">Today&apos;s register</p>
              <p className="text-sm">
                <span className="display text-xl font-bold tabular"
                      style={{ color: summary.seen === 0 ? C.inkSoft : summary.rate >= 90 ? C.ledger : summary.rate >= 75 ? C.brass : C.sanction }}>
                  {summary.seen === 0 ? "—" : `${summary.rate}%`}
                </span>
                <span className="text-ink-soft"> present</span>
              </p>
            </div>
            <div className="h-2.5 rounded-full bg-paper overflow-hidden flex">
              {summary.segs.map((s) => s.pct > 0 && (
                <span key={s.key} style={{ width: `${s.pct}%`, background: s.color, transition: "width .3s ease" }} />
              ))}
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-3 text-xs">
              {chips.map((ch) => (
                <span key={ch.key} className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: ch.color }} />
                  <span className="text-ink-soft">{ch.label}</span>
                  <span className="tabular font-medium">{summary[ch.key]}</span>
                </span>
              ))}
              <span className="ml-auto text-ink-soft">{summary.seen} of {students.length} marked</span>
            </div>
          </div>

          <div className="rounded-lg border border-line bg-card divide-y divide-line">
            {students.map((s) => (
              <div key={s.id}
                   className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                <span className="text-sm whitespace-nowrap">
                  <span className="tabular text-ink-soft mr-2">{s.admission_number}</span>
                  {s.first_name} {s.last_name}
                </span>
                <div className="flex gap-1.5" role="radiogroup"
                     aria-label={`${s.first_name} ${s.last_name} attendance`}>
                  {STATUSES.map((st) => {
                    const active = marks[s.id] === st.value;
                    return (
                      <button key={st.value} role="radio" aria-checked={active}
                              onClick={() => setMarks((p) => ({ ...p, [s.id]: st.value }))}
                              className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                                active ? st.on : "border-line bg-white text-ink-soft hover:border-ink"}`}>
                        {st.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-4">
            <button onClick={save} disabled={saving || marked === 0}
                    className="rounded-md bg-ink text-white px-5 py-2.5 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
              {saving ? "Saving…" : `Save register (${marked}/${students.length})`}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
