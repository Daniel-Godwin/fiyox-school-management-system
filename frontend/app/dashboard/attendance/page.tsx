"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

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
    api<Arm[]>("/api/academics/arms")
      .then(setArms)
      .catch(() => setNotice({ kind: "err", text: "Could not load classes. Is the backend running?" }));
  }, []);

  const load = useCallback(async () => {
    if (!armId || !date) return;
    setNotice(null);
    try {
      const [all, register] = await Promise.all([
        api<Student[]>("/api/students"),
        api<RegisterRow[]>(`/api/attendance/register?arm_id=${armId}&date=${date}`),
      ]);
      setStudents(
        all.filter((s) => s.current_arm_id === armId)
           .sort((a, b) => a.admission_number.localeCompare(b.admission_number)),
      );
      setMarks(Object.fromEntries(register.map((r) => [r.student_id, r.status])));
    } catch {
      setNotice({ kind: "err", text: "Could not load the register." });
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
      const res = await api<{ created: number; updated: number; unchanged: number }>(
        "/api/attendance/mark",
        { method: "POST", body: JSON.stringify({ arm_id: armId, date, records }) },
      );
      const parts = [];
      if (res.created) parts.push(`${res.created} marked`);
      if (res.updated) parts.push(`${res.updated} corrected`);
      if (res.unchanged) parts.push(`${res.unchanged} unchanged`);
      setNotice({ kind: "ok", text: `Register saved — ${parts.join(", ")}.` });
    } catch {
      setNotice({ kind: "err", text: "Save failed. Check your connection and try again." });
    } finally { setSaving(false); }
  }

  const marked = Object.keys(marks).length;

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
