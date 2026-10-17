"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, me } from "@/lib/api";

type Me = { role: string };

type StaffExam = {
  id: string; title: string; subject_name: string | null; class_label: string | null;
  status: string; total_marks: number; question_count: number;
  duration_minutes: number;
};

type AvailExam = {
  id: string; title: string; subject_name: string | null;
  duration_minutes: number; question_count: number; total_marks: number;
  open_now: boolean; can_start: boolean; attempts_used: number; max_attempts: number;
  in_progress_attempt: string | null; last_attempt_id: string | null;
  last_status: string | null; show_results: boolean;
  opens_at: string | null; closes_at: string | null;
};

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-brass/15 text-brass-ink border-brass/30",
  published: "bg-ledger/10 text-ledger border-ledger/30",
  closed: "bg-ink/10 text-ink-soft border-line",
};

function Badge({ status }: { status: string }) {
  return (
    <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${STATUS_STYLE[status] ?? "border-line"}`}>
      {status}
    </span>
  );
}

export default function CBTLanding() {
  const [user, setUser] = useState<Me | null>(null);
  const [exams, setExams] = useState<StaffExam[] | null>(null);
  const [avail, setAvail] = useState<AvailExam[] | null>(null);

  useEffect(() => {
    me().then((u) => {
      setUser(u);
      if (u.role === "student") {
        api<AvailExam[]>("/api/cbt/available").then(setAvail).catch(() => setAvail([]));
      } else {
        api<StaffExam[]>("/api/cbt/exams").then(setExams).catch(() => setExams([]));
      }
    });
  }, []);

  if (!user) {
    return (
      <div className="grid place-items-center py-20 text-ink-soft text-sm">
        <span className="spinner" /> Loading tests…
      </div>
    );
  }

  // ---------------- student view ----------------
  if (user.role === "student") {
    return (
      <div className="max-w-3xl space-y-6">
        <header>
          <h1 className="text-2xl font-bold">My tests</h1>
          <p className="text-ink-soft text-sm mt-1">
            Computer-based tests set for your class. Each one is timed — once you
            start, the clock keeps running.
          </p>
        </header>

        {avail === null ? (
          <p className="text-ink-soft text-sm"><span className="spinner" /> Loading…</p>
        ) : avail.length === 0 ? (
          <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-6">
            No tests are open for you right now. Check back when your teacher sets one.
          </p>
        ) : (
          <div className="grid gap-4">
            {avail.map((e) => {
              const done = e.last_status === "submitted" && !e.in_progress_attempt;
              return (
                <div key={e.id} className="bg-card border border-line rounded-xl p-5 card">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h2 className="font-semibold">{e.title}</h2>
                      <p className="text-sm text-ink-soft mt-0.5">
                        {e.subject_name ?? "—"} · {e.question_count} questions ·
                        {" "}{e.total_marks} marks · {e.duration_minutes} min
                      </p>
                      <p className="text-xs text-ink-soft mt-1">
                        Attempt {Math.min(e.attempts_used + (done ? 0 : 1), e.max_attempts)} of {e.max_attempts}
                      </p>
                    </div>
                    <div className="shrink-0">
                      {e.in_progress_attempt ? (
                        <Link href={`/dashboard/cbt/take/${e.id}`}
                              className="rounded-md bg-brass text-white px-4 py-2 text-sm font-medium hover:opacity-90">
                          Resume
                        </Link>
                      ) : e.can_start ? (
                        <Link href={`/dashboard/cbt/take/${e.id}`}
                              className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft">
                          Start test
                        </Link>
                      ) : done && e.show_results && e.last_attempt_id ? (
                        <Link href={`/dashboard/cbt/take/${e.id}?review=${e.last_attempt_id}`}
                              className="rounded-md border border-ink text-ink px-4 py-2 text-sm font-medium hover:bg-ink hover:text-white">
                          See result
                        </Link>
                      ) : (
                        <span className="text-xs text-ink-soft">
                          {done ? "Submitted" : !e.open_now ? "Not open" : "No attempts left"}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  // ---------------- staff / oversight view ----------------
  const canAuthor = user.role === "teacher" || user.role === "school_admin" || user.role === "super_admin";
  return (
    <div className="max-w-4xl space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Computer-based tests</h1>
          <p className="text-ink-soft text-sm mt-1">
            {canAuthor
              ? "Build timed objective tests, publish them to a class, and let Fiyox mark every sitting automatically."
              : "Oversight of every test set in the school, and how each class performed."}
          </p>
        </div>
        {canAuthor && (
          <Link href="/dashboard/cbt/new"
                className="shrink-0 rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft">
            + New test
          </Link>
        )}
      </header>

      {exams === null ? (
        <p className="text-ink-soft text-sm"><span className="spinner" /> Loading…</p>
      ) : exams.length === 0 ? (
        <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-6 max-w-xl">
          No tests yet. {canAuthor && "Create your first one with “New test”."}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-line bg-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-ink text-white text-left">
                <th className="px-4 py-2.5 font-medium">Test</th>
                <th className="px-3 py-2.5 font-medium">Class</th>
                <th className="px-3 py-2.5 font-medium text-center">Qs</th>
                <th className="px-3 py-2.5 font-medium text-center">Marks</th>
                <th className="px-3 py-2.5 font-medium">Status</th>
                <th className="px-3 py-2.5 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {exams.map((e, i) => (
                <tr key={e.id} className={i % 2 ? "bg-paper/50" : ""}>
                  <td className="px-4 py-3">
                    <div className="font-medium">{e.title}</div>
                    <div className="text-xs text-ink-soft">{e.subject_name ?? "—"} · {e.duration_minutes} min</div>
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap">{e.class_label ?? "—"}</td>
                  <td className="px-3 py-3 text-center tabular">{e.question_count}</td>
                  <td className="px-3 py-3 text-center tabular">{e.total_marks}</td>
                  <td className="px-3 py-3"><Badge status={e.status} /></td>
                  <td className="px-3 py-3">
                    <div className="flex justify-end gap-3 whitespace-nowrap">
                      {canAuthor && (
                        <Link href={`/dashboard/cbt/${e.id}`} className="text-ink font-medium hover:underline">
                          {e.status === "draft" ? "Edit" : "Open"}
                        </Link>
                      )}
                      <Link href={`/dashboard/cbt/${e.id}/results`} className="text-ledger font-medium hover:underline">
                        Results
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
