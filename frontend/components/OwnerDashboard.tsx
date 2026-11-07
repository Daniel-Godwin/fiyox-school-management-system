"use client";

/**
 * The platform owner's (super admin) home: a bird's-eye view across every school
 * on Fiyox — headline KPIs, platform charts, and an interactive schools
 * leaderboard. Uses the shared SVG Charts, so it stays light and fast.
 */
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, User } from "@/lib/api";
import { Donut, ProgressRing } from "@/components/Charts";

const C = { ink: "#0b1f3a", inkSoft: "#274264", ledger: "#1e7a4f", brass: "#c8a24b", sanction: "#b4232a" };

type Overview = {
  schools: number;
  enrolment: { total_students: number; active: number; by_gender: { male: number; female: number } };
  academics: { computed_results: number; pass_rate: number | null };
  finance: { expected: number; collected: number; collection_rate: number | null; outstanding: number; debtors: number };
  cbt: { published_tests: number; sittings: number };
};
type SchoolRow = {
  id: string; name: string; slug: string; state: string | null; phone: string | null;
  students: number; admins: number; principals: number; bursars: number;
  teachers: number; parents: number; active_accounts: number; created_at: string | null;
};

function nairaShort(n: number) {
  if (n >= 1_000_000) return "₦" + (n / 1_000_000).toFixed(2).replace(/\.?0+$/, "") + "M";
  if (n >= 1_000) return "₦" + (n / 1_000).toFixed(1).replace(/\.?0+$/, "") + "K";
  return "₦" + Math.round(n).toLocaleString("en-NG");
}

function schoolStatus(s: SchoolRow): { label: string; color: string; bg: string } {
  if (s.students > 0) return { label: "Active", color: C.ledger, bg: "bg-ledger/10" };
  if (s.active_accounts > 0) return { label: "Setting up", color: C.brass, bg: "bg-brass/15" };
  return { label: "New", color: C.inkSoft, bg: "bg-paper" };
}

function Kpi({ label, value, hint, accent = C.ink }: { label: string; value: string; hint?: string; accent?: string }) {
  return (
    <div className="group relative bg-card border border-line rounded-xl p-4 overflow-hidden
                    transition-transform duration-200 hover:-translate-y-0.5 hover:shadow-md">
      <span className="absolute left-0 top-0 h-full w-1" style={{ background: accent }} />
      <p className="text-xs uppercase tracking-wide text-ink-soft">{label}</p>
      <p className="display text-2xl font-bold mt-1 tabular" style={{ color: accent }}>{value}</p>
      {hint && <p className="text-xs text-ink-soft mt-1">{hint}</p>}
    </div>
  );
}

