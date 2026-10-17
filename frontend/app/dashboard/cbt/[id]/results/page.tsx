"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";

type Row = {
  attempt_id: string; student_name: string; attempt_no: number;
  status: string; score: number; max_score: number; percent: number;
  submitted_at: string | null; auto_submitted: boolean;
};
type Results = {
  exam_id: string; title: string; total_marks: number; status: string;
  sittings: number; submitted: number; average_percent: number | null; rows: Row[];
};

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-card border border-line rounded-xl p-4">
      <p className="text-xs uppercase tracking-wide text-ink-soft">{label}</p>
      <p className="display text-2xl font-bold mt-1 tabular">{value}</p>
    </div>
  );
}

export default function CBTResults() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<Results | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api<Results>(`/api/cbt/exams/${id}/results`).then(setData).catch(() => setError(true));
  }, [id]);

  if (error) {
    return <p className="text-sm text-sanction">Could not load results for this test.</p>;
  }
  if (!data) {
    return <div className="grid place-items-center py-20 text-ink-soft text-sm">
      <span className="spinner" /> Loading results…</div>;
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div className="text-sm">
        <Link href="/dashboard/cbt" className="text-ink-soft hover:underline">← All tests</Link>
      </div>

      <header>
        <h1 className="text-2xl font-bold">{data.title}</h1>
        <p className="text-ink-soft text-sm mt-1 capitalize">
          {data.status} · {data.total_marks} marks total
        </p>
      </header>

      <div className="grid grid-cols-3 gap-4">
        <Stat label="Sittings" value={String(data.sittings)} />
        <Stat label="Submitted" value={String(data.submitted)} />
        <Stat label="Class average" value={data.average_percent === null ? "—" : `${data.average_percent}%`} />
      </div>

      {data.rows.length === 0 ? (
        <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-6">
          No one has sat this test yet.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-line bg-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-ink text-white text-left">
                <th className="px-4 py-2.5 font-medium">Student</th>
                <th className="px-3 py-2.5 font-medium text-center">Score</th>
                <th className="px-3 py-2.5 font-medium text-center">%</th>
                <th className="px-3 py-2.5 font-medium">Submitted</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r, i) => (
                <tr key={r.attempt_id} className={i % 2 ? "bg-paper/50" : ""}>
                  <td className="px-4 py-3">
                    {r.student_name}
                    {r.attempt_no > 1 && <span className="text-xs text-ink-soft"> · attempt {r.attempt_no}</span>}
                    {r.auto_submitted && <span className="text-xs text-brass-ink"> · auto-submitted</span>}
                  </td>
                  <td className="px-3 py-3 text-center tabular">
                    {r.status === "submitted" ? `${r.score}/${r.max_score}` : "—"}
                  </td>
                  <td className="px-3 py-3 text-center tabular">
                    {r.status === "submitted"
                      ? <span className={r.percent >= 50 ? "text-ledger font-medium" : "text-sanction font-medium"}>{r.percent}%</span>
                      : <span className="text-xs text-brass-ink">in progress</span>}
                  </td>
                  <td className="px-3 py-3 text-ink-soft">
                    {r.submitted_at ? new Date(r.submitted_at).toLocaleString() : "—"}
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
