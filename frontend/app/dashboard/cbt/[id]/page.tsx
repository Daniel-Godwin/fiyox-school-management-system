"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";

type Option = { id: string; text: string };
type Question = {
  id: string; type: string; text: string; options: Option[];
  correct: unknown; marks: number; sequence: number;
};
type Exam = {
  id: string; title: string; instructions: string; status: string;
  subject_id: string; subject_name: string | null; class_label: string | null;
  duration_minutes: number; max_attempts: number;
  shuffle_questions: boolean; show_results_immediately: boolean;
  total_marks: number; question_count: number; questions: Question[];
  component_id: string | null; component_name: string | null;
  source: string; pool_size: number; difficulty_ratio: Record<string, number>;
};
type Component = { id: string; name: string; max_score: number };
type BankSummary = { easy: number; medium: number; hard: number; total: number };

// largest-remainder split — mirrors the backend's pool balancing
function splitPool(poolSize: number, ratio: Record<string, number>) {
  const r = { easy: ratio.easy ?? 0, medium: ratio.medium ?? 0, hard: ratio.hard ?? 0 };
  const total = (r.easy + r.medium + r.hard) || 1;
  const raw = {
    easy: (poolSize * r.easy) / total,
    medium: (poolSize * r.medium) / total,
    hard: (poolSize * r.hard) / total,
  };
  const base = { easy: Math.floor(raw.easy), medium: Math.floor(raw.medium), hard: Math.floor(raw.hard) };
  let rem = poolSize - base.easy - base.medium - base.hard;
  const diffs: ("easy" | "medium" | "hard")[] = ["easy", "medium", "hard"];
  diffs.sort((a, b) => (raw[b] - base[b]) - (raw[a] - base[a]))
    .forEach((d) => { if (rem-- > 0) base[d]++; });
  return base;
}

const TYPES = [
  { v: "single", label: "Single choice" },
  { v: "multiple", label: "Multiple answers" },
  { v: "boolean", label: "True / False" },
  { v: "short", label: "Short answer" },
];
const field = "w-full rounded-md border border-line bg-white px-3 py-2 text-sm";

function typeLabel(t: string) {
  return TYPES.find((x) => x.v === t)?.label ?? t;
}

