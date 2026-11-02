"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";

type Option = { id: string; text: string };
type Question = { id: string; type: string; text: string; options: Option[]; correct: unknown; marks: number };
type Test = {
  id: string; title: string; instructions: string; applying_class_id: string | null;
  applying_class: string | null; duration_minutes: number; total_marks: number;
  question_count: number; is_active: boolean; questions?: Question[];
};
type Klass = { id: string; name: string };

const TYPES = [
  { v: "single", label: "Single choice" }, { v: "multiple", label: "Multiple answers" },
  { v: "boolean", label: "True / False" }, { v: "short", label: "Short answer" },
];
const field = "w-full rounded-md border border-line bg-white px-3 py-2 text-sm";

function QuestionEditor({ testId, onSaved, onCancel }: { testId: string; onSaved: () => void; onCancel: () => void }) {
  const { err } = useToast();
  const [type, setType] = useState("single");
  const [text, setText] = useState(""); const [marks, setMarks] = useState(1);
  const [options, setOptions] = useState<Option[]>([{ id: "o1", text: "" }, { id: "o2", text: "" }]);
  const [single, setSingle] = useState(""); const [multi, setMulti] = useState<string[]>([]);
  const [bool, setBool] = useState(true); const [short, setShort] = useState("");
  const [saving, setSaving] = useState(false);

  function addOption() {
    const n = options.reduce((m, o) => Math.max(m, Number(o.id.replace("o", "")) || 0), 0) + 1;
    setOptions([...options, { id: `o${n}`, text: "" }]);
  }
  async function save() {
    if (!text.trim()) return err("Write the question");
    const body: Record<string, unknown> = { type, text: text.trim(), marks: Number(marks) };
    if (type === "single" || type === "multiple") {
      const cleaned = options.filter((o) => o.text.trim());
      if (cleaned.length < 2) return err("Give at least two options");
      body.options = cleaned;
      if (type === "single") { if (!single) return err("Mark the correct option"); body.correct = single; }
      else { if (multi.length === 0) return err("Tick at least one correct answer"); body.correct = multi; }
    } else if (type === "boolean") body.correct = bool;
    else { const acc = short.split(",").map(s => s.trim()).filter(Boolean); if (!acc.length) return err("Give an accepted answer"); body.correct = acc; }
    setSaving(true);
    try { await api(`/api/admissions/tests/${testId}/questions`, { method: "POST", body: JSON.stringify(body) }); onSaved(); }
    catch (e) { err(e instanceof ApiError ? e.message : "Could not save"); setSaving(false); }
  }

  return (
    <div className="rounded-lg border border-ink/30 bg-paper/60 p-4 space-y-3">
      <div className="grid sm:grid-cols-[1fr_auto] gap-3">
        <div><label className="block text-xs text-ink-soft mb-1">Type</label>
          <select className={field} value={type} onChange={e => setType(e.target.value)}>{TYPES.map(t => <option key={t.v} value={t.v}>{t.label}</option>)}</select></div>
        <div><label className="block text-xs text-ink-soft mb-1">Marks</label>
          <input type="number" min={1} className={`${field} w-24`} value={marks} onChange={e => setMarks(Number(e.target.value))} /></div>
      </div>
      <div><label className="block text-xs text-ink-soft mb-1">Question</label>
        <textarea className={`${field} min-h-[56px]`} value={text} onChange={e => setText(e.target.value)} /></div>
      {(type === "single" || type === "multiple") && (
        <div className="space-y-2">
          <p className="text-xs text-ink-soft">{type === "single" ? "Pick the correct answer" : "Tick every correct answer"}</p>
          {options.map((o) => (
            <div key={o.id} className="flex items-center gap-2">
              {type === "single"
                ? <input type="radio" name="c" checked={single === o.id} onChange={() => setSingle(o.id)} />
                : <input type="checkbox" checked={multi.includes(o.id)} onChange={e => setMulti(e.target.checked ? [...multi, o.id] : multi.filter(x => x !== o.id))} />}
              <input className={field} value={o.text} placeholder="Option" onChange={e => setOptions(options.map(x => x.id === o.id ? { ...x, text: e.target.value } : x))} />
            </div>
          ))}
          <button onClick={addOption} className="text-sm text-ink font-medium hover:underline">+ Add option</button>
        </div>
      )}
      {type === "boolean" && (
        <div className="flex gap-4 text-sm">
          <label className="flex items-center gap-2"><input type="radio" checked={bool} onChange={() => setBool(true)} /> True is correct</label>
          <label className="flex items-center gap-2"><input type="radio" checked={!bool} onChange={() => setBool(false)} /> False is correct</label>
        </div>
      )}
      {type === "short" && <div><label className="block text-xs text-ink-soft mb-1">Accepted answers (comma-separated)</label><input className={field} value={short} onChange={e => setShort(e.target.value)} placeholder="e.g. 8, eight" /></div>}
      <div className="flex gap-2">
        <button onClick={save} disabled={saving} className="rounded-md bg-ink text-white px-4 py-1.5 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">{saving ? "Saving…" : "Add question"}</button>
        <button onClick={onCancel} className="rounded-md border border-line px-4 py-1.5 text-sm font-medium hover:border-ink">Cancel</button>
      </div>
    </div>
  );
}

