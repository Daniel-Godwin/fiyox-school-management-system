"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, me, User } from "@/lib/api";

type Student = { id: string };
type Term = { id: string; name: string; session: string; is_current: boolean;
              next_term_begins: string | null };
type FeeSummary = { collected: number; expected: number; collection_rate: number };
type Ward = { name: string };

function naira(n: number) {
  return "\u20A6" + n.toLocaleString("en-NG", { maximumFractionDigits: 0 });
}

function StatCard({ href, label, value, hint, tone = "ink" }: {
  href?: string; label: string; value: string; hint?: string;
  tone?: "ink" | "ledger" | "brass" | "sanction";
}) {
  const toneClass = {
    ink: "text-ink", ledger: "text-ledger",
    brass: "text-brass-ink", sanction: "text-sanction",
  }[tone];
  const inner = (
    <>
      <p className="text-xs uppercase tracking-wide text-ink-soft">{label}</p>
      <p className={`display text-3xl font-bold mt-1 tabular ${toneClass}`}>{value}</p>
      {hint && <p className="text-sm text-ink-soft mt-2">{hint}</p>}
    </>
  );
  const cls = "block bg-card border border-line rounded-xl p-5 card";
  return href
    ? <Link href={href} className={`${cls} card-interactive`}>{inner}</Link>
    : <div className={cls}>{inner}</div>;
}

function QuickLink({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href}
          className="rounded-full border border-line bg-card px-4 py-2 text-sm font-medium hover:border-ink hover:bg-ink hover:text-white transition-colors">
      {label}
    </Link>
  );
}

export default function Overview() {
  const [user, setUser] = useState<User | null>(null);
  const [students, setStudents] = useState<number | null>(null);
  const [term, setTerm] = useState<Term | null>(null);
  const [fees, setFees] = useState<FeeSummary | null>(null);
  const [wards, setWards] = useState<Ward[] | null>(null);
  const [atRisk, setAtRisk] = useState<number | null>(null);

  useEffect(() => {
    me().then((u) => {
      setUser(u);
      const staff = ["super_admin", "school_admin", "teacher", "bursar"].includes(u.role);

      api<Term[]>("/api/academics/terms").then((ts) => {
        const cur = ts.find((t) => t.is_current) ?? ts[0] ?? null;
        setTerm(cur);
        if (cur && ["super_admin", "school_admin", "bursar"].includes(u.role)) {
          api<FeeSummary>(`/api/fees/summary?term_id=${cur.id}`).then(setFees).catch(() => {});
        }
        if (cur && ["super_admin", "school_admin", "teacher"].includes(u.role)) {
          api<unknown[]>(`/api/ai/at-risk?term_id=${cur.id}`)
            .then((r) => setAtRisk(r.length)).catch(() => {});
        }
      }).catch(() => {});

      if (staff) {
        api<Student[]>("/api/students").then((s) => setStudents(s.length)).catch(() => {});
      }
      if (u.role === "parent" || u.role === "student") {
        api<Ward[]>("/api/my/wards").then(setWards).catch(() => {});
      }
    });
  }, []);

  if (!user) {
    return (
      <div className="grid place-items-center py-20 text-ink-soft text-sm">
        <span className="spinner" /> Loading your dashboard…
      </div>
    );
  }

  const staff = ["super_admin", "school_admin", "teacher", "bursar"].includes(user.role);
  const isAdmin = ["super_admin", "school_admin"].includes(user.role);
  const isBursar = ["super_admin", "school_admin", "bursar"].includes(user.role);
  const family = user.role === "parent" || user.role === "student";

  return (
    <div className="max-w-4xl space-y-8">
      <header>
        <h1 className="text-2xl font-bold">Welcome, {user.first_name}</h1>
        <p className="text-ink-soft text-sm mt-1">
          {term
            ? <>You are in the <b>{term.name} term</b>, {term.session} session.</>
            : staff
              ? "Here is where your school's day-to-day work happens."
              : "Follow your ward's results, fees and attendance here."}
          {term?.next_term_begins && (
            <span className="ml-1">Next term begins {term.next_term_begins}.</span>
          )}
        </p>
      </header>

      {staff && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <StatCard href="/dashboard/students" label="Students"
                    value={students?.toLocaleString() ?? "\u2014"}
                    hint="View the register \u2192" />
          {isBursar && fees && (
            <StatCard href="/dashboard/fees" label="Fees collected"
                      value={`${Math.round(fees.collection_rate)}%`}
                      tone={fees.collection_rate >= 70 ? "ledger" : "brass"}
                      hint={`${naira(fees.collected)} of ${naira(fees.expected)} \u2192`} />
          )}
          {atRisk !== null && (
            <StatCard href="/dashboard/end-of-term" label="Need attention"
                      value={atRisk.toString()}
                      tone={atRisk === 0 ? "ledger" : "sanction"}
                      hint={atRisk === 0 ? "All students on track" : "Review the register \u2192"} />
          )}
        </div>
      )}

      {staff && (
        <section>
          <h2 className="text-sm font-semibold text-ink-soft uppercase tracking-wide mb-3">
            Quick actions
          </h2>
          <div className="flex flex-wrap gap-2">
            {isAdmin && <QuickLink href="/dashboard/setup" label="School setup" />}
            {isAdmin && <QuickLink href="/dashboard/users" label="Accounts" />}
            <QuickLink href="/dashboard/scores" label="Enter scores" />
            <QuickLink href="/dashboard/results" label="Compute results" />
            <QuickLink href="/dashboard/attendance" label="Mark attendance" />
            <QuickLink href="/dashboard/timetable" label="Timetable" />
            {isBursar && <QuickLink href="/dashboard/fees" label="Fees" />}
            {isAdmin && <QuickLink href="/dashboard/end-of-term" label="End of term" />}
          </div>
        </section>
      )}

      {family && (
        <div className="grid sm:grid-cols-2 gap-4">
          <StatCard href="/dashboard/wards" label="My children"
                    value={wards ? wards.length.toString() : "\u2014"}
                    hint={wards && wards.length > 0
                      ? wards.map((w) => w.name).join(", ")
                      : "View results & fees \u2192"} />
          <StatCard href="/dashboard/timetable" label="Timetable"
                    value="View" hint="This week's lessons \u2192" />
        </div>
      )}
    </div>
  );
}
