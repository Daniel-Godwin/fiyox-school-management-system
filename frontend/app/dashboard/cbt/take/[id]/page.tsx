"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";

type Option = { id: string; text: string };
type Question = { id: string; type: string; text: string; marks: number; options: Option[] };
type StartPayload = {
  attempt_id: string;
  exam: { id: string; title: string; instructions: string; duration_minutes: number; total_marks: number };
  deadline_at: string | null; server_now: string;
  saved_answers: Record<string, unknown>; questions: Question[];
};
type Review = {
  exam_title: string; status: string; show_results: boolean;
  score?: number; max_score?: number; percent?: number;
  review?: { question: string; your_answer: unknown; correct: boolean; marks: number; max: number }[];
};
type SubmitResult = { status: string; show_results: boolean; score?: number; max_score?: number; percent?: number };

function fmt(sec: number) {
  const m = Math.floor(sec / 60), s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function TakeCBT() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const search = useSearchParams();
  const reviewId = search.get("review");
  const { ok, err } = useToast();

  const [data, setData] = useState<StartPayload | null>(null);
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  const [left, setLeft] = useState<number | null>(null);
  const [result, setResult] = useState<SubmitResult | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [fatal, setFatal] = useState<string | null>(null);

  const offsetRef = useRef(0);         // local clock - server clock, ms
  const deadlineRef = useRef<number | null>(null);
  const submittedRef = useRef(false);
  const answersRef = useRef(answers);
  answersRef.current = answers;

  // ---- review mode: just show a finished attempt ----
  useEffect(() => {
    if (!reviewId) return;
    api<Review>(`/api/cbt/attempts/${reviewId}`).then(setReview)
      .catch(() => setFatal("Could not load your result."));
  }, [reviewId]);

  const doSubmit = useCallback(async (auto: boolean) => {
    if (submittedRef.current || !data) return;
    submittedRef.current = true;
    setSubmitting(true);
    try {
      const res = await api<SubmitResult>(`/api/cbt/attempts/${data.attempt_id}/submit`, {
        method: "POST", body: JSON.stringify({ answers: answersRef.current, auto }) });
      setResult(res);
      if (auto) ok("Time's up — your test was submitted automatically.");
    } catch (e) {
      submittedRef.current = false;
      err(e instanceof ApiError ? e.message : "Could not submit. Try again.");
    }
    setSubmitting(false);
  }, [data, ok, err]);

  // ---- start (or resume) the sitting ----
  useEffect(() => {
    if (reviewId) return;
    let alive = true;
    api<StartPayload>(`/api/cbt/exams/${id}/start`, { method: "POST" })
      .then((d) => {
        if (!alive) return;
        setData(d);
        setAnswers(d.saved_answers || {});
        offsetRef.current = Date.now() - new Date(d.server_now).getTime();
        if (d.deadline_at) deadlineRef.current = new Date(d.deadline_at).getTime();
      })
      .catch((e) => setFatal(e instanceof ApiError ? e.message : "Could not start this test."));
    return () => { alive = false; };
  }, [id, reviewId]);

  // ---- countdown ----
  useEffect(() => {
    if (!data || deadlineRef.current === null || result) return;
    const tick = () => {
      const serverNow = Date.now() - offsetRef.current;
      const secs = Math.max(0, Math.round((deadlineRef.current! - serverNow) / 1000));
      setLeft(secs);
      if (secs <= 0 && !submittedRef.current) doSubmit(true);
    };
    tick();
    const h = setInterval(tick, 1000);
    return () => clearInterval(h);
  }, [data, result, doSubmit]);

  // ---- periodic autosave ----
  useEffect(() => {
    if (!data || result) return;
    const h = setInterval(() => {
      api(`/api/cbt/attempts/${data.attempt_id}/answer`, {
        method: "POST", body: JSON.stringify({ answers: answersRef.current }) }).catch(() => {});
    }, 20000);
    return () => clearInterval(h);
  }, [data, result]);

  function setAnswer(qid: string, value: unknown) {
    setAnswers((a) => ({ ...a, [qid]: value }));
  }

  if (fatal) {
    return (
      <div className="max-w-xl space-y-4">
        <p className="text-sm text-sanction border border-sanction/30 bg-sanction/5 rounded-lg p-4">{fatal}</p>
        <Link href="/dashboard/cbt" className="text-sm text-ink font-medium hover:underline">← Back to my tests</Link>
      </div>
    );
  }

  // ---- review screen ----
  if (reviewId) {
    if (!review) return <div className="grid place-items-center py-20 text-ink-soft text-sm"><span className="spinner" /> Loading…</div>;
    return (
      <div className="max-w-2xl space-y-5">
        <header>
          <h1 className="text-2xl font-bold">{review.exam_title}</h1>
          {review.show_results && review.score !== undefined ? (
            <p className="text-ink-soft mt-1">
              You scored <b className="text-ink">{review.score}/{review.max_score}</b> ({review.percent}%).
            </p>
          ) : <p className="text-ink-soft mt-1">Submitted. Your teacher will release the score.</p>}
        </header>
        {review.review && (
          <div className="space-y-2">
            {review.review.map((r, i) => (
              <div key={i} className={`rounded-lg border p-3 text-sm ${r.correct ? "border-ledger/30 bg-ledger/5" : "border-sanction/30 bg-sanction/5"}`}>
                <p className="font-medium">{r.correct ? "✓" : "✗"} {r.question}</p>
                <p className="text-xs text-ink-soft mt-1">{r.marks} / {r.max} marks</p>
              </div>
            ))}
          </div>
        )}
        <Link href="/dashboard/cbt" className="inline-block text-sm text-ink font-medium hover:underline">← Back to my tests</Link>
      </div>
    );
  }

  // ---- result screen (just submitted) ----
  if (result) {
    return (
      <div className="max-w-xl space-y-5 py-6">
        <div className="rounded-xl border border-ledger/30 bg-ledger/5 p-6 text-center">
          <p className="text-4xl mb-2">✓</p>
          <h1 className="text-xl font-bold">Test submitted</h1>
          {result.show_results && result.score !== undefined ? (
            <p className="text-ink-soft mt-2">
              You scored <b className="text-ink">{result.score}/{result.max_score}</b> — {result.percent}%.
            </p>
          ) : (
            <p className="text-ink-soft mt-2">Your answers are in. Your teacher will release the score.</p>
          )}
        </div>
        <Link href="/dashboard/cbt" className="inline-block text-sm text-ink font-medium hover:underline">← Back to my tests</Link>
      </div>
    );
  }

  if (!data) return <div className="grid place-items-center py-20 text-ink-soft text-sm"><span className="spinner" /> Preparing your test…</div>;

  const lowTime = left !== null && left <= 60;
  const answered = data.questions.filter((q) => {
    const v = answers[q.id];
    return Array.isArray(v) ? v.length > 0 : v !== undefined && v !== "";
  }).length;

  return (
    <div className="max-w-2xl space-y-5 pb-24">
      {/* sticky timer bar */}
      <div className="sticky top-0 z-20 -mx-4 sm:-mx-5 md:-mx-8 px-4 sm:px-5 md:px-8 py-3 bg-paper/95 backdrop-blur border-b border-line flex items-center justify-between">
        <div>
          <h1 className="font-bold leading-tight">{data.exam.title}</h1>
          <p className="text-xs text-ink-soft">{answered} of {data.questions.length} answered</p>
        </div>
        {left !== null && (
          <div className={`tabular font-bold text-lg px-3 py-1 rounded-md border ${lowTime ? "border-sanction text-sanction animate-pulse" : "border-line text-ink"}`}>
            {fmt(left)}
          </div>
        )}
      </div>

      {data.exam.instructions && (
        <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-3">{data.exam.instructions}</p>
      )}

      {data.questions.map((q, i) => (
        <div key={q.id} className="rounded-xl border border-line bg-card p-5">
          <p className="font-medium">
            <span className="text-ink-soft mr-1">{i + 1}.</span>{q.text}
            <span className="text-xs text-ink-soft ml-2">({q.marks} mark{q.marks === 1 ? "" : "s"})</span>
          </p>

          <div className="mt-3 space-y-2">
            {(q.type === "single" || q.type === "boolean") &&
              q.options.map((o) => (
                <label key={o.id} className="flex items-center gap-2.5 text-sm cursor-pointer rounded-md border border-line px-3 py-2 hover:border-ink has-[:checked]:border-ink has-[:checked]:bg-ink/5">
                  <input type="radio" name={q.id} checked={answers[q.id] === o.id}
                         onChange={() => setAnswer(q.id, o.id)} />
                  {o.text}
                </label>
              ))}

            {q.type === "multiple" &&
              q.options.map((o) => {
                const arr = (answers[q.id] as string[]) ?? [];
                return (
                  <label key={o.id} className="flex items-center gap-2.5 text-sm cursor-pointer rounded-md border border-line px-3 py-2 hover:border-ink has-[:checked]:border-ink has-[:checked]:bg-ink/5">
                    <input type="checkbox" checked={arr.includes(o.id)}
                           onChange={(e) => setAnswer(q.id, e.target.checked ? [...arr, o.id] : arr.filter((x) => x !== o.id))} />
                    {o.text}
                  </label>
                );
              })}

            {q.type === "short" && (
              <input className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm"
                     value={(answers[q.id] as string) ?? ""} placeholder="Type your answer"
                     onChange={(e) => setAnswer(q.id, e.target.value)} />
            )}
          </div>
        </div>
      ))}

      <div className="fixed bottom-0 inset-x-0 md:left-[230px] border-t border-line bg-card/95 backdrop-blur px-4 sm:px-6 py-3 flex items-center justify-between">
        <p className="text-sm text-ink-soft">{answered} of {data.questions.length} answered</p>
        <button onClick={() => doSubmit(false)} disabled={submitting}
                className="rounded-md bg-ink text-white px-6 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
          {submitting ? "Submitting…" : "Submit test"}
        </button>
      </div>
    </div>
  );
}
