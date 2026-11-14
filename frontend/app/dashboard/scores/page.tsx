"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "@/lib/api";
import { cachedGet, queuedPost, putCache } from "@/lib/offline/offlineApi";
import { Kpi, BRAND as C } from "@/components/Panels";

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
type PvComp = { id: string; name: string; max_score: number; is_exam: boolean; cbt_backed: boolean };
type PvStudent = {
  student_id: string; admission_number: string; name: string;
  scores: Record<string, number>; total: number; missing: string[];
};
type Preview = { components: PvComp[]; students: PvStudent[] };

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
  const [preview, setPreview] = useState<Preview | null>(null);

  // load selectors once (served from the offline cache when there's no network)
  useEffect(() => {
    Promise.all([
      cachedGet<Me>("/api/auth/me"),
      cachedGet<Term[]>("/api/academics/terms"),
      cachedGet<Arm[]>("/api/academics/arms"),
      cachedGet<Subject[]>("/api/academics/subjects"),
      cachedGet<Assignment[]>("/api/users/assignments"),
    ]).then(([u, t, a, s, asg]) => {
      setMe(u.data);
      setTerms(t.data);
      setArms(a.data);
      setSubjects(s.data);
      setAssignments(asg.data);
      const current = t.data.find((x) => x.is_current);
      if (current) setTermId(current.id);
    }).catch(() => setNotice({ kind: "err", text: "Could not load class lists. Open this page once while online so it can be used offline later." }));
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
    const scoresPath = `/api/scores?arm_id=${armId}&subject_id=${subjectId}&term_id=${termId}`;
    try {
      const [comps, allStudents, existing] = await Promise.all([
        cachedGet<Component[]>("/api/assessment-components"),
        cachedGet<Student[]>("/api/students"),
        cachedGet<ScoreCell[]>(scoresPath),
      ]);
      setComponents([...comps.data].sort((a, b) => a.sequence - b.sequence));
      setStudents(
        allStudents.data
          .filter((s) => s.current_arm_id === armId)
          .sort((a, b) => a.admission_number.localeCompare(b.admission_number)),
      );
      const filled: Record<string, string> = {};
      for (const c of existing.data) filled[k(c.student_id, c.component_id)] = String(c.score);
      setCells(filled);
      if (comps.stale || allStudents.stale || existing.stale) {
        setNotice({ kind: "ok", text: "You're offline — showing the last saved copy. Scores you enter will sync automatically." });
      }
    } catch {
      setNotice({ kind: "err", text: "Could not load the score sheet. Open it once while online to use it offline." });
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
      const label = `Scores — ${arms.find((a) => a.id === armId)?.label ?? "class"}, ${subjects.find((s) => s.id === subjectId)?.name ?? "subject"}`;
      const r = await queuedPost<{ scores_written: number }>(
        "/api/scores",
        { subject_id: subjectId, arm_id: armId, term_id: termId, rows },
        label,
      );
      if (r.queued) {
        // keep the entered values in the offline cache so reopening shows them
        const cache: ScoreCell[] = [];
        for (const s of students) for (const c of components) {
          const raw = cells[k(s.id, c.id)];
          if (raw !== undefined && raw.trim() !== "" && !isInvalid(c.id, raw)) {
            cache.push({ student_id: s.id, component_id: c.id, score: Number(raw) });
          }
        }
        void putCache(`/api/scores?arm_id=${armId}&subject_id=${subjectId}&term_id=${termId}`, cache);
        setNotice({ kind: "ok", text: "Saved on this device — it will sync automatically when you're back online." });
      } else {
        const n = r.result?.scores_written ?? 0;
        // re-read from the server so the grid shows the confirmed, persisted
        // values — not just the local echo — which also surfaces any discrepancy
        await loadGrid();
        setNotice({ kind: "ok", text: `Saved ${n} score${n === 1 ? "" : "s"}. These are now stored on the server.` });
      }
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Save failed. Check your connection and try again." });
    } finally {
      setSaving(false);
    }
  }

  async function openPreview() {
    setSaving(true);
    setNotice(null);
    try {
      const p = await cachedGet<Preview>(
        `/api/scores/preview?arm_id=${armId}&subject_id=${subjectId}&term_id=${termId}`);
      setPreview(p.data);
    } catch {
      setNotice({ kind: "err", text: "Could not load the preview. Save first, then try again." });
    } finally { setSaving(false); }
  }

  const totalFor = (sid: string) =>
    components.reduce((sum, c) => {
      const raw = cells[k(sid, c.id)];
      const n = Number(raw);
      return raw && !Number.isNaN(n) ? sum + n : sum;
    }, 0);

  // live entry progress + running class average as the teacher fills the sheet
  const progress = useMemo(() => {
    const totalCells = students.length * components.length;
    let filled = 0;
    const totals: number[] = [];
    for (const s of students) {
      let any = false, t = 0;
      for (const c of components) {
        const raw = cells[k(s.id, c.id)];
        if (raw !== undefined && raw.trim() !== "" && !isInvalid(c.id, raw)) { filled++; any = true; t += Number(raw); }
      }
      if (any) totals.push(t);
    }
    const avg = totals.length ? Math.round(totals.reduce((a, b) => a + b, 0) / totals.length) : null;
    return { totalCells, filled, withScores: totals.length,
             pct: totalCells ? Math.round((filled / totalCells) * 100) : 0, avg };
  }, [students, components, cells, maxByComp]); // eslint-disable-line react-hooks/exhaustive-deps

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
          {/* live entry progress */}
          <div className="space-y-2 fiyox-rise max-w-3xl">
            <div className="grid grid-cols-3 gap-3">
              <Kpi label="Students" value={students.length.toString()} accent={C.ink} />
              <Kpi label="Scores entered" value={`${progress.filled}/${progress.totalCells}`}
                   hint={`${progress.pct}% complete`}
                   accent={progress.pct === 100 ? C.ledger : C.brass} />
              <Kpi label="Class average" value={progress.avg === null ? "—" : String(progress.avg)}
                   hint={progress.withScores ? `${progress.withScores} with scores` : undefined}
                   accent={C.inkSoft} />
            </div>
            <div className="h-2 rounded-full bg-paper overflow-hidden">
              <div className="h-full rounded-full"
                   style={{ width: `${progress.pct}%`, background: progress.pct === 100 ? C.ledger : C.brass, transition: "width .3s ease" }} />
            </div>
          </div>

          {/* tablet / desktop: the full sheet as a table */}
          <div className="hidden md:block overflow-x-auto rounded-lg border border-line bg-card">
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

          {/* phone: one card per student so the name and its score boxes stay together */}
          <div className="md:hidden space-y-3">
            {students.map((s) => (
              <div key={s.id} className="rounded-lg border border-line bg-card p-3">
                <div className="flex items-baseline justify-between gap-2 mb-3">
                  <p className="font-medium leading-tight">
                    {s.first_name} {s.last_name}
                    <span className="block tabular text-xs text-ink-soft">{s.admission_number}</span>
                  </p>
                  <p className="text-sm text-ink-soft shrink-0">
                    Total <span className="tabular font-semibold text-ink">{totalFor(s.id)}</span>
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {components.map((c) => {
                    const raw = cells[k(s.id, c.id)] ?? "";
                    const bad = isInvalid(c.id, raw);
                    return (
                      <label key={c.id} className="block">
                        <span className="block text-xs text-ink-soft mb-1">
                          {c.name} <span className="opacity-60">/{c.max_score}</span>
                        </span>
                        <input
                          inputMode="decimal"
                          aria-label={`${s.first_name} ${s.last_name} — ${c.name}`}
                          value={raw}
                          onChange={(e) => setCell(s.id, c.id, e.target.value)}
                          className={`w-full rounded border px-3 py-2 text-center tabular ${
                            bad ? "border-sanction bg-sanction/10" : "border-line bg-white"
                          }`}
                        />
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-4 flex-wrap">
            <button
              onClick={save}
              disabled={saving || invalidCount > 0}
              className="rounded-md bg-ink text-white px-5 py-2.5 text-sm font-medium hover:bg-ink-soft disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save scores"}
            </button>
            <button
              onClick={openPreview}
              disabled={saving || invalidCount > 0}
              className="rounded-md border border-ink text-ink px-5 py-2.5 text-sm font-medium hover:bg-ink hover:text-white disabled:opacity-50"
            >
              Preview &amp; verify
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

          {/* read-only verify sheet: confirm every mark (incl. CBT) before results go up */}
          {preview && (
            <section className="rounded-lg border border-ink/30 bg-paper/50 p-4 space-y-3 fiyox-rise">
              <div className="flex items-baseline justify-between gap-2">
                <p className="text-sm font-medium">Preview &amp; verify — saved scores on the server</p>
                <button onClick={() => setPreview(null)}
                        className="text-xs text-ink-soft underline underline-offset-2">Close</button>
              </div>
              <p className="text-xs text-ink-soft">
                These are the marks currently stored. <span className="text-ledger font-medium">CBT</span> columns
                are filled automatically from a test; a red <span className="text-sanction font-medium">—</span> means
                no mark has been entered yet. Check totals and fill any gaps before results are sent for approval.
              </p>
              <div className="overflow-x-auto rounded-lg border border-line bg-card">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="bg-ink text-white text-left">
                      <th className="px-3 py-2 font-medium">Student</th>
                      {preview.components.map((c) => (
                        <th key={c.id} className="px-3 py-2 font-medium text-center whitespace-nowrap">
                          {c.name} <span className="opacity-60 font-normal">/{c.max_score}</span>
                          {c.cbt_backed && <span className="block text-[10px] text-brass">CBT</span>}
                        </th>
                      ))}
                      <th className="px-3 py-2 font-medium text-right">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.students.map((s, i) => (
                      <tr key={s.student_id} className={i % 2 ? "bg-paper" : "bg-card"}>
                        <td className="px-3 py-1.5 whitespace-nowrap">
                          <span className="tabular text-ink-soft mr-2">{s.admission_number}</span>{s.name}
                        </td>
                        {preview.components.map((c) => (
                          <td key={c.id} className="px-3 py-1.5 text-center tabular">
                            {s.missing.includes(c.id)
                              ? <span className="text-sanction font-semibold">—</span>
                              : s.scores[c.id]}
                          </td>
                        ))}
                        <td className="px-3 py-1.5 text-right tabular font-medium">{s.total}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {(() => {
                const gaps = preview.students.filter((s) => s.missing.length > 0).length;
                return gaps > 0 ? (
                  <p className="text-xs text-sanction">
                    {gaps} student{gaps === 1 ? "" : "s"} still {gaps === 1 ? "has" : "have"} one or
                    more empty columns. Once everything is correct, the class results can be
                    submitted for approval from the Results page.
                  </p>
                ) : (
                  <p className="text-xs text-ledger">
                    Every student has a mark in every column. You can submit the class results
                    for approval from the Results page.
                  </p>
                );
              })()}
            </section>
          )}
        </>
      )}
    </div>
  );
}
