"use client";

import { useEffect, useMemo, useState } from "react";
import { api, me } from "@/lib/api";
import { Donut, ProgressRing, Columns, BarRow } from "@/components/Charts";

type Term = { id: string; name: string; session: string; is_current: boolean };
type Overview = {
  scope: "school" | "platform";
  schools: number;
  term: { id: string; name: string } | null;
  enrolment: {
    total_students: number; active: number;
    by_gender: { male: number; female: number };
    by_class: { class: string; count: number }[];
  };
  academics: {
    computed_results: number; overall_average: number | null; pass_rate: number | null;
    below_pass: number;
    grade_distribution: { grade: string; count: number }[];
    top_students: { name: string; average: number; class_label: string }[];
  };
  finance: {
    expected: number; collected: number; collection_rate: number | null;
    outstanding: number; debtors: number;
  };
  cbt: { published_tests: number; sittings: number; submitted: number; average_percent: number | null };
};

const C = { ink: "#0b1f3a", inkSoft: "#274264", ledger: "#1e7a4f", brass: "#c8a24b", sanction: "#b4232a" };

function naira(n: number) {
  return "₦" + Math.round(n).toLocaleString("en-NG");
}

/** Compact currency for tight KPI tiles: ₦1.98M, ₦940K, ₦750. */
function nairaShort(n: number) {
  if (n >= 1_000_000) return "₦" + (n / 1_000_000).toFixed(2).replace(/\.?0+$/, "") + "M";
  if (n >= 1_000) return "₦" + (n / 1_000).toFixed(1).replace(/\.?0+$/, "") + "K";
  return "₦" + Math.round(n).toLocaleString("en-NG");
}

function gradeColor(g: string) {
  if (["A1", "B2", "B3"].includes(g)) return C.ledger;
  if (["C4", "C5", "C6"].includes(g)) return C.brass;
  if (g === "F9") return C.sanction;
  return C.inkSoft;
}

/** KPI tile with a colored accent and a subtle hover lift. */
function Kpi({ label, value, hint, accent = C.ink }: {
  label: string; value: string; hint?: string; accent?: string;
}) {
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

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 fiyox-rise">
      <h2 className="text-sm font-semibold text-ink-soft uppercase tracking-wide">{title}</h2>
      {children}
    </section>
  );
}