export default function EntranceTestSetup() {
  const { ok, err } = useToast();
  const [tests, setTests] = useState<Test[]>([]);
  const [classes, setClasses] = useState<Klass[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Test | null>(null);
  const [adding, setAdding] = useState(false);
  const [nt, setNt] = useState({ title: "", applying_class_id: "", duration_minutes: 30 });

  const load = useCallback(() => { api<Test[]>("/api/admissions/tests").then(setTests).catch(() => err("Could not load tests")); }, [err]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api<Klass[]>("/api/academics/arms").then((arms: { class_id: string; class_name: string }[] | any) => {
    // derive distinct classes from arms
    const seen = new Map<string, string>();
    (arms as { class_id: string; class_name: string }[]).forEach(a => seen.set(a.class_id, a.class_name));
    setClasses([...seen].map(([id, name]) => ({ id, name })));
  }).catch(() => {}); }, []);

  const openTest = useCallback((id: string) => {
    if (openId === id) { setOpenId(null); setDetail(null); return; }
    setOpenId(id); setDetail(null);
    api<Test>(`/api/admissions/tests/${id}`).then(setDetail).catch(() => err("Could not load test"));
  }, [openId, err]);

  async function createTest() {
    if (!nt.title.trim()) return err("Give the test a title");
    try {
      await api("/api/admissions/tests", { method: "POST", body: JSON.stringify({
        title: nt.title.trim(), applying_class_id: nt.applying_class_id || null, duration_minutes: Number(nt.duration_minutes) }) });
      setNt({ title: "", applying_class_id: "", duration_minutes: 30 }); ok("Test created."); load();
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not create"); }
  }
  async function toggleActive(t: Test) {
    try { await api(`/api/admissions/tests/${t.id}`, { method: "PATCH", body: JSON.stringify({ is_active: !t.is_active }) }); ok(t.is_active ? "Deactivated." : "Activated."); load(); }
    catch (e) { err(e instanceof ApiError ? e.message : "Could not update"); }
  }
  async function delQuestion(testId: string, qid: string) {
    try { await api(`/api/admissions/tests/${testId}/questions/${qid}`, { method: "DELETE" }); openTestReload(testId); load(); }
    catch (e) { err(e instanceof ApiError ? e.message : "Could not delete"); }
  }
  function openTestReload(id: string) { api<Test>(`/api/admissions/tests/${id}`).then(setDetail).catch(() => {}); }

  return (
    <div className="max-w-3xl space-y-6">
      <div className="text-sm"><Link href="/dashboard/admissions" className="text-ink-soft hover:underline">← Admissions</Link></div>
      <header>
        <h1 className="text-2xl font-bold">Entrance test</h1>
        <p className="text-ink-soft text-sm mt-1">Optional. Applicants sit an active test automatically when they apply — it’s auto-marked, and the score shows on each application.</p>
      </header>

      {/* create */}
      <div className="rounded-xl border border-line bg-card p-4 space-y-3">
        <p className="text-sm font-semibold">New entrance test</p>
        <div className="grid sm:grid-cols-3 gap-3">
          <div className="sm:col-span-1"><label className="block text-xs text-ink-soft mb-1">Title</label><input className={field} value={nt.title} onChange={e => setNt({ ...nt, title: e.target.value })} placeholder="Entrance exam" /></div>
          <div><label className="block text-xs text-ink-soft mb-1">For class</label>
            <select className={field} value={nt.applying_class_id} onChange={e => setNt({ ...nt, applying_class_id: e.target.value })}>
              <option value="">All applicants</option>{classes.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
          <div><label className="block text-xs text-ink-soft mb-1">Duration (min)</label><input type="number" min={1} className={field} value={nt.duration_minutes} onChange={e => setNt({ ...nt, duration_minutes: Number(e.target.value) })} /></div>
        </div>
        <button onClick={createTest} className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft">Create test</button>
      </div>

      {/* list */}
      {tests.length === 0 ? (
        <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-5">No entrance test yet. Create one above, or leave it off to admit without a test.</p>
      ) : tests.map((t) => (
        <div key={t.id} className="rounded-xl border border-line bg-card overflow-hidden">
          <div className="flex items-center justify-between gap-3 px-4 py-3">
            <button onClick={() => openTest(t.id)} className="text-left min-w-0">
              <p className="font-medium truncate">{t.title}
                {t.is_active && <span className="ml-2 inline-block rounded-full bg-ledger/10 text-ledger px-2 py-0.5 text-xs font-medium">Active</span>}</p>
              <p className="text-xs text-ink-soft">{t.applying_class ?? "All applicants"} · {t.question_count} questions · {t.total_marks} marks · {t.duration_minutes} min</p>
            </button>
            <button onClick={() => toggleActive(t)}
                    className={`shrink-0 rounded-md px-3 py-1.5 text-sm font-medium ${t.is_active ? "border border-sanction text-sanction hover:bg-sanction hover:text-white" : "bg-ledger text-white hover:opacity-90"}`}>
              {t.is_active ? "Deactivate" : "Activate"}</button>
          </div>

          {openId === t.id && (
            <div className="border-t border-line px-4 py-4 space-y-3">
              {!detail ? <p className="text-sm text-ink-soft"><span className="spinner" /> Loading…</p> : (
                <>
                  {(detail.questions ?? []).map((q, i) => (
                    <div key={q.id} className="rounded-lg border border-line p-3 flex items-start justify-between gap-3">
                      <div className="min-w-0"><p className="text-sm font-medium"><span className="text-ink-soft mr-1">{i + 1}.</span>{q.text}</p>
                        <p className="text-xs text-ink-soft mt-0.5">{TYPES.find(x => x.v === q.type)?.label} · {q.marks} mark{q.marks === 1 ? "" : "s"}</p></div>
                      <button onClick={() => delQuestion(t.id, q.id)} className="text-sanction text-sm font-medium hover:underline shrink-0">Delete</button>
                    </div>
                  ))}
                  {adding ? (
                    <QuestionEditor testId={t.id} onSaved={() => { setAdding(false); openTestReload(t.id); load(); }} onCancel={() => setAdding(false)} />
                  ) : (
                    <button onClick={() => setAdding(true)} className="rounded-md border border-ink text-ink px-4 py-2 text-sm font-medium hover:bg-ink hover:text-white">+ Add question</button>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
