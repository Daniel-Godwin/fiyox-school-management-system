"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, me, User } from "@/lib/api";
import OwnerDashboard from "@/components/OwnerDashboard";
import { StatTile } from "@/components/ui";

const I = {
  students: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /></svg>,
  fees: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4"><path d="M2 7h20v12H2zM2 11h20" /><circle cx="12" cy="15" r="1.5" /></svg>,
  alert: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4"><path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /></svg>,
  check: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><path d="M22 4 12 14.01l-3-3" /></svg>,
  cal: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4"><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M8 2v4M16 2v4M3 10h18" /></svg>,
};

type Student = { id: string };
type Term = { id: string; name: string; session: string; is_current: boolean;
              next_term_begins: string | null };
type FeeSummary = { collected: number; expected: number; collection_rate: number };
type Ward = { name: string };
type SetupState = {
  terms: boolean; classes: boolean; subjects: boolean;
  students: boolean; teachers: boolean; fees: boolean;
};
type ApprovalArm = { arm_id: string; term_id: string; arm_label: string; term_label: string; count: number };
type ApprovalQueue = { count: number; arms: ApprovalArm[] };

function naira(n: number) {
  return "₦" + n.toLocaleString("en-NG", { maximumFractionDigits: 0 });
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
  const [setup, setSetup] = useState<SetupState | null>(null);
  const [approvals, setApprovals] = useState<ApprovalQueue | null>(null);

  useEffect(() => {
    me().then((u) => {
      setUser(u);
      // the platform owner gets a dedicated dashboard (OwnerDashboard) that does
      // its own data loading, so skip the single-school staff fetches here
      if (u.role === "super_admin") return;
      const staff = ["school_admin", "teacher", "bursar"].includes(u.role);

      api<Term[]>("/api/academics/terms").then((ts) => {
        const cur = ts.find((t) => t.is_current) ?? ts[0] ?? null;
        setTerm(cur);
        if (cur && ["super_admin", "school_admin", "principal", "bursar"].includes(u.role)) {
          api<FeeSummary>(`/api/fees/summary?term_id=${cur.id}`).then(setFees).catch(() => {});
        }
        if (cur && ["super_admin", "school_admin", "principal", "teacher"].includes(u.role)) {
          api<unknown[]>(`/api/ai/at-risk?term_id=${cur.id}`)
            .then((r) => setAtRisk(r.length)).catch(() => {});
        }
      }).catch(() => {});

      if (staff || u.role === "principal") {
        api<Student[]>("/api/students").then((s) => setStudents(s.length)).catch(() => {});
      }
      if (u.role === "principal") {
        api<ApprovalQueue>("/api/results/approval-queue").then(setApprovals).catch(() => {});
      }
      if (["super_admin", "school_admin"].includes(u.role)) {
        // is this a brand-new school? compute the setup checklist
        Promise.all([
          api<unknown[]>("/api/academics/terms").catch(() => []),
          api<unknown[]>("/api/academics/arms").catch(() => []),
          api<unknown[]>("/api/academics/subjects").catch(() => []),
          api<Student[]>("/api/students").catch(() => []),
          api<unknown[]>("/api/users?role=teacher").catch(() => []),
          api<unknown[]>("/api/fees/categories").catch(() => []),
        ]).then(([t, a, sub, st, te, fc]) => {
          setSetup({
            terms: t.length > 0, classes: a.length > 0, subjects: sub.length > 0,
            students: st.length > 0, teachers: te.length > 0, fees: fc.length > 0,
          });
        });
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

  if (user.role === "super_admin") return <OwnerDashboard user={user} />;

  const staff = ["super_admin", "school_admin", "teacher", "bursar"].includes(user.role);
  const isAdmin = ["super_admin", "school_admin"].includes(user.role);
  const isBursar = ["super_admin", "school_admin", "bursar"].includes(user.role);
  const isPrincipal = user.role === "principal";
  const family = user.role === "parent" || user.role === "student";

  const today = new Date().toLocaleDateString("en-GB", {
    weekday: "long", day: "numeric", month: "long", year: "numeric" });

  return (
    <div className="max-w-5xl space-y-6">
      {/* premium hero band */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-ink to-ink-soft p-6 sm:p-8 text-white">
        <div className="fiyox-float pointer-events-none absolute -right-12 -top-16 h-48 w-48 rounded-full bg-brass/20 blur-3xl" />
        <div className="fiyox-float--2 pointer-events-none absolute -bottom-20 right-24 h-40 w-40 rounded-full bg-ledger/20 blur-3xl" />
        <div className="relative">
          <p className="text-xs uppercase tracking-[0.14em] text-white/55">{today}</p>
          <h1 className="display text-2xl sm:text-3xl font-bold mt-1.5">Welcome, {user.first_name}</h1>
          <p className="mt-2 max-w-xl text-sm text-white/80">
            {term
              ? <>Your school is in the <b className="text-white">{term.name} term</b> of the {term.session} session.</>
              : (staff || isPrincipal)
                ? "This is where your school's day-to-day work happens."
                : "Follow your ward's results, fees and attendance here."}
            {term?.next_term_begins && <span className="ml-1 text-white/70">Next term begins {term.next_term_begins}.</span>}
          </p>
          {term && (
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-medium ring-1 ring-white/15">{term.name} term</span>
              <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-medium ring-1 ring-white/15">{term.session} session</span>
            </div>
          )}
        </div>
      </div>

      {isAdmin && setup && Object.values(setup).some((done) => !done) && (
        <section className="rounded-xl border border-brass bg-brass/10 p-5">
          <h2 className="text-base font-semibold">Set up your school</h2>
          <p className="text-sm text-ink-soft mt-1 mb-4">
            Work through these in order — each step unlocks the next. The quick
            setup on the School setup page can do the first three at once.
          </p>
          <ol className="space-y-2">
            {([
              { done: setup.terms, label: "Create the session and terms", href: "/dashboard/setup" },
              { done: setup.classes, label: "Add your classes and arms (JSS1 A…)", href: "/dashboard/setup" },
              { done: setup.subjects, label: "Add the subjects you teach", href: "/dashboard/setup" },
              { done: setup.students, label: "Admit your students", href: "/dashboard/students" },
              { done: setup.teachers, label: "Create teacher accounts and assign subjects", href: "/dashboard/users" },
              { done: setup.fees, label: "Set up fee categories and amounts", href: "/dashboard/fees" },
            ]).map((step, i) => (
              <li key={i}>
                <Link href={step.href}
                      className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 text-sm ${
                        step.done
                          ? "border-ledger/30 bg-ledger/5 text-ink-soft"
                          : "border-line bg-white hover:border-ink"}`}>
                  <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                    step.done ? "bg-ledger text-white" : "bg-paper border border-line text-ink-soft"}`}>
                    {step.done ? "✓" : i + 1}
                  </span>
                  <span className={step.done ? "line-through decoration-ink-soft/40" : "font-medium"}>
                    {step.label}
                  </span>
                  {!step.done && <span className="ml-auto text-ink-soft">→</span>}
                </Link>
              </li>
            ))}
          </ol>
        </section>
      )}

      {staff && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <StatTile href="/dashboard/students" label="Students" icon={I.students}
                    value={students?.toLocaleString() ?? "—"}
                    hint="View the register →" />
          {isBursar && fees && (
            <StatTile href="/dashboard/fees" label="Fees collected" icon={I.fees}
                      value={`${Math.round(fees.collection_rate)}%`}
                      tone={fees.collection_rate >= 70 ? "ledger" : "brass"}
                      hint={`${naira(fees.collected)} of ${naira(fees.expected)} →`} />
          )}
          {atRisk !== null && (
            <StatTile href="/dashboard/end-of-term" label="Need attention"
                      icon={atRisk === 0 ? I.check : I.alert}
                      value={atRisk.toString()}
                      tone={atRisk === 0 ? "ledger" : "sanction"}
                      hint={atRisk === 0 ? "All students on track" : "Review the register →"} />
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

      {isPrincipal && (
        <>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <StatTile href="/dashboard/students" label="Students" icon={I.students}
                      value={students?.toLocaleString() ?? "—"} hint="School roll →" />
            {fees && (
              <StatTile href="/dashboard/fees" label="Fees collected" icon={I.fees}
                        value={`${Math.round(fees.collection_rate)}%`}
                        tone={fees.collection_rate >= 70 ? "ledger" : "brass"}
                        hint={`${naira(fees.collected)} of ${naira(fees.expected)} →`} />
            )}
            <StatTile href="/dashboard/results" label="Awaiting approval" icon={I.check}
                      value={approvals ? approvals.count.toString() : "—"}
                      tone={approvals && approvals.count > 0 ? "brass" : "ledger"}
                      hint={approvals && approvals.count > 0 ? "Review & approve →" : "Nothing waiting"} />
          </div>

          {approvals && approvals.count > 0 && (
            <section className="rounded-xl border border-brass bg-brass/10 p-5">
              <h2 className="text-base font-semibold">Results awaiting your approval</h2>
              <p className="text-sm text-ink-soft mt-1 mb-3">
                These classes have submitted results. Review and approve them before they reach parents.
              </p>
              <ul className="space-y-2">
                {approvals.arms.map((a) => (
                  <li key={a.arm_id + a.term_id}>
                    <Link href="/dashboard/results"
                          className="flex items-center justify-between gap-3 rounded-lg border border-line bg-white px-3 py-2.5 text-sm hover:border-ink">
                      <span><b>{a.arm_label}</b> — {a.term_label}</span>
                      <span className="text-ink-soft">{a.count} result{a.count === 1 ? "" : "s"} →</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <h2 className="text-sm font-semibold text-ink-soft uppercase tracking-wide mb-3">
              Quick actions
            </h2>
            <div className="flex flex-wrap gap-2">
              <QuickLink href="/dashboard/results" label="Approve results" />
              <QuickLink href="/dashboard/fees" label="Fees & debtors" />
              <QuickLink href="/dashboard/students" label="Students" />
              <QuickLink href="/dashboard/timetable" label="Timetable" />
            </div>
          </section>
        </>
      )}

      {family && (
        <div className="grid sm:grid-cols-2 gap-4">
          <StatTile href="/dashboard/wards" label="My children" icon={I.students}
                    value={wards ? wards.length.toString() : "—"}
                    hint={wards && wards.length > 0
                      ? wards.map((w) => w.name).join(", ")
                      : "View results & fees →"} />
          <StatTile href="/dashboard/timetable" label="Timetable" icon={I.cal}
                    value="View" hint="This week's lessons →" />
        </div>
      )}
    </div>
  );
}