export default function AnalyticsPage() {
  const [terms, setTerms] = useState<Term[]>([]);
  const [termId, setTermId] = useState("");
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    me().then(() => {
      api<Term[]>("/api/academics/terms").then((ts) => {
        setTerms(ts);
        const cur = ts.find((t) => t.is_current) ?? ts[0];
        if (cur) setTermId(cur.id);
        else load("");
      }).catch(() => setError(true));
    }).catch(() => setError(true));
  }, []);

  function load(tid: string) {
    setLoading(true);
    const q = tid ? `?term_id=${tid}` : "";
    api<Overview>(`/api/analytics/overview${q}`)
      .then(setData).catch(() => setError(true)).finally(() => setLoading(false));
  }

  useEffect(() => { if (termId) load(termId); }, [termId]);

  const maxClass = useMemo(
    () => Math.max(1, ...(data?.enrolment.by_class.map((c) => c.count) ?? [1])),
    [data]);

  if (error) {
    return <p className="text-sm text-sanction">Could not load analytics. Is the backend running?</p>;
  }
  if (loading && !data) {
    return <div className="grid place-items-center py-24 text-ink-soft text-sm gap-3">
      <span className="spinner" /> Crunching the numbers…</div>;
  }
  if (!data) return null;

  const { enrolment: en, academics: ac, finance: fi, cbt } = data;

  return (
    <div className="max-w-5xl space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Analytics</h1>
          <p className="text-ink-soft text-sm mt-1">
            {data.scope === "platform"
              ? `Across all ${data.schools} schools on the platform.`
              : "A snapshot of your school this term."}
          </p>
        </div>
        <select value={termId} onChange={(e) => setTermId(e.target.value)}
                className="rounded-md border border-line bg-white px-3 py-2 text-sm">
          {terms.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name} — {t.session}{t.is_current ? " (current)" : ""}
            </option>
          ))}
        </select>
      </header>

      {/* HEADLINE KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 fiyox-rise">
        <Kpi label="Students" value={en.total_students.toLocaleString()}
             hint={`${en.active.toLocaleString()} active`} accent={C.ink} />
        <Kpi label="Pass rate" value={ac.pass_rate === null ? "—" : `${ac.pass_rate}%`}
             hint={ac.computed_results ? `${ac.computed_results} results` : "no results yet"}
             accent={ac.pass_rate !== null && ac.pass_rate >= 60 ? C.ledger : C.brass} />
        <Kpi label="Fees collected" value={fi.collection_rate === null ? "—" : `${fi.collection_rate}%`}
             hint={nairaShort(fi.collected)} accent={fi.collection_rate !== null && fi.collection_rate >= 70 ? C.ledger : C.brass} />
        <Kpi label="Outstanding" value={nairaShort(fi.outstanding)}
             hint={`${fi.debtors} debtor${fi.debtors === 1 ? "" : "s"}`}
             accent={fi.outstanding > 0 ? C.sanction : C.ledger} />
      </div>

      {/* ENROLMENT */}
      <Section title="Enrolment">
        <div className="grid md:grid-cols-2 gap-3">
          <Card title="Boys & girls">
            {en.by_gender.male + en.by_gender.female > 0 ? (
              <Donut centerSub="students" data={[
                { label: "Boys", value: en.by_gender.male, color: C.ink },
                { label: "Girls", value: en.by_gender.female, color: C.brass },
              ]} />
            ) : <p className="text-sm text-ink-soft">No students enrolled yet.</p>}
          </Card>
          <Card title="Students by class">
            {en.by_class.length > 0 ? (
              <div className="space-y-2">
                {en.by_class.map((c) => (
                  <BarRow key={c.class} label={c.class} value={c.count} max={maxClass} color={C.ink} />
                ))}
              </div>
            ) : <p className="text-sm text-ink-soft">No classes with students yet.</p>}
          </Card>
        </div>
      </Section>

      {/* ACADEMICS */}
      <Section title="Academic performance">
        {ac.computed_results === 0 ? (
          <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-4">
            No results computed for this term yet. Enter scores and compute to see performance here.
          </p>
        ) : (
          <div className="grid md:grid-cols-3 gap-3">
            <Card title="Pass rate" className="grid place-items-center">
              <ProgressRing value={ac.pass_rate} label={`${ac.below_pass} below pass mark`}
                            sub="passing" color={ac.pass_rate !== null && ac.pass_rate >= 60 ? C.ledger : C.brass} />
            </Card>
            <Card title="Grade distribution" className="md:col-span-2">
              <Columns data={ac.grade_distribution.map((g) => ({
                label: g.grade, value: g.count, color: gradeColor(g.grade),
              }))} />
            </Card>
            <Card title="Overall average" className="grid place-items-center">
              <ProgressRing value={ac.overall_average} label="class average" sub="average" color={C.inkSoft} />
            </Card>
            <Card title="Top students" className="md:col-span-2">
              <ol className="space-y-1.5">
                {ac.top_students.map((s, i) => (
                  <li key={i} className="flex items-center justify-between text-sm">
                    <span className="truncate">
                      <span className="inline-grid place-items-center h-5 w-5 rounded-full bg-paper text-xs tabular mr-2 text-ink-soft">{i + 1}</span>
                      {s.name}
                      {s.class_label && <span className="text-ink-soft text-xs"> · {s.class_label}</span>}
                    </span>
                    <span className="tabular font-medium text-ledger ml-2">{s.average}%</span>
                  </li>
                ))}
              </ol>
            </Card>
          </div>
        )}
      </Section>

      {/* FINANCE */}
      <Section title="Fees & finance">
        <div className="grid md:grid-cols-3 gap-3">
          <Card title="Collection rate" className="grid place-items-center">
            <ProgressRing value={fi.collection_rate} label={`${naira(fi.collected)} of ${naira(fi.expected)}`}
                          sub="collected" color={fi.collection_rate !== null && fi.collection_rate >= 70 ? C.ledger : C.brass} />
          </Card>
          <Card title="Collected vs outstanding" className="md:col-span-2">
            {fi.expected > 0 ? (
              <div className="space-y-4">
                <Donut centerSub="expected" data={[
                  { label: "Collected", value: fi.collected, color: C.ledger },
                  { label: "Outstanding", value: fi.outstanding, color: C.sanction },
                ]} />
              </div>
            ) : <p className="text-sm text-ink-soft">No invoices issued this term yet.</p>}
          </Card>
        </div>
      </Section>

      {/* CBT */}
      <Section title="Computer-based tests">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Kpi label="Published tests" value={cbt.published_tests.toLocaleString()} accent={C.ink} />
          <Kpi label="Sittings" value={cbt.sittings.toLocaleString()} accent={C.inkSoft} />
          <Kpi label="Submitted" value={cbt.submitted.toLocaleString()} accent={C.inkSoft} />
          <Kpi label="Average score" value={cbt.average_percent === null ? "—" : `${cbt.average_percent}%`}
               accent={cbt.average_percent !== null && cbt.average_percent >= 50 ? C.ledger : C.brass} />
        </div>
      </Section>
    </div>
  );
}
