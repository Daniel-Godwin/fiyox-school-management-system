"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

type Term = { id: string; name: string; session: string; is_current: boolean };
type Arm = { id: string; label: string };
type Subject = { id: string; name: string };
type Component = { id: string; name: string; max_score: number; sequence: number };
type Assignment = {
  id: string; subject_id: string; subject_name: string;
  arm_id: string; class_label: string;
};
type Me = { role: string };
type Student = {
  id: string; admission_number: string; first_name: string; last_name: string;
  current_arm_id: string | null;
};
type ScoreCell = { student_id: string; component_id: string; score: number };

/** cell key */
const k = (s: string, c: string) => `${s}::${c}`;

export default function ScoreEntryPage() {
  const [terms, setTerms] = useState<Term[]>([]);
  const [arms, setArms] = useState<Arm[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [termId, setTermId] = useState("");
  const [armId, setArmId] = useState("");
  const [subjectId, setSubjectId] = useState("");

  const [components, setComponents] = useState<Component[]>([]);
  const [students, setStudents] = useState<Student[]>([]);
  const [cells, setCells] = useState<Record<string, string>>({});
  const [me, setMe] = useState<Me | null>(null);
  const [assignments, setAssignments] = useState<Assignment[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  // load selectors once
  useEffect(() => {
    Promise.all([
      api<Me>("/api/auth/me"),
      api<Term[]>("/api/academics/terms"),
      api<Arm[]>("/api/academics/arms"),
      api<Subject[]>("/api/academics/subjects"),
      api<Assignment[]>("/api/users/assignments"),
    ]).then(([u, t, a, s, asg]) => {
      setMe(u);
      setTerms(t);
      setArms(a);
      setSubjects(s);
      setAssignments(asg);
      const current = t.find((x) => x.is_current);
      if (current) setTermId(current.id);
    }).catch(() => setNotice({ kind: "err", text: "Could not load class lists. Is the backend running?" }));
  }, []);

  const isTeacher = me?.role === "teacher";

  // a teacher may only enter scores for what they are assigned to teach
  const allowedArms = isTeacher && assignments
    ? arms.filter((a) => assignments.some((x) => x.arm_id === a.id))
    : arms;
  const allowedSubjects = isTeacher && assignments
    ? subjects.filter((s) => assignments.some(
        (x) => x.subject_id === s.id && (!armId || x.arm_id === armId)))
    : subjects;

  const ready = termId && armId && subjectId;

  // load the grid whenever all three are chosen
  const loadGrid = useCallback(async () => {
    if (!ready) return;
    setLoading(true);
    setNotice(null);
    try {
      const [comps, allStudents, existing] = await Promise.all([
        api<Component[]>("/api/assessment-components"),
        api<Student[]>("/api/students"),
        api<ScoreCell[]>(`/api/scores?arm_id=${armId}&subject_id=${subjectId}&term_id=${termId}`),
      ]);
      setComponents([...comps].sort((a, b) => a.sequence - b.sequence));
      setStudents(
        allStudents
          .filter((s) => s.current_arm_id === armId)
          .sort((a, b) => a.admission_number.localeCompare(b.admission_number)),
      );
      const filled: Record<string, string> = {};
      for (const c of existing) filled[k(c.student_id, c.component_id)] = String(c.score);
      setCells(filled);
    } catch {
      setNotice({ kind: "err", text: "Could not load the score sheet. Try again." });
    } finally {
      setLoading(false);
    }
  }, [ready, armId, subjectId, termId]);

  useEffect(() => { loadGrid(); }, [loadGrid]);

  const maxByComp = useMemo(
    () => Object.fromEntries(components.map((c) => [c.id, c.max_score])),
    [components],
  );

  function setCell(sid: string, cid: string, value: string) {
    setCells((prev) => ({ ...prev, [k(sid, cid)]: value }));
  }

  /** invalid = non-numeric or above the component max */
  function isInvalid(cid: string, raw: string): boolean {
    if (raw.trim() === "") return false;
    const n = Number(raw);
    return Number.isNaN(n) || n < 0 || n > (maxByComp[cid] ?? 100);
  }

  const invalidCount = useMemo(
    () =>
      Object.entries(cells).filter(([key, v]) => {
        const cid = key.split("::")[1];
        return isInvalid(cid, v);
      }).length,
    [cells, maxByComp], // eslint-disable-line react-hooks/exhaustive-deps
  );

  async function save() {
    setSaving(true);
    setNotice(null);
    try {
      const rows = students
        .map((s) => {
          const scores: Record<string, number> = {};
          for (const c of components) {
            const raw = cells[k(s.id, c.id)];
            if (raw !== undefined && raw.trim() !== "" && !isInvalid(c.id, raw)) {
              scores[c.id] = Number(raw);
            }
          }
          return { student_id: s.id, scores };
        })
        .filter((r) => Object.keys(r.scores).length > 0);

      if (rows.length === 0) {
        setNotice({ kind: "err", text: "Nothing to save yet — enter at least one score." });
        return;
      }
      const res = await api<{ scores_written: number }>("/api/scores", {
        method: "POST",
        body: JSON.stringify({ subject_id: subjectId, arm_id: armId, term_id: termId, rows }),
      });
      setNotice({ kind: "ok", text: `Saved ${res.scores_written} score${res.scores_written === 1 ? "" : "s"}.` });
    } catch {
      setNotice({ kind: "err", text: "Save failed. Check your connection and try again." });
    } finally {
      setSaving(false);
    }
  }

  const totalFor = (sid: string) =>
    components.reduce((sum, c) => {
      const raw = cells[k(sid, c.id)];
      const n = Number(raw);
      return raw && !Number.isNaN(n) ? sum + n : sum;
    }, 0);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">Score entry</h1>
        <p className="text-sm text-ink-soft mt-1">
          Pick a term, class and subject, then fill the sheet. Corrections are
          recorded in the audit trail.
        </p>
      </header>

      {/* selectors */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-3xl">
        {[
          { label: "Term", value: termId, set: setTermId,
            opts: terms.map((t) => ({ id: t.id, label: `${t.name} term · ${t.session}` })) },
          { label: "Class", value: armId, set: setArmId,
            opts: allowedArms.map((a) => ({ id: a.id, label: a.label })) },
          { label: "Subject", value: subjectId, set: setSubjectId,
            opts: allowedSubjects.map((s) => ({ id: s.id, label: s.name })) },
        ].map((f) => (
          <label key={f.label} className="block">
            <span className="block text-xs font-medium text-ink-soft mb-1">{f.label}</span>
            <select
              value={f.value}
              onChange={(e) => f.set(e.target.value)}
              className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm"
            >
              <option value="">Select {f.label.toLowerCase()}…</option>
              {f.opts.map((o) => (
                <option key={o.id} value={o.id}>{o.label}</option>
              ))}
            </select>
          </label>
        ))}
      </div>

      {isTeacher && assignments && assignments.length === 0 && (
        <p className="text-sm text-sanction border border-sanction/30 bg-sanction/5 rounded-lg p-4 max-w-3xl">
          You have not been assigned any subjects yet. Only the subjects you teach
          appear here — ask the school admin to assign you.
        </p>
      )}

      {isTeacher && assignments && assignments.length > 0 && (
        <p className="text-xs text-ink-soft">
          You can enter scores for:{" "}
          {assignments.map((a) => `${a.subject_name} (${a.class_label})`).join(" · ")}
        </p>
      )}

      {!ready && (
        <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-6 max-w-3xl">
          The score sheet appears once a term, class and subject are selected.
        </p>
      )}

      {ready && loading && <p className="text-sm text-ink-soft">Loading the sheet…</p>}

      {ready && !loading && students.length === 0 && (
        <p className="text-sm text-ink-soft">No students in this class yet.</p>
      )}

      {ready && !loading && students.length > 0 && (
        <>
          <div className="overflow-x-auto rounded-lg border border-line bg-card">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-ink text-white text-left">
                  <th className="px-3 py-2 font-medium">Student</th>
                  {components.map((c) => (
                    <th key={c.id} className="px-3 py-2 font-medium text-center whitespace-nowrap">
                      {c.name} <span className="opacity-60 font-normal">/{c.max_score}</span>
                    </th>
                  ))}
                  <th className="px-3 py-2 font-medium text-right">Total</th>
                </tr>
              </thead>
              <tbody>
                {students.map((s, i) => (
                  <tr key={s.id} className={i % 2 ? "bg-paper" : "bg-card"}>
                    <td className="px-3 py-1.5 whitespace-nowrap">
                      <span className="tabular text-ink-soft mr-2">{s.admission_number}</span>
                      {s.first_name} {s.last_name}
                    </td>
                    {components.map((c) => {
                      const raw = cells[k(s.id, c.id)] ?? "";
                      const bad = isInvalid(c.id, raw);
                      return (
                        <td key={c.id} className="px-2 py-1.5 text-center">
                          <input
                            inputMode="decimal"
                            aria-label={`${s.first_name} ${s.last_name} — ${c.name}`}
                            value={raw}
                            onChange={(e) => setCell(s.id, c.id, e.target.value)}
                            className={`w-16 rounded border px-2 py-1 text-center tabular ${
                              bad ? "border-sanction bg-sanction/10" : "border-line bg-white"
                            }`}
                          />
                        </td>
                      );
                    })}
                    <td className="px-3 py-1.5 text-right tabular font-medium">{totalFor(s.id)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={save}
              disabled={saving || invalidCount > 0}
              className="rounded-md bg-ink text-white px-5 py-2.5 text-sm font-medium hover:bg-ink-soft disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save scores"}
            </button>
            {invalidCount > 0 && (
              <span className="text-sm text-sanction">
                {invalidCount} score{invalidCount === 1 ? " is" : "s are"} above the maximum — fix the red cells.
              </span>
            )}
            {notice && (
              <span
                role="status"
                className={`text-sm ${notice.kind === "ok" ? "text-ledger" : "text-sanction"}`}
              >
                {notice.text}
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}