function Card({ title, children, className = "" }: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-card border border-line rounded-xl p-5 ${className}`}>
      {title && <p className="text-xs text-ink-soft mb-3 uppercase tracking-wide">{title}</p>}
      {children}
    </div>
  );
}

export default function OwnerDashboard({ user }: { user: User }) {
  const [ov, setOv] = useState<Overview | null>(null);
  const [schools, setSchools] = useState<SchoolRow[] | null>(null);
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<"students" | "name" | "accounts">("students");

  useEffect(() => {
    api<Overview>("/api/analytics/overview").then(setOv).catch(() => {});
    api<SchoolRow[]>("/api/schools").then(setSchools).catch(() => {});
  }, []);

  const counts = useMemo(() => {
    const c = { active: 0, setup: 0, neu: 0 };
    (schools ?? []).forEach((s) => {
      if (s.students > 0) c.active++;
      else if (s.active_accounts > 0) c.setup++;
      else c.neu++;
    });
    return c;
  }, [schools]);

  const rows = useMemo(() => {
    let r = [...(schools ?? [])];
    const needle = q.trim().toLowerCase();
    if (needle) r = r.filter((s) =>
      s.name.toLowerCase().includes(needle) || (s.state ?? "").toLowerCase().includes(needle));
    r.sort((a, b) =>
      sort === "name" ? a.name.localeCompare(b.name)
        : sort === "accounts" ? b.active_accounts - a.active_accounts
          : b.students - a.students);
    return r;
  }, [schools, q, sort]);

  const maxStudents = Math.max(1, ...(schools ?? []).map((s) => s.students));

  return (
    <div className="max-w-5xl space-y-8">
      <header className="fiyox-rise">
        <p className="text-xs uppercase tracking-[0.2em] text-brass-ink">Platform owner</p>
        <h1 className="text-2xl font-bold mt-1">Welcome, {user.first_name}</h1>
        <p className="text-ink-soft text-sm mt-1">
          A bird&apos;s-eye view of every school running on Fiyox.
        </p>
      </header>

      {/* HEADLINE KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 fiyox-rise">
        <Kpi label="Schools" value={(ov?.schools ?? schools?.length ?? 0).toLocaleString()}
             hint={schools ? `${counts.active} active · ${counts.setup} setting up` : undefined} accent={C.ink} />
        <Kpi label="Students" value={(ov?.enrolment.total_students ?? 0).toLocaleString()}
             hint={ov ? `${ov.enrolment.active.toLocaleString()} active` : undefined} accent={C.inkSoft} />
        <Kpi label="Fees collected" value={ov?.finance.collection_rate == null ? "—" : `${ov.finance.collection_rate}%`}
             hint={ov ? nairaShort(ov.finance.collected) : undefined}
             accent={ov && ov.finance.collection_rate != null && ov.finance.collection_rate >= 70 ? C.ledger : C.brass} />
        <Kpi label="Outstanding" value={ov ? nairaShort(ov.finance.outstanding) : "—"}
             hint={ov ? `${ov.finance.debtors} debtor${ov.finance.debtors === 1 ? "" : "s"}` : undefined}
             accent={ov && ov.finance.outstanding > 0 ? C.sanction : C.ledger} />
      </div>

      {/* PLATFORM CHARTS */}
      <div className="grid md:grid-cols-3 gap-3 fiyox-rise">
        <Card title="Schools by status" className="grid place-items-center">
          {schools && schools.length > 0 ? (
            <Donut centerSub="schools" data={[
              { label: "Active", value: counts.active, color: C.ledger },
              { label: "Setting up", value: counts.setup, color: C.brass },
              { label: "New", value: counts.neu, color: C.inkSoft },
            ]} />
          ) : <p className="text-sm text-ink-soft">No schools yet.</p>}
        </Card>
        <Card title="Students — boys & girls" className="grid place-items-center">
          {ov && ov.enrolment.by_gender.male + ov.enrolment.by_gender.female > 0 ? (
            <Donut centerSub="students" data={[
              { label: "Boys", value: ov.enrolment.by_gender.male, color: C.ink },
              { label: "Girls", value: ov.enrolment.by_gender.female, color: C.brass },
            ]} />
          ) : <p className="text-sm text-ink-soft">No students enrolled yet.</p>}
        </Card>
        <Card title="Fees collected" className="grid place-items-center">
          <ProgressRing value={ov?.finance.collection_rate ?? null} sub="collected" label="across all schools"
                        color={ov && ov.finance.collection_rate != null && ov.finance.collection_rate >= 70 ? C.ledger : C.brass} />
        </Card>
      </div>

      {/* SCHOOLS LEADERBOARD */}
      <section className="fiyox-rise space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-ink-soft uppercase tracking-wide">Schools</h2>
          <div className="flex items-center gap-2">
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search school or state…"
                   className="rounded-md border border-line bg-white px-3 py-1.5 text-sm w-44 focus:border-ink outline-none" />
            <select value={sort} onChange={(e) => setSort(e.target.value as typeof sort)}
                    className="rounded-md border border-line bg-white px-2 py-1.5 text-sm">
              <option value="students">Most students</option>
              <option value="accounts">Most active accounts</option>
              <option value="name">Name (A–Z)</option>
            </select>
          </div>
        </div>

        {schools == null ? (
          <p className="text-sm text-ink-soft">Loading schools…</p>
        ) : rows.length === 0 ? (
          <div className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-ink-soft">
            {q ? "No schools match your search." : "No schools onboarded yet."}
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-line bg-card">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-ink text-white text-left">
                  <th className="px-4 py-2.5 font-medium">School</th>
                  <th className="px-4 py-2.5 font-medium">Students</th>
                  <th className="px-4 py-2.5 font-medium hidden sm:table-cell">Teachers</th>
                  <th className="px-4 py-2.5 font-medium hidden md:table-cell">Parents</th>
                  <th className="px-4 py-2.5 font-medium hidden md:table-cell">Active a/c</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5 font-medium hidden lg:table-cell">Onboarded</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((s, i) => {
                  const st = schoolStatus(s);
                  return (
                    <tr key={s.id} className={`${i % 2 ? "bg-paper/50" : "bg-card"} hover:bg-paper transition-colors`}>
                      <td className="px-4 py-2.5">
                        <div className="font-medium text-ink truncate max-w-[200px]">{s.name}</div>
                        {s.state && <div className="text-xs text-ink-soft">{s.state}</div>}
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <span className="tabular font-medium w-8">{s.students}</span>
                          <span className="hidden sm:block h-1.5 rounded-full bg-paper overflow-hidden flex-1 min-w-[40px] max-w-[90px]">
                            <span className="block h-full rounded-full"
                                  style={{ width: `${Math.max(4, (s.students / maxStudents) * 100)}%`, background: C.ink }} />
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-2.5 tabular hidden sm:table-cell">{s.teachers}</td>
                      <td className="px-4 py-2.5 tabular hidden md:table-cell">{s.parents}</td>
                      <td className="px-4 py-2.5 tabular hidden md:table-cell">{s.active_accounts}</td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-flex items-center gap-1.5 rounded-full ${st.bg} px-2.5 py-0.5 text-xs font-medium`}
                              style={{ color: st.color }}>
                          <span className="h-1.5 w-1.5 rounded-full" style={{ background: st.color }} />
                          {st.label}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-ink-soft hidden lg:table-cell whitespace-nowrap">{s.created_at ?? "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex flex-wrap gap-2 pt-1">
          <Link href="/dashboard/schools"
                className="rounded-full border border-line bg-card px-4 py-2 text-sm font-medium hover:border-ink hover:bg-ink hover:text-white transition-colors">
            Manage schools
          </Link>
          <Link href="/dashboard/analytics"
                className="rounded-full border border-line bg-card px-4 py-2 text-sm font-medium hover:border-ink hover:bg-ink hover:text-white transition-colors">
            Full analytics
          </Link>
        </div>
      </section>
    </div>
  );
}
