"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";

type Subject = { id: string; name: string };
type Opt = { id: string; text: string };
type BankQ = {
  id: string; subject_id: string; topic: string; difficulty: string;
  type: string; text: string; options: Opt[]; correct: unknown; marks: number;
  active: boolean;
};
type Summary = { easy: number; medium: number; hard: number; total: number };

const DIFFS = ["easy", "medium", "hard"] as const;
const TYPES = [
  { v: "single", label: "Single choice" },
  { v: "multiple", label: "Multiple choice" },
  { v: "boolean", label: "True / False" },
  { v: "short", label: "Short answer" },
];

export default function QuestionBank() {
  const { ok, err } = useToast();
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [subjectId, setSubjectId] = useState("");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [rows, setRows] = useState<BankQ[]>([]);
  const [filter, setFilter] = useState<string>("");
  const [saving, setSaving] = useState(false);

  // new-question form
  const [type, setType] = useState("single");
  const [text, setText] = useState("");
  const [topic, setTopic] = useState("");
  const [difficulty, setDifficulty] = useState("medium");
  const [marks, setMarks] = useState(1);
  const [options, setOptions] = useState<Opt[]>([{ id: "a", text: "" }, { id: "b", text: "" }]);
  const [single, setSingle] = useState("a");
  const [multi, setMulti] = useState<string[]>([]);
  const [boolAns, setBoolAns] = useState(true);
  const [shortAns, setShortAns] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);

  useEffect(() => {
    api<Subject[]>("/api/academics/subjects").then(setSubjects).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    if (!subjectId) { setRows([]); setSummary(null); return; }
    const q = filter ? `&difficulty=${filter}` : "";
    const [list, sum] = await Promise.all([
      api<BankQ[]>(`/api/cbt/bank?subject_id=${subjectId}${q}`),
      api<Summary>(`/api/cbt/bank/summary?subject_id=${subjectId}`),
    ]);
    setRows(list); setSummary(sum);
  }, [subjectId, filter]);

  useEffect(() => { load().catch(() => {}); }, [load]);

  function reset() {
    setEditingId(null);
    setText(""); setTopic(""); setMarks(1); setDifficulty("medium"); setType("single");
    setOptions([{ id: "a", text: "" }, { id: "b", text: "" }]);
    setSingle("a"); setMulti([]); setBoolAns(true); setShortAns("");
  }

  function correctFor(): unknown {
    if (type === "single") return single;
    if (type === "multiple") return multi;
    if (type === "boolean") return boolAns;
    return shortAns.split(",").map((s) => s.trim()).filter(Boolean);
  }

  // load an existing question into the form for editing
  function startEdit(q: BankQ) {
    setEditingId(q.id);
    setType(q.type); setText(q.text); setTopic(q.topic);
    setDifficulty(q.difficulty); setMarks(q.marks);
    setOptions(q.options.length ? q.options.map((o) => ({ id: o.id, text: o.text }))
                                : [{ id: "a", text: "" }, { id: "b", text: "" }]);
    setSingle(q.type === "single" && typeof q.correct === "string" ? q.correct : "a");
    setMulti(q.type === "multiple" && Array.isArray(q.correct) ? (q.correct as string[]) : []);
    setBoolAns(q.type === "boolean" ? q.correct === true : true);
    setShortAns(q.type === "short" && Array.isArray(q.correct) ? (q.correct as string[]).join(", ") : "");
    if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function submit() {
    if (!subjectId) return err("Choose a subject first");
    if (!text.trim()) return err("Write the question");
    const body: Record<string, unknown> = {
      subject_id: subjectId, topic: topic.trim(), difficulty, type,
      text: text.trim(), marks: Number(marks), correct: correctFor(),
      options: type === "single" || type === "multiple"
        ? options.filter((o) => o.text.trim()) : [],
    };
    setSaving(true);
    try {
      if (editingId) {
        await api(`/api/cbt/bank/${editingId}`, { method: "PATCH", body: JSON.stringify(body) });
        ok("Question updated");
      } else {
        await api("/api/cbt/bank", { method: "POST", body: JSON.stringify(body) });
        ok("Added to the bank");
      }
      reset();
      await load();
    } catch (e) {
      err(e instanceof ApiError ? e.message : "Could not save the question");
    } finally { setSaving(false); }
  }

  async function remove(id: string) {
    if (!confirm("Delete this question from the bank? This cannot be undone.")) return;
    try {
      await api(`/api/cbt/bank/${id}`, { method: "DELETE" });
      if (editingId === id) reset();
      ok("Question deleted");
      await load();
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not delete it"); }
  }

  const field = "w-full rounded-md border border-line bg-white px-3 py-2 text-sm";
  const label = "block text-sm font-medium mb-1";
  const chip = (n: number, l: string, c: string) => (
    <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium"
          style={{ background: `${c}18`, color: c }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: c }} /> {n} {l}
    </span>
  );

  return (
    <div className="max-w-4xl space-y-5">
      <header>
        <h1 className="text-2xl font-bold">Question bank</h1>
        <p className="text-ink-soft text-sm mt-1">
          Build a pool of tagged questions. Pool exams draw a balanced, unique set
          from here for each student.
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[220px]">
          <label className={label}>Subject</label>
          <select className={field} value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
            <option value="">Select subject…</option>
            {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        {summary && (
          <div className="flex flex-wrap gap-2 pb-1">
            {chip(summary.easy, "easy", "#1e7a4f")}
            {chip(summary.medium, "medium", "#c8a24b")}
            {chip(summary.hard, "hard", "#b4232a")}
            <span className="text-xs text-ink-soft self-center">{summary.total} total</span>
          </div>
        )}
      </div>

      {subjectId && (
        <div className={`bg-card border rounded-xl p-5 space-y-4 card ${editingId ? "border-ink" : "border-line"}`}>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium">{editingId ? "Edit question" : "Add a question"}</p>
            {editingId && (
              <button onClick={reset} className="text-xs text-ink-soft hover:text-ink underline underline-offset-2">
                Cancel edit
              </button>
            )}
          </div>
          <div className="grid sm:grid-cols-4 gap-3">
            <div>
              <label className={label}>Type</label>
              <select className={field} value={type} onChange={(e) => setType(e.target.value)}>
                {TYPES.map((t) => <option key={t.v} value={t.v}>{t.label}</option>)}
              </select>
            </div>
            <div>
              <label className={label}>Difficulty</label>
              <select className={field} value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
                {DIFFS.map((d) => <option key={d} value={d} className="capitalize">{d}</option>)}
              </select>
            </div>
            <div>
              <label className={label}>Topic</label>
              <input className={field} value={topic} onChange={(e) => setTopic(e.target.value)}
                     placeholder="e.g. Fractions" />
            </div>
            <div>
              <label className={label}>Marks</label>
              <input type="number" min={1} step={0.5} className={field} value={marks}
                     onChange={(e) => setMarks(Number(e.target.value))} />
            </div>
          </div>

          <div>
            <label className={label}>Question</label>
            <textarea className={`${field} min-h-[60px]`} value={text}
                      onChange={(e) => setText(e.target.value)} />
          </div>

          {(type === "single" || type === "multiple") && (
            <div className="space-y-2">
              <label className={label}>Options {type === "single" ? "(pick the correct one)" : "(tick all correct)"}</label>
              {options.map((o, i) => (
                <div key={o.id} className="flex items-center gap-2">
                  <input type={type === "single" ? "radio" : "checkbox"} name="correct"
                         checked={type === "single" ? single === o.id : multi.includes(o.id)}
                         onChange={() => type === "single" ? setSingle(o.id)
                           : setMulti(multi.includes(o.id) ? multi.filter((x) => x !== o.id) : [...multi, o.id])} />
                  <span className="text-xs text-ink-soft w-4 uppercase">{o.id}</span>
                  <input className={field} value={o.text}
                         onChange={(e) => setOptions(options.map((x, j) => j === i ? { ...x, text: e.target.value } : x))}
                         placeholder={`Option ${o.id.toUpperCase()}`} />
                  {options.length > 2 && (
                    <button type="button" onClick={() => setOptions(options.filter((_, j) => j !== i))}
                            className="text-sanction text-xs">✕</button>
                  )}
                </div>
              ))}
              {options.length < 6 && (
                <button type="button"
                        onClick={() => setOptions([...options, { id: String.fromCharCode(97 + options.length), text: "" }])}
                        className="text-xs text-ink underline underline-offset-2">+ Add option</button>
              )}
            </div>
          )}

          {type === "boolean" && (
            <div>
              <label className={label}>Correct answer</label>
              <select className={field} value={boolAns ? "true" : "false"}
                      onChange={(e) => setBoolAns(e.target.value === "true")}>
                <option value="true">True</option>
                <option value="false">False</option>
              </select>
            </div>
          )}

          {type === "short" && (
            <div>
              <label className={label}>Accepted answers (comma-separated)</label>
              <input className={field} value={shortAns} onChange={(e) => setShortAns(e.target.value)}
                     placeholder="e.g. eight, 8" />
            </div>
          )}

          <button onClick={submit} disabled={saving}
                  className="rounded-md bg-ink text-white px-5 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
            {saving ? "Saving…" : editingId ? "Save changes" : "Add to bank"}
          </button>
        </div>
      )}

      {subjectId && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">Questions</span>
            <select className="rounded-md border border-line bg-white px-2 py-1 text-xs"
                    value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="">All difficulties</option>
              {DIFFS.map((d) => <option key={d} value={d} className="capitalize">{d}</option>)}
            </select>
          </div>
          {rows.length === 0 ? (
            <p className="text-sm text-ink-soft">No questions yet.</p>
          ) : rows.map((q) => (
            <div key={q.id}
                 className={`bg-card border rounded-lg p-3 flex items-start justify-between gap-3 ${editingId === q.id ? "border-ink" : "border-line"}`}>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink-soft mb-0.5">
                  <span className="capitalize font-medium">{q.difficulty}</span>
                  {q.topic && <span>· {q.topic}</span>}
                  <span>· {q.type}</span>
                  <span>· {q.marks} mark{q.marks === 1 ? "" : "s"}</span>
                </div>
                <div className="text-sm break-words">{q.text}</div>
              </div>
              <div className="shrink-0 flex items-center gap-3">
                <button onClick={() => startEdit(q)}
                        className="text-ink text-xs underline underline-offset-2">Edit</button>
                <button onClick={() => remove(q.id)}
                        className="text-sanction text-xs underline underline-offset-2">Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