/* ---------- question editor (add or edit one question) ---------- */
function QuestionEditor({ examId, initial, onSaved, onCancel }: {
  examId: string; initial: Question | null;
  onSaved: () => void; onCancel: () => void;
}) {
  const { err } = useToast();
  const [type, setType] = useState(initial?.type ?? "single");
  const [text, setText] = useState(initial?.text ?? "");
  const [marks, setMarks] = useState(initial?.marks ?? 1);
  const [options, setOptions] = useState<Option[]>(
    initial && (initial.type === "single" || initial.type === "multiple")
      ? initial.options
      : [{ id: "o1", text: "" }, { id: "o2", text: "" }]);
  const [single, setSingle] = useState<string>(
    initial?.type === "single" ? String(initial.correct ?? "") : "");
  const [multi, setMulti] = useState<string[]>(
    initial?.type === "multiple" ? (initial.correct as string[]) ?? [] : []);
  const [bool, setBool] = useState<boolean>(
    initial?.type === "boolean" ? Boolean(initial.correct) : true);
  const [short, setShort] = useState<string>(
    initial?.type === "short" ? ((initial.correct as string[]) ?? []).join(", ") : "");
  const [saving, setSaving] = useState(false);

  function addOption() {
    const n = options.reduce((m, o) => Math.max(m, Number(o.id.replace("o", "")) || 0), 0) + 1;
    setOptions([...options, { id: `o${n}`, text: "" }]);
  }
  function removeOption(id: string) {
    setOptions(options.filter((o) => o.id !== id));
    setSingle((s) => (s === id ? "" : s));
    setMulti((m) => m.filter((x) => x !== id));
  }

  async function save() {
    if (!text.trim()) return err("Write the question text");
    const body: Record<string, unknown> = { type, text: text.trim(), marks: Number(marks) };
    if (type === "single" || type === "multiple") {
      const cleaned = options.filter((o) => o.text.trim());
      if (cleaned.length < 2) return err("Give at least two options");
      body.options = cleaned;
      if (type === "single") {
        if (!single || !cleaned.some((o) => o.id === single)) return err("Mark the correct option");
        body.correct = single;
      } else {
        const chosen = multi.filter((id) => cleaned.some((o) => o.id === id));
        if (chosen.length === 0) return err("Tick at least one correct answer");
        body.correct = chosen;
      }
    } else if (type === "boolean") {
      body.correct = bool;
    } else {
      const accepted = short.split(",").map((s) => s.trim()).filter(Boolean);
      if (accepted.length === 0) return err("Give at least one accepted answer");
      body.correct = accepted;
    }

    setSaving(true);
    try {
      if (initial) {
        await api(`/api/cbt/exams/${examId}/questions/${initial.id}`, {
          method: "PATCH", body: JSON.stringify(body) });
      } else {
        await api(`/api/cbt/exams/${examId}/questions`, {
          method: "POST", body: JSON.stringify(body) });
      }
      onSaved();
    } catch (e) {
      err(e instanceof ApiError ? e.message : "Could not save the question");
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border border-ink/30 bg-paper/60 p-4 space-y-3">
      <div className="grid sm:grid-cols-[1fr_auto] gap-3">
        <div>
          <label className="block text-xs font-medium mb-1 text-ink-soft">Type</label>
          <select className={field} value={type} onChange={(e) => setType(e.target.value)}>
            {TYPES.map((t) => <option key={t.v} value={t.v}>{t.label}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium mb-1 text-ink-soft">Marks</label>
          <input type="number" min={1} step={1} className={`${field} w-24`} value={marks}
                 onChange={(e) => setMarks(Number(e.target.value))} />
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium mb-1 text-ink-soft">Question</label>
        <textarea className={`${field} min-h-[60px]`} value={text}
                  onChange={(e) => setText(e.target.value)} />
      </div>

      {(type === "single" || type === "multiple") && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-ink-soft">
            Options — {type === "single" ? "pick the one correct answer" : "tick every correct answer"}
          </p>
          {options.map((o) => (
            <div key={o.id} className="flex items-center gap-2">
              {type === "single" ? (
                <input type="radio" name="correct" checked={single === o.id}
                       onChange={() => setSingle(o.id)} />
              ) : (
                <input type="checkbox" checked={multi.includes(o.id)}
                       onChange={(e) => setMulti(e.target.checked
                         ? [...multi, o.id] : multi.filter((x) => x !== o.id))} />
              )}
              <input className={field} value={o.text} placeholder="Option text"
                     onChange={(e) => setOptions(options.map((x) =>
                       x.id === o.id ? { ...x, text: e.target.value } : x))} />
              {options.length > 2 && (
                <button onClick={() => removeOption(o.id)}
                        className="text-sanction text-sm px-2" aria-label="Remove option">✕</button>
              )}
            </div>
          ))}
          <button onClick={addOption} className="text-sm text-ink font-medium hover:underline">
            + Add option
          </button>
        </div>
      )}

      {type === "boolean" && (
        <div className="flex gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input type="radio" checked={bool} onChange={() => setBool(true)} /> True is correct
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" checked={!bool} onChange={() => setBool(false)} /> False is correct
          </label>
        </div>
      )}

      {type === "short" && (
        <div>
          <label className="block text-xs font-medium mb-1 text-ink-soft">
            Accepted answers (comma-separated — matching ignores case and spacing)
          </label>
          <input className={field} value={short} onChange={(e) => setShort(e.target.value)}
                 placeholder="e.g. 8, eight" />
        </div>
      )}

      <div className="flex gap-2 pt-1">
        <button onClick={save} disabled={saving}
                className="rounded-md bg-ink text-white px-4 py-1.5 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
          {saving ? "Saving…" : initial ? "Save changes" : "Add question"}
        </button>
        <button onClick={onCancel}
                className="rounded-md border border-line px-4 py-1.5 text-sm font-medium hover:border-ink">
          Cancel
        </button>
      </div>
    </div>
  );
}

/* ---------- a published/read-only summary of one question ---------- */
function correctSummary(q: Question): string {
  if (q.type === "single") {
    const o = q.options.find((x) => x.id === q.correct);
    return o ? o.text : String(q.correct);
  }
  if (q.type === "multiple") {
    const ids = (q.correct as string[]) ?? [];
    return q.options.filter((o) => ids.includes(o.id)).map((o) => o.text).join(", ");
  }
  if (q.type === "boolean") return q.correct ? "True" : "False";
  if (q.type === "short") return ((q.correct as string[]) ?? []).join(" / ");
  return "";
}

/* ---------- page ---------- */
export default function CBTBuilder() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { ok, err } = useToast();
  const [exam, setExam] = useState<Exam | null>(null);
  const [components, setComponents] = useState<Component[]>([]);
  const [bank, setBank] = useState<BankSummary | null>(null);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<Exam>(`/api/cbt/exams/${id}`).then(setExam)
      .catch(() => err("Could not load this test"));
  }, [id, err]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api<Component[]>("/api/assessment-components").then(setComponents).catch(() => {});
  }, []);
  // for pool exams, keep an eye on whether the bank can fill the draw
  useEffect(() => {
    if (exam?.source === "pool" && exam.subject_id) {
      api<BankSummary>(`/api/cbt/bank/summary?subject_id=${exam.subject_id}`)
        .then(setBank).catch(() => setBank(null));
    }
  }, [exam?.source, exam?.subject_id]);

  async function setComponent(componentId: string) {
    try {
      await api(`/api/cbt/exams/${id}`, {
        method: "PATCH", body: JSON.stringify({ component_id: componentId || null }) });
      load();
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not update"); }
  }

  if (!exam) {
    return <div className="grid place-items-center py-20 text-ink-soft text-sm">
      <span className="spinner" /> Loading…</div>;
  }

  const isDraft = exam.status === "draft";
  const isPool = exam.source === "pool";
  const want = isPool ? splitPool(exam.pool_size, exam.difficulty_ratio) : null;
  const bankEnough = !!(bank && want
    && bank.easy >= want.easy && bank.medium >= want.medium && bank.hard >= want.hard);
  // manual exams need attached questions; pool exams need a sufficient bank
  const canPublish = isPool ? bankEnough : exam.questions.length > 0;

  async function publish() {
    setBusy(true);
    try {
      await api(`/api/cbt/exams/${id}/publish`, { method: "POST" });
      ok("Test published — students in this class can now sit it.");
      load();
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not publish"); }
    setBusy(false);
  }
  async function close() {
    setBusy(true);
    try {
      await api(`/api/cbt/exams/${id}/close`, { method: "POST" });
      ok("Test closed — no new sittings can begin.");
      load();
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not close"); }
    setBusy(false);
  }
  async function removeQuestion(qid: string) {
    try {
      await api(`/api/cbt/exams/${id}/questions/${qid}`, { method: "DELETE" });
      load();
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not delete"); }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div className="text-sm">
        <Link href="/dashboard/cbt" className="text-ink-soft hover:underline">← All tests</Link>
      </div>

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold break-words">{exam.title}</h1>
          <p className="text-ink-soft text-sm mt-1">
            {exam.subject_name ?? "—"} · {exam.class_label ?? "—"} · {exam.duration_minutes} min ·
            {" "}{isPool && isDraft
              ? `${exam.pool_size} from the bank`
              : `${exam.question_count} questions · ${exam.total_marks} marks`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {exam.status === "published" && (
            <Link href={`/dashboard/cbt/${id}/monitor`}
                  className="rounded-md border border-ink text-ink px-4 py-2 text-sm font-medium hover:bg-ink hover:text-white">
              Monitor live
            </Link>
          )}
          <Link href={`/dashboard/cbt/${id}/results`}
                className="rounded-md border border-ledger text-ledger px-4 py-2 text-sm font-medium hover:bg-ledger hover:text-white">
            Results
          </Link>
          {isDraft ? (
            <button onClick={publish} disabled={busy || !canPublish}
                    title={!canPublish
                      ? (isPool ? "Add enough questions to the bank first" : "Add at least one question first")
                      : undefined}
                    className="rounded-md bg-ledger text-white px-4 py-2 text-sm font-medium hover:opacity-90 disabled:opacity-40">
              Publish
            </button>
          ) : exam.status === "published" ? (
            <button onClick={close} disabled={busy}
                    className="rounded-md border border-sanction text-sanction px-4 py-2 text-sm font-medium hover:bg-sanction hover:text-white disabled:opacity-40">
              Close test
            </button>
          ) : (
            <span className="rounded-full border border-line px-3 py-1 text-xs text-ink-soft">Closed</span>
          )}
        </div>
      </header>

      {!isDraft && (
        <p className="text-sm rounded-lg border border-ledger/30 bg-ledger/5 text-ink-soft p-3">
          This test is <b className="text-ledger">{exam.status}</b>. Questions are locked.
          {exam.status === "published" && " Close it first if you need to make changes."}
        </p>
      )}

      {exam.instructions && (
        <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-3">
          <span className="font-medium text-ink">Instructions: </span>{exam.instructions}
        </p>
      )}

      {/* result-sheet mapping */}
      <div className="rounded-lg border border-line bg-card p-4">
        <p className="text-sm font-medium">Counts towards (result sheet)</p>
        {isDraft ? (
          <>
            <select value={exam.component_id ?? ""}
                    onChange={(e) => setComponent(e.target.value)}
                    className="mt-2 w-full max-w-sm rounded-md border border-line bg-white px-3 py-2 text-sm">
              <option value="">Practice only — does not count</option>
              {components.map((c) => (
                <option key={c.id} value={c.id}>{c.name} (max {c.max_score})</option>
              ))}
            </select>
            <p className="text-xs text-ink-soft mt-1">
              When set, each student&apos;s score is scaled to this column and recorded
              in their report card automatically when they submit.
            </p>
          </>
        ) : (
          <p className="text-sm text-ink-soft mt-1">
            {exam.component_name
              ? <>Scores record into <span className="font-medium text-ledger">{exam.component_name}</span> on the result sheet.</>
              : "Practice only — scores are not written to the result sheet."}
          </p>
        )}
      </div>

      {/* pool exams draw from the bank — no questions are attached to the exam itself */}
      {isPool && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-ink-soft uppercase tracking-wide">
            Questions — drawn from the bank
          </h2>
          <div className="rounded-lg border border-line bg-card p-4 space-y-3">
            <p className="text-sm">
              Each student gets a unique, balanced set of{" "}
              <span className="font-medium">{exam.pool_size}</span> question{exam.pool_size === 1 ? "" : "s"}
              {" "}drawn from the {exam.subject_name ?? "subject"} bank when they start.
            </p>
            {want && (
              <p className="text-xs text-ink-soft">
                Needs <strong>{want.easy}</strong> easy · <strong>{want.medium}</strong> medium ·{" "}
                <strong>{want.hard}</strong> hard
                {bank !== null && (
                  <> — bank has {bank.easy} · {bank.medium} · {bank.hard} ({bank.total} total){" "}
                    {bankEnough
                      ? <span className="text-ledger font-medium">✓ enough to publish</span>
                      : <span className="text-sanction font-medium">— add more before publishing</span>}
                  </>
                )}
                {bank === null && " — checking the bank…"}
              </p>
            )}
            {isDraft && (
              <a href="/dashboard/cbt/bank"
                 className="inline-block rounded-md border border-ink text-ink px-4 py-2 text-sm font-medium hover:bg-ink hover:text-white">
                Manage question bank →
              </a>
            )}
          </div>
          {isDraft && !bankEnough && bank !== null && (
            <p className="text-sm rounded-lg border border-sanction/30 bg-sanction/5 text-ink-soft p-3">
              The bank doesn&apos;t yet hold enough questions for this draw, so Publish is disabled.
              Add questions to the bank (you can bulk-import a Word or PDF), then come back here to publish.
            </p>
          )}
        </section>
      )}

      {/* manual exams: author questions directly on the exam */}
      {!isPool && (
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-ink-soft uppercase tracking-wide">
          Questions ({exam.questions.length})
        </h2>

        {exam.questions.length === 0 && !adding && (
          <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-5">
            No questions yet. Add some below, then publish.
          </p>
        )}

        {exam.questions.map((q, i) =>
          editingId === q.id ? (
            <QuestionEditor key={q.id} examId={id} initial={q}
                            onSaved={() => { setEditingId(null); load(); }}
                            onCancel={() => setEditingId(null)} />
          ) : (
            <div key={q.id} className="rounded-lg border border-line bg-card p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium">
                    <span className="text-ink-soft mr-1">{i + 1}.</span>{q.text}
                  </p>
                  <p className="text-xs text-ink-soft mt-1">
                    {typeLabel(q.type)} · {q.marks} mark{q.marks === 1 ? "" : "s"} ·
                    {" "}answer: <span className="text-ledger font-medium">{correctSummary(q)}</span>
                  </p>
                </div>
                {isDraft && (
                  <div className="flex gap-3 shrink-0 text-sm">
                    <button onClick={() => setEditingId(q.id)}
                            className="text-ink font-medium hover:underline">Edit</button>
                    <button onClick={() => removeQuestion(q.id)}
                            className="text-sanction font-medium hover:underline">Delete</button>
                  </div>
                )}
              </div>
            </div>
          )
        )}

        {isDraft && (adding ? (
          <QuestionEditor examId={id} initial={null}
                          onSaved={() => { setAdding(false); load(); }}
                          onCancel={() => setAdding(false)} />
        ) : (
          <button onClick={() => setAdding(true)}
                  className="rounded-md border border-ink text-ink px-4 py-2 text-sm font-medium hover:bg-ink hover:text-white">
            + Add question
          </button>
        ))}
      </section>
      )}
    </div>
  );
}
