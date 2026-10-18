"use client";

import { useEffect, useMemo, useState } from "react";
import { api, me } from "@/lib/api";

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

function naira(n: number) {
  return "₦" + Math.round(n).toLocaleString("en-NG");
}

function Stat({ label, value, hint, tone = "ink" }: {
  label: string; value: string; hint?: string;
  tone?: "ink" | "ledger" | "brass" | "sanction";
}) {
  const toneClass = { ink: "text-ink", ledger: "text-ledger", brass: "text-brass-ink", sanction: "text-sanction" }[tone];
  return (
    <div className="bg-card border border-line rounded-xl p-4">
      <p className="text-xs uppercase tracking-wide text-ink-soft">{label}</p>
      <p className={`display text-2xl font-bold mt-1 tabular ${toneClass}`}>{value}</p>
      {hint && <p className="text-xs text-ink-soft mt-1">{hint}</p>}
    </div>
  );
}

/** horizontal bar row */
function Bar({ label, value, max, suffix = "", tone = "bg-ink" }: {
  label: string; value: number; max: number; suffix?: string; tone?: string;
}) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="w-24 shrink-0 text-ink-soft truncate">{label}</span>
      <div className="flex-1 h-5 rounded bg-paper overflow-hidden border border-line">
        <div className={`h-full ${tone}`} style={{ width: `${Math.max(pct, 2)}%` }} />
      </div>
      <span className="w-16 shrink-0 text-right tabular font-medium">{value}{suffix}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
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
  const maxGrade = useMemo(
    () => Math.max(1, ...(data?.academics.grade_distribution.map((g) => g.count) ?? [1])),
    [data]);

  if (error) {
    return <p className="text-sm text-sanction">Could not load analytics. Is the backend running?</p>;
  }
  if (loading && !data) {
    return <div className="grid place-items-center py-20 text-ink-soft text-sm">
      <span className="spinner" /> Crunching the numbers…</div>;
  }
  if (!data) return null;

  const { enrolment: en, academics: ac, finance: fi, cbt } = data;
  const totalGender = en.by_gender.male + en.by_gender.female;

  return (
    <div className="max-w-4xl space-y-8">
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

      {/* ENROLMENT */}
      <Section title="Enrolment">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat label="Students" value={en.total_students.toLocaleString()} />
          <Stat label="Active" value={en.active.toLocaleString()} tone="ledger" />
          <Stat label="Boys" value={en.by_gender.male.toLocaleString()}
                hint={totalGender ? `${Math.round(en.by_gender.male / totalGender * 100)}%` : undefined} />
          <Stat label="Girls" value={en.by_gender.female.toLocaleString()}
                hint={totalGender ? `${Math.round(en.by_gender.female / totalGender * 100)}%` : undefined} />
        </div>
        {en.by_class.length > 0 && (
          <div className="bg-card border border-line rounded-xl p-4 space-y-2">
            <p className="text-xs text-ink-soft mb-1">Students by class</p>
            {en.by_class.map((c) => (
              <Bar key={c.class} label={c.class} value={c.count} max={maxClass} tone="bg-ink" />
            ))}
          </div>
        )}
      </Section>

      {/* ACADEMICS */}
      <Section title="Academic performance">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat label="Computed results" value={ac.computed_results.toLocaleString()} />
          <Stat label="Overall average" value={ac.overall_average === null ? "—" : `${ac.overall_average}%`} />
          <Stat label="Pass rate" value={ac.pass_rate === null ? "—" : `${ac.pass_rate}%`}
                tone={ac.pass_rate !== null && ac.pass_rate >= 60 ? "ledger" : "brass"} />
          <Stat label="Below pass mark" value={ac.below_pass.toLocaleString()}
                tone={ac.below_pass > 0 ? "sanction" : "ledger"} />
        </div>

        {ac.computed_results === 0 ? (
          <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-4">
            No results computed for this term yet. Enter scores and compute to see performance here.
          </p>
        ) : (
          <div className="grid md:grid-cols-2 gap-3">
            <div className="bg-card border border-line rounded-xl p-4 space-y-2">
              <p className="text-xs text-ink-soft mb-1">Grade distribution (all subjects)</p>
              {ac.grade_distribution.map((g) => (
                <Bar key={g.grade} label={g.grade} value={g.count} max={maxGrade}
                     tone={["A1", "B2", "B3"].includes(g.grade) ? "bg-ledger"
                       : g.grade === "F9" ? "bg-sanction" : "bg-brass"} />
              ))}
            </div>
            <div className="bg-card border border-line rounded-xl p-4">
              <p className="text-xs text-ink-soft mb-2">Top students</p>
              <ol className="space-y-1.5">
                {ac.top_students.map((s, i) => (
                  <li key={i} className="flex items-center justify-between text-sm">
                    <span className="truncate">
                      <span className="text-ink-soft tabular mr-2">{i + 1}.</span>{s.name}
                      {s.class_label && <span className="text-ink-soft text-xs"> · {s.class_label}</span>}
                    </span>
                    <span className="tabular font-medium text-ledger ml-2">{s.average}%</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        )}
      </Section>

      {/* FINANCE */}
      <Section title="Fees & finance">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat label="Collection rate" value={fi.collection_rate === null ? "—" : `${fi.collection_rate}%`}
                tone={fi.collection_rate !== null && fi.collection_rate >= 70 ? "ledger" : "brass"} />
          <Stat label="Collected" value={naira(fi.collected)} hint={`of ${naira(fi.expected)}`} />
          <Stat label="Outstanding" value={naira(fi.outstanding)} tone={fi.outstanding > 0 ? "sanction" : "ledger"} />
          <Stat label="Debtors" value={fi.debtors.toLocaleString()} tone={fi.debtors > 0 ? "sanction" : "ledger"} />
        </div>
        {fi.expected > 0 && (
          <div className="bg-card border border-line rounded-xl p-4">
            <p className="text-xs text-ink-soft mb-2">Fees collected vs expected</p>
            <div className="h-6 rounded bg-paper overflow-hidden border border-line">
              <div className="h-full bg-ledger grid place-items-center text-xs text-white font-medium"
                   style={{ width: `${Math.min(100, Math.round((fi.collected / fi.expected) * 100))}%` }}>
                {fi.collection_rate}%
              </div>
            </div>
          </div>
        )}
      </Section>

      {/* CBT */}
      <Section title="Computer-based tests">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat label="Published tests" value={cbt.published_tests.toLocaleString()} />
          <Stat label="Sittings" value={cbt.sittings.toLocaleString()} />
          <Stat label="Submitted" value={cbt.submitted.toLocaleString()} />
          <Stat label="Average score" value={cbt.average_percent === null ? "—" : `${cbt.average_percent}%`}
                tone={cbt.average_percent !== null && cbt.average_percent >= 50 ? "ledger" : "brass"} />
        </div>
      </Section>
    </div>
  );
}
