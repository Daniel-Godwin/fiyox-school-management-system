"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, me, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";

type Term = { id: string; name: string; session: string; is_current: boolean };
type Arm = { id: string; label: string };
type Subject = { id: string; name: string };
type Assignment = { subject_id: string; arm_id: string };
type Component = { id: string; name: string; max_score: number };

export default function NewCBT() {
  const router = useRouter();
  const { err } = useToast();

  const [role, setRole] = useState<string>("");
  const [terms, setTerms] = useState<Term[]>([]);
  const [arms, setArms] = useState<Arm[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);

  const [title, setTitle] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [armId, setArmId] = useState("");
  const [termId, setTermId] = useState("");
  const [duration, setDuration] = useState(30);
  const [maxAttempts, setMaxAttempts] = useState(1);
  const [shuffle, setShuffle] = useState(true);
  const [showResults, setShowResults] = useState(true);
  const [instructions, setInstructions] = useState("");
  const [components, setComponents] = useState<Component[]>([]);
  const [componentId, setComponentId] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([
      me(),
      api<Term[]>("/api/academics/terms"),
      api<Arm[]>("/api/academics/arms"),
      api<Subject[]>("/api/academics/subjects"),
      api<Assignment[]>("/api/users/assignments").catch(() => []),
      api<Component[]>("/api/assessment-components").catch(() => []),
    ]).then(([u, t, a, s, asg, comps]) => {
      setRole(u.role);
      setTerms(t); setArms(a); setSubjects(s); setAssignments(asg); setComponents(comps);
      const cur = t.find((x) => x.is_current);
      if (cur) setTermId(cur.id);
    }).catch(() => err("Could not load class lists. Is the backend running?"));
  }, [err]);

  const isTeacher = role === "teacher";
  // a teacher may only set tests for pairs they teach
  const allowedArms = useMemo(
    () => (isTeacher ? arms.filter((a) => assignments.some((x) => x.arm_id === a.id)) : arms),
    [isTeacher, arms, assignments]);
  const allowedSubjects = useMemo(
    () => (isTeacher
      ? subjects.filter((s) => assignments.some((x) => x.subject_id === s.id && (!armId || x.arm_id === armId)))
      : subjects),
    [isTeacher, subjects, assignments, armId]);

  async function create() {
    if (!title.trim()) return err("Give the test a title");
    if (!subjectId || !armId || !termId) return err("Choose a class, subject and term");
    setSaving(true);
    try {
      const exam = await api<{ id: string }>("/api/cbt/exams", {
        method: "POST",
        body: JSON.stringify({
          title: title.trim(), subject_id: subjectId, arm_id: armId, term_id: termId,
          duration_minutes: Number(duration), max_attempts: Number(maxAttempts),
          shuffle_questions: shuffle, show_results_immediately: showResults,
          instructions: instructions.trim(),
          component_id: componentId || null,
        }),
      });
      router.push(`/dashboard/cbt/${exam.id}`);
    } catch (e) {
      err(e instanceof ApiError ? e.message : "Could not create the test");
      setSaving(false);
    }
  }

  const field = "w-full rounded-md border border-line bg-white px-3 py-2 text-sm";
  const label = "block text-sm font-medium mb-1";

  return (
    <div className="max-w-2xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold">New test</h1>
        <p className="text-ink-soft text-sm mt-1">
          Set the basics now — you’ll add questions on the next screen, then publish
          when it’s ready.
        </p>
      </header>

      <div className="bg-card border border-line rounded-xl p-5 space-y-4 card">
        <div>
          <label className={label}>Title</label>
          <input className={field} value={title} onChange={(e) => setTitle(e.target.value)}
                 placeholder="e.g. Mathematics — First CA test" />
        </div>

        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className={label}>Class</label>
            <select className={field} value={armId}
                    onChange={(e) => { setArmId(e.target.value); setSubjectId(""); }}>
              <option value="">Select class…</option>
              {allowedArms.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
            </select>
          </div>
          <div>
            <label className={label}>Subject</label>
            <select className={field} value={subjectId}
                    onChange={(e) => setSubjectId(e.target.value)}>
              <option value="">Select subject…</option>
              {allowedSubjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
        </div>

        <div className="grid sm:grid-cols-3 gap-4">
          <div>
            <label className={label}>Term</label>
            <select className={field} value={termId} onChange={(e) => setTermId(e.target.value)}>
              <option value="">Select…</option>
              {terms.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} — {t.session}{t.is_current ? " (current)" : ""}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={label}>Duration (min)</label>
            <input type="number" min={1} className={field} value={duration}
                   onChange={(e) => setDuration(Number(e.target.value))} />
          </div>
          <div>
            <label className={label}>Attempts allowed</label>
            <input type="number" min={1} className={field} value={maxAttempts}
                   onChange={(e) => setMaxAttempts(Number(e.target.value))} />
          </div>
        </div>

        <div>
          <label className={label}>Counts towards (result sheet)</label>
          <select className={field} value={componentId}
                  onChange={(e) => setComponentId(e.target.value)}>
            <option value="">Practice only — does not count</option>
            {components.map((c) => (
              <option key={c.id} value={c.id}>{c.name} (max {c.max_score})</option>
            ))}
          </select>
          <p className="text-xs text-ink-soft mt-1">
            When set, each student&apos;s score is scaled to this column and written
            into their report card automatically on submit.
          </p>
        </div>

        <div>
          <label className={label}>Instructions (optional)</label>
          <textarea className={`${field} min-h-[72px]`} value={instructions}
                    onChange={(e) => setInstructions(e.target.value)}
                    placeholder="Shown to students before they begin." />
        </div>

        <div className="flex flex-col gap-2 pt-1">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={shuffle} onChange={(e) => setShuffle(e.target.checked)} />
            Shuffle question order for each student
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={showResults} onChange={(e) => setShowResults(e.target.checked)} />
            Show each student their score immediately after submitting
          </label>
        </div>

        <div className="flex gap-3 pt-2">
          <button onClick={create} disabled={saving}
                  className="rounded-md bg-ink text-white px-5 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
            {saving ? "Creating…" : "Create & add questions"}
          </button>
          <button onClick={() => router.push("/dashboard/cbt")}
                  className="rounded-md border border-line px-5 py-2 text-sm font-medium hover:border-ink">
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
