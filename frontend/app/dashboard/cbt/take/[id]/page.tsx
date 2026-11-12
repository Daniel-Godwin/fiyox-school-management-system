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
  exam: {
    id: string; title: string; instructions: string; duration_minutes: number;
    total_marks: number; proctored?: boolean; max_violations?: number;
  };
  deadline_at: string | null; server_now: string; violation_count?: number;
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

// per-attempt offline answer cache (survives a dropped connection / refresh)
const lsKey = (aid: string) => `cbt_ans_${aid}`;
function loadLocal(aid: string): Record<string, unknown> | null {
  try { const s = localStorage.getItem(lsKey(aid)); return s ? JSON.parse(s) : null; } catch { return null; }
}
function saveLocal(aid: string, ans: unknown) {
  try { localStorage.setItem(lsKey(aid), JSON.stringify(ans)); } catch { /* ignore */ }
}
function clearLocal(aid: string) {
  try { localStorage.removeItem(lsKey(aid)); } catch { /* ignore */ }
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

  // proctoring
  const [started, setStarted] = useState(false);           // false = pre-start gate
  const [violations, setViolations] = useState(0);
  const [warning, setWarning] = useState<{ count: number; max: number } | null>(null);
  const [endedByViolation, setEndedByViolation] = useState(false);

  const offsetRef = useRef(0);
  const deadlineRef = useRef<number | null>(null);
  const submittedRef = useRef(false);
  const lastViolationRef = useRef(0);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const answersRef = useRef(answers);
  answersRef.current = answers;

  const proctored = !!data?.exam.proctored;

  // ---- review mode ----
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
      clearLocal(data.attempt_id);
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
      setResult(res);
      if (auto) ok("Time's up — your test was submitted automatically.");
    } catch (e) {
      submittedRef.current = false;
      err(e instanceof ApiError ? e.message : "Could not submit. Try again.");
    }
    setSubmitting(false);
  }, [data, ok, err]);

  // ---- start (or resume) ----
  useEffect(() => {
    if (reviewId) return;
    let alive = true;
    api<StartPayload>(`/api/cbt/exams/${id}/start`, { method: "POST" })
      .then((d) => {
        if (!alive) return;
        setData(d);
        // merge any unsynced offline answers over the server's copy
        const local = loadLocal(d.attempt_id);
        setAnswers({ ...(d.saved_answers || {}), ...(local || {}) });
        setViolations(d.violation_count || 0);
        setStarted(!d.exam.proctored);   // proctored tests wait for the full-screen gate
        offsetRef.current = Date.now() - new Date(d.server_now).getTime();
        if (d.deadline_at) deadlineRef.current = new Date(d.deadline_at).getTime();
      })
      .catch((e) => setFatal(e instanceof ApiError ? e.message : "Could not start this test."));
    return () => { alive = false; };
  }, [id, reviewId]);

  // ---- countdown (server-authoritative) ----
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

  // ---- save answers (10s heartbeat + on reconnect); offline-safe ----
  const pushSave = useCallback(async () => {
    if (!data || submittedRef.current) return;
    try {
      await api(`/api/cbt/attempts/${data.attempt_id}/answer`, {
        method: "POST", body: JSON.stringify({ answers: answersRef.current }) });
    } catch { /* offline — the answers stay cached locally and sync next time */ }
  }, [data]);

  useEffect(() => {
    if (!data || result) return;
    const h = setInterval(pushSave, 10000);
    const onOnline = () => pushSave();
    window.addEventListener("online", onOnline);
    return () => { clearInterval(h); window.removeEventListener("online", onOnline); };
  }, [data, result, pushSave]);

  function setAnswer(qid: string, value: unknown) {
    setAnswers((a) => {
      const next = { ...a, [qid]: value };
      if (data) saveLocal(data.attempt_id, next);     // cache immediately
      return next;
    });
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(pushSave, 1200);    // debounced background save
  }

  // ---- record an anti-cheat violation (server decides the auto-submit) ----
  const registerViolation = useCallback(async (kind: string) => {
    if (!data || submittedRef.current) return;
    const now = Date.now();
    if (now - lastViolationRef.current < 1200) return;  // collapse clustered events
    lastViolationRef.current = now;
    try {
      const r = await api<{ count: number; max: number; auto_submit: boolean }>(
        `/api/cbt/attempts/${data.attempt_id}/violation`,
        { method: "POST", body: JSON.stringify({ kind }) });
      setViolations(r.count);
      if (r.auto_submit) {
        submittedRef.current = true;
        if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
        setEndedByViolation(true);
      } else {
        setWarning({ count: r.count, max: r.max });
      }
    } catch { /* ignore — a lost beacon shouldn't break the sitting */ }
  }, [data]);

  // ---- proctoring: full-screen lock + action lock + tab-switch detection ----
  useEffect(() => {
    if (!proctored || !started || result || endedByViolation) return;
    const block = (e: Event) => e.preventDefault();
    const onKey = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      if (e.key === "F12"
        || (e.ctrlKey && e.shiftKey && ["i", "j", "c"].includes(k))
        || (e.ctrlKey && ["u", "s", "p", "c", "x", "v", "a"].includes(k))) {
        e.preventDefault();
      }
    };
    const onVis = () => { if (document.hidden) registerViolation("tab_switch"); };
    const onBlur = () => registerViolation("blur");
    document.addEventListener("contextmenu", block);
    document.addEventListener("copy", block);
    document.addEventListener("cut", block);
    document.addEventListener("paste", block);
    document.addEventListener("selectstart", block);
    document.addEventListener("keydown", onKey);
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("blur", onBlur);
    return () => {
      document.removeEventListener("contextmenu", block);
      document.removeEventListener("copy", block);
      document.removeEventListener("cut", block);
      document.removeEventListener("paste", block);
      document.removeEventListener("selectstart", block);
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("blur", onBlur);
    };
  }, [proctored, started, result, endedByViolation, registerViolation]);

  async function beginProctored() {
    try { await document.documentElement.requestFullscreen(); } catch { /* allowed to fail */ }
    setStarted(true);
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

  // ---- ended by too many violations ----
  if (endedByViolation) {
    return (
      <div className="max-w-xl space-y-5 py-6">
        <div className="rounded-xl border border-sanction/30 bg-sanction/5 p-6 text-center">
          <p className="text-4xl mb-2">⚠️</p>
          <h1 className="text-xl font-bold">Test submitted</h1>
          <p className="text-ink-soft mt-2">
            Your test left full screen too many times and was submitted automatically.
            Your teacher can see the record.
          </p>
        </div>
        <Link href="/dashboard/cbt" className="inline-block text-sm text-ink font-medium hover:underline">← Back to my tests</Link>
      </div>
    );
  }

  // ---- result screen ----
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

  // ---- proctored pre-start gate (needed for a user gesture to enter full screen) ----
  if (proctored && !started) {
    return (
      <div className="max-w-lg mx-auto py-10 space-y-5">
        <div className="rounded-xl border border-brass/40 bg-brass/10 p-6 space-y-3">
          <h1 className="text-xl font-bold">{data.exam.title}</h1>
          <p className="text-sm text-ink">This is a <strong>proctored test</strong>. When you begin:</p>
          <ul className="text-sm text-ink-soft list-disc pl-5 space-y-1">
            <li>It opens in full screen, and copy / paste / right-click are disabled.</li>
            <li>Leaving the test (switching tab or app) is recorded.</li>
            <li>After {data.exam.max_violations ?? 3} times, your test is submitted automatically.</li>
          </ul>
          {data.exam.instructions && (
            <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-3">{data.exam.instructions}</p>
          )}
          <button onClick={beginProctored}
                  className="rounded-md bg-ink text-white px-6 py-2.5 text-sm font-medium hover:bg-ink-soft">
            Enter full screen & begin
          </button>
        </div>
        <Link href="/dashboard/cbt" className="inline-block text-sm text-ink-soft hover:text-ink">← Not now</Link>
      </div>
    );
  }

  const lowTime = left !== null && left <= 60;
  const answered = data.questions.filter((q) => {
    const v = answers[q.id];
    return Array.isArray(v) ? v.length > 0 : v !== undefined && v !== "";
  }).length;

  return (
    <div className={`max-w-2xl space-y-5 pb-24 ${proctored ? "select-none" : ""}`}>
      {/* sticky timer bar */}
      <div className="sticky top-0 z-20 -mx-4 sm:-mx-5 md:-mx-8 px-4 sm:px-5 md:px-8 py-3 bg-paper/95 backdrop-blur border-b border-line flex items-center justify-between">
        <div>
          <h1 className="font-bold leading-tight">{data.exam.title}</h1>
          <p className="text-xs text-ink-soft">
            {answered} of {data.questions.length} answered
            {proctored && violations > 0 && (
              <span className="text-sanction"> · {violations} warning{violations === 1 ? "" : "s"}</span>
            )}
          </p>
        </div>
        {left !== null && (
          <div className={`tabular font-bold text-lg px-3 py-1 rounded-md border ${lowTime ? "border-sanction text-sanction animate-pulse" : "border-line text-ink"}`}>
            {fmt(left)}
          </div>
        )}
      </div>

      {data.exam.instructions && !proctored && (
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

      {/* violation warning modal */}
      {warning && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 px-4">
          <div className="bg-card rounded-xl border border-sanction/40 p-6 max-w-sm w-full space-y-3 text-center">
            <p className="text-3xl">⚠️</p>
            <h2 className="text-lg font-bold">Stay on the test</h2>
            <p className="text-sm text-ink-soft">
              Leaving the test was recorded (warning {warning.count} of {warning.max}).
              {warning.count >= warning.max - 1
                ? " One more and your test will be submitted automatically."
                : " Please don't switch tabs or apps."}
            </p>
            <button onClick={() => setWarning(null)}
                    className="rounded-md bg-ink text-white px-5 py-2 text-sm font-medium hover:bg-ink-soft">
              I understand
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
