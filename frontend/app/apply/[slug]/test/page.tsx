"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";

type Option = { id: string; text: string };
type Question = { id: string; type: string; text: string; marks: number; options: Option[] };
type Start = {
  title: string; instructions: string; duration_minutes: number;
  total_marks: number; questions: Question[]; server_now: string;
};
type Result = { submitted: boolean; message: string };

function fmt(s: number) { const m = Math.floor(s / 60); return `${m}:${String(s % 60).padStart(2, "0")}`; }

function TestInner() {
  const { slug } = useParams<{ slug: string }>();
  const search = useSearchParams();
  const app = search.get("app") ?? "";
  const code = search.get("code") ?? "";
  const creds = { application_number: app, access_code: code };

  const [data, setData] = useState<Start | null>(null);
  const [phase, setPhase] = useState<"intro" | "taking">("intro");
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  const [left, setLeft] = useState<number | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const submittedRef = useRef(false);
  const answersRef = useRef(answers); answersRef.current = answers;
  const deadlineRef = useRef<number | null>(null);
  const offsetRef = useRef(0);

  const doSubmit = useCallback(async (auto: boolean) => {
    if (submittedRef.current || !data) return;
    submittedRef.current = true; setSubmitting(true);
    try {
      const r = await api<Result>(`/api/admissions/${slug}/test/submit`, {
        method: "POST", body: JSON.stringify({ ...creds, answers: answersRef.current, auto }) });
      setResult(r);
    } catch (e) {
      submittedRef.current = false;
      setFatal(e instanceof ApiError ? e.message : "Could not submit. Try again.");
    }
    setSubmitting(false);
  }, [data, slug]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!app || !code) { setFatal("Missing application number or code."); return; }
    api<Start>(`/api/admissions/${slug}/test/start`, { method: "POST", body: JSON.stringify(creds) })
      .then((d) => setData(d))   // show the instructions first; the clock waits for "Start"
      .catch((e) => setFatal(e instanceof ApiError ? e.message : "Could not start the test."));
  }, [slug, app, code]); // eslint-disable-line react-hooks/exhaustive-deps

  // the countdown begins only when the applicant clicks "Start exam"
  function startExam() {
    if (!data) return;
    deadlineRef.current = Date.now() + data.duration_minutes * 60000;
    setPhase("taking");
  }

  useEffect(() => {
    if (phase !== "taking" || !data || deadlineRef.current === null || result) return;
    const tick = () => {
      const now = Date.now() - offsetRef.current;
      const secs = Math.max(0, Math.round((deadlineRef.current! - now) / 1000));
      setLeft(secs);
      if (secs <= 0 && !submittedRef.current) doSubmit(true);
    };
    tick();
    const h = setInterval(tick, 1000);
    return () => clearInterval(h);
  }, [phase, data, result, doSubmit]);

  function setAnswer(q: string, v: unknown) { setAnswers((a) => ({ ...a, [q]: v })); }

  if (fatal) return (
    <main className="min-h-screen grid place-items-center bg-paper px-5">
      <div className="max-w-md text-center space-y-3">
        <p className="text-sm text-sanction border border-sanction/30 bg-sanction/5 rounded-lg p-4">{fatal}</p>
        <Link href={`/apply/${slug}`} className="text-sm text-ink font-medium hover:underline">← Back to admissions</Link>
      </div>
    </main>
  );

  if (result) return (
    <main className="min-h-screen grid place-items-center bg-paper px-5">
      <div className="max-w-md w-full bg-card border border-ledger/30 rounded-xl p-6 text-center">
        <p className="text-4xl mb-2">✓</p>
        <h1 className="text-xl font-bold">Entrance test submitted</h1>
        <p className="text-ink-soft text-sm mt-2">{result.message}</p>
        <Link href={`/apply/${slug}`} className="mt-4 inline-block text-sm text-ink font-medium hover:underline">← Back to admissions</Link>
      </div>
    </main>
  );

  if (!data) return <main className="min-h-screen grid place-items-center bg-paper text-ink-soft text-sm"><span className="spinner" /> Loading the test…</main>;

  // instructions screen — the clock does not run until the applicant starts
  if (phase === "intro") return (
    <main className="min-h-screen bg-paper">
      <header className="bg-ink text-white">
        <div className="mx-auto max-w-2xl px-5 py-4"><h1 className="font-bold">{data.title}</h1>
          <p className="text-xs text-white/70">Entrance test</p></div>
      </header>
      <div className="mx-auto max-w-2xl px-5 py-8">
        <div className="bg-card border border-line rounded-xl p-6 card space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-line p-3"><p className="text-xs text-ink-soft">Questions</p><p className="font-bold text-lg tabular">{data.questions.length}</p></div>
            <div className="rounded-lg border border-line p-3"><p className="text-xs text-ink-soft">Time limit</p><p className="font-bold text-lg tabular">{data.duration_minutes} min</p></div>
          </div>
          <div>
            <p className="font-semibold mb-1">Instructions</p>
            <p className="text-sm text-ink-soft whitespace-pre-line">
              {data.instructions || "Answer all the questions. Once you start, the timer runs continuously and the test submits automatically when the time is up."}
            </p>
          </div>
          <p className="text-sm text-sanction">The countdown begins when you click Start. Make sure you are ready and have a steady connection.</p>
          <button onClick={startExam} className="rounded-md bg-ink text-white px-6 py-2.5 text-sm font-medium hover:bg-ink-soft">Start exam</button>
        </div>
        <p className="text-center text-xs text-ink-soft mt-6">Powered by Fiyox</p>
      </div>
    </main>
  );

  const lowTime = left !== null && left <= 60;
  const answered = data.questions.filter((q) => { const v = answers[q.id]; return Array.isArray(v) ? v.length > 0 : v !== undefined && v !== ""; }).length;

  return (
    <main className="min-h-screen bg-paper pb-24">
      <div className="sticky top-0 z-20 bg-ink text-white">
        <div className="mx-auto max-w-2xl px-5 py-3 flex items-center justify-between">
          <div><h1 className="font-bold leading-tight">{data.title}</h1>
            <p className="text-xs text-white/70">{answered} of {data.questions.length} answered</p></div>
          {left !== null && <div className={`tabular font-bold text-lg px-3 py-1 rounded-md ${lowTime ? "bg-sanction animate-pulse" : "bg-white/15"}`}>{fmt(left)}</div>}
        </div>
      </div>

      <div className="mx-auto max-w-2xl px-5 py-5 space-y-4">
        {data.instructions && <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-3 bg-card">{data.instructions}</p>}
        {data.questions.map((q, i) => (
          <div key={q.id} className="rounded-xl border border-line bg-card p-5">
            <p className="font-medium"><span className="text-ink-soft mr-1">{i + 1}.</span>{q.text}
              <span className="text-xs text-ink-soft ml-2">({q.marks} mark{q.marks === 1 ? "" : "s"})</span></p>
            <div className="mt-3 space-y-2">
              {(q.type === "single" || q.type === "boolean") && q.options.map((o) => (
                <label key={o.id} className="flex items-center gap-2.5 text-sm cursor-pointer rounded-md border border-line px-3 py-2 hover:border-ink has-[:checked]:border-ink has-[:checked]:bg-ink/5">
                  <input type="radio" name={q.id} checked={answers[q.id] === o.id} onChange={() => setAnswer(q.id, o.id)} />{o.text}</label>
              ))}
              {q.type === "multiple" && q.options.map((o) => {
                const arr = (answers[q.id] as string[]) ?? [];
                return <label key={o.id} className="flex items-center gap-2.5 text-sm cursor-pointer rounded-md border border-line px-3 py-2 hover:border-ink has-[:checked]:border-ink has-[:checked]:bg-ink/5">
                  <input type="checkbox" checked={arr.includes(o.id)} onChange={(e) => setAnswer(q.id, e.target.checked ? [...arr, o.id] : arr.filter((x) => x !== o.id))} />{o.text}</label>;
              })}
              {q.type === "short" && <input className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm" value={(answers[q.id] as string) ?? ""} placeholder="Type your answer" onChange={(e) => setAnswer(q.id, e.target.value)} />}
            </div>
          </div>
        ))}
      </div>

      <div className="fixed bottom-0 inset-x-0 border-t border-line bg-card/95 backdrop-blur px-5 py-3">
        <div className="mx-auto max-w-2xl flex items-center justify-between">
          <p className="text-sm text-ink-soft">{answered} of {data.questions.length} answered</p>
          <button onClick={() => doSubmit(false)} disabled={submitting}
                  className="rounded-md bg-ink text-white px-6 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
            {submitting ? "Submitting…" : "Submit test"}</button>
        </div>
      </div>
    </main>
  );
}

export default function EntranceTestPage() {
  return (
    <Suspense fallback={<main className="min-h-screen grid place-items-center bg-paper text-ink-soft text-sm">Loading…</main>}>
      <TestInner />
    </Suspense>
  );
}
