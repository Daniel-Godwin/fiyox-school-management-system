"use client";

import { useCallback, useEffect, useState } from "react";
import { api, openPdf, ApiError } from "@/lib/api";

type Term = { id: string; name: string; session: string; is_current: boolean };
type Ward = { student_id: string; name: string; admission_number: string; class_label: string };
type FeeView = { id: string; student_id: string; invoice_number: string; amount: number; paid: number; balance: number; status: string };
type AttSummary = { days_recorded: number; present: number; absent: number; late: number; excused: number };
type Report = { summary: { average: number; position: number; class_size: number; grand_total: number } };

type ResultState =
  | { kind: "ready"; report: Report }
  | { kind: "withheld" | "unpublished" | "none"; message: string };

const ngn = (n: number) =>
  new Intl.NumberFormat("en-NG", { style: "currency", currency: "NGN", maximumFractionDigits: 2 }).format(n);
const ordinal = (n: number) =>
  n + (["th", "st", "nd", "rd"][(n % 100 >> 3) ^ 1 && n % 10] || "th");

export default function WardsPage() {
  const [terms, setTerms] = useState<Term[]>([]);
  const [termId, setTermId] = useState("");
  const [wards, setWards] = useState<Ward[]>([]);
  const [fees, setFees] = useState<Record<string, FeeView>>({});
  const [attendance, setAttendance] = useState<Record<string, AttSummary>>({});
  const [results, setResults] = useState<Record<string, ResultState>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api<Term[]>("/api/academics/terms"), api<Ward[]>("/api/my/wards")])
      .then(([t, w]) => {
        setTerms(t);
        setWards(w);
        const current = t.find((x) => x.is_current);
        if (current) setTermId(current.id);
      })
      .catch(() => setError("Could not load your wards. Is the backend running?"));
  }, []);

  const load = useCallback(async () => {
    if (!termId || wards.length === 0) return;
    setError(null);

    // fees (one call for all wards)
    try {
      const f = await api<FeeView[]>(`/api/my/fees?term_id=${termId}`);
      setFees(Object.fromEntries(f.map((x) => [x.student_id, x])));
    } catch { /* fees stay empty */ }

    // per-ward attendance + result status
    for (const w of wards) {
      api<AttSummary>(`/api/attendance/summary?student_id=${w.student_id}`)
        .then((a) => setAttendance((prev) => ({ ...prev, [w.student_id]: a })))
        .catch(() => {});

      api<Report>(`/api/report/${w.student_id}?term_id=${termId}`)
        .then((r) => setResults((prev) => ({ ...prev, [w.student_id]: { kind: "ready", report: r } })))
        .catch((e) => {
          let state: ResultState;
          if (e instanceof ApiError && e.status === 402) {
            state = { kind: "withheld", message: e.message };
          } else if (e instanceof ApiError && e.status === 403) {
            state = { kind: "unpublished", message: "Result not yet published by the school." };
          } else {
            state = { kind: "none", message: "No result for this term yet." };
          }
          setResults((prev) => ({ ...prev, [w.student_id]: state }));
        });
    }
  }, [termId, wards]);

  useEffect(() => { load(); }, [load]);

  async function pdf(w: Ward) {
    setBusy(w.student_id);
    try {
      await openPdf(`/api/report/${w.student_id}/pdf?term_id=${termId}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `Could not open ${w.name}'s report card.`);
    } finally { setBusy(null); }
  }

  async function payOnline(fee: FeeView) {
    setBusy(`pay-${fee.student_id}`);
    setError(null);
    try {
      const res = await api<{ authorization_url: string }>(
        `/api/fees/invoices/${fee.id}/pay/init`, { method: "POST" });
      window.location.href = res.authorization_url;   // off to Paystack checkout
    } catch (e) {
      setError(e instanceof ApiError
        ? e.message   // e.g. "Online payments are not enabled yet — please pay at the school bursary"
        : "Could not start the payment.");
      setBusy(null);
    }
  }

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">My wards</h1>
        <p className="text-sm text-ink-soft mt-1">
          Results, attendance and fees for your children this term.
        </p>
      </header>

      <label className="block max-w-xs">
        <span className="block text-xs font-medium text-ink-soft mb-1">Term</span>
        <select value={termId} onChange={(e) => setTermId(e.target.value)}
                className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm">
          {terms.map((t) => (
            <option key={t.id} value={t.id}>{t.name} term · {t.session}</option>
          ))}
        </select>
      </label>

      {error && <p role="alert" className="text-sm text-sanction">{error}</p>}

      {wards.length === 0 && !error && (
        <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-6 max-w-xl">
          No wards are linked to your account yet. Ask the school to link your children.
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {wards.map((w) => {
          const fee = fees[w.student_id];
          const att = attendance[w.student_id];
          const res = results[w.student_id];
          return (
            <section key={w.student_id}
                     className="rounded-lg border border-line bg-card p-4 space-y-4">
              <div className="flex items-baseline justify-between gap-2">
                <h2 className="text-lg font-semibold">{w.name}</h2>
                <span className="text-xs text-ink-soft tabular">
                  {w.admission_number} · {w.class_label}
                </span>
              </div>

              {/* result */}
              <div className="rounded-md border border-line bg-paper p-3">
                <p className="text-xs font-medium text-ink-soft mb-1">Result</p>
                {!res && <p className="text-sm text-ink-soft">Checking…</p>}
                {res?.kind === "ready" && (
                  <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
                    <span className="text-sm">
                      Average <b className="tabular">{res.report.summary.average}%</b>
                    </span>
                    <span className="text-sm">
                      Position{" "}
                      <b className="tabular">
                        {ordinal(res.report.summary.position)} of {res.report.summary.class_size}
                      </b>
                    </span>
                    <button onClick={() => pdf(w)} disabled={busy !== null}
                            className="text-sm text-ink underline underline-offset-2 hover:text-ink-soft disabled:opacity-50">
                      {busy === w.student_id ? "Opening…" : "Open report card"}
                    </button>
                  </div>
                )}
                {res && res.kind !== "ready" && (
                  <p className={`text-sm ${res.kind === "withheld" ? "text-sanction" : "text-ink-soft"}`}>
                    {res.message}
                  </p>
                )}
              </div>

              {/* attendance */}
              <div className="rounded-md border border-line bg-paper p-3">
                <p className="text-xs font-medium text-ink-soft mb-1">Attendance</p>
                {att ? (
                  att.days_recorded > 0 ? (
                    <p className="text-sm tabular">
                      {att.present} present · {att.absent} absent · {att.late} late
                      {att.excused ? ` · ${att.excused} excused` : ""}{" "}
                      <span className="text-ink-soft">({att.days_recorded} days)</span>
                    </p>
                  ) : (
                    <p className="text-sm text-ink-soft">No attendance recorded yet.</p>
                  )
                ) : (
                  <p className="text-sm text-ink-soft">Checking…</p>
                )}
              </div>

              {/* fees */}
              <div className="rounded-md border border-line bg-paper p-3">
                <p className="text-xs font-medium text-ink-soft mb-1">Fees</p>
                {fee ? (
                  <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
                    <span>Invoice <b className="tabular">{fee.invoice_number}</b></span>
                    <span>Paid <b className="tabular">{ngn(fee.paid)}</b></span>
                    <span className={fee.balance > 0 ? "text-sanction" : "text-ledger"}>
                      Balance <b className="tabular">{ngn(fee.balance)}</b>
                    </span>
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                      fee.status === "paid" ? "bg-ledger/10 text-ledger"
                        : fee.status === "part_paid" ? "bg-brass/15 text-ink"
                        : "bg-sanction/10 text-sanction"}`}>
                      {fee.status.replace("_", " ")}
                    </span>
                    {fee.balance > 0 && (
                      <button onClick={() => payOnline(fee)} disabled={busy !== null}
                              className="rounded-md bg-ink text-white px-3 py-1.5 text-xs font-medium hover:bg-ink-soft disabled:opacity-50">
                        {busy === `pay-${fee.student_id}` ? "Starting…" : "Pay online"}
                      </button>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-ink-soft">No invoice for this term.</p>
                )}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
