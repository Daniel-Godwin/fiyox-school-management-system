"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, openPdf, ApiError } from "@/lib/api";

type Term = { id: string; name: string; session: string; is_current: boolean };
type Arm = { id: string; label: string };
type Student = { id: string; admission_number: string; first_name: string; last_name: string };
type Summary = {
  invoices: number; expected: number; collected: number; outstanding: number;
  collection_rate: number; by_status: Record<string, number>;
  debtors: { student_id: string; invoice_number: string; balance: number }[];
};
type Invoice = {
  id: string; student_id: string; invoice_number: string; amount: number;
  discount: number; paid: number; balance: number; status: string;
};
type PayForm = { amount: string; method: string; reference: string };

const ngn = (n: number) =>
  new Intl.NumberFormat("en-NG", { style: "currency", currency: "NGN", maximumFractionDigits: 2 }).format(n);

const METHODS = ["cash", "transfer", "pos", "paystack", "flutterwave"];

export default function FeesPage() {
  const [terms, setTerms] = useState<Term[]>([]);
  const [arms, setArms] = useState<Arm[]>([]);
  const [students, setStudents] = useState<Student[]>([]);
  const [termId, setTermId] = useState("");
  const [genArmId, setGenArmId] = useState("");

  const [summary, setSummary] = useState<Summary | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [payOpen, setPayOpen] = useState<string | null>(null);      // invoice id
  const [pay, setPay] = useState<PayForm>({ amount: "", method: "cash", reference: "" });
  const [lastReceipt, setLastReceipt] = useState<Record<string, string>>({}); // invoice -> payment id
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  useEffect(() => {
    Promise.all([
      api<Term[]>("/api/academics/terms"),
      api<Arm[]>("/api/academics/arms"),
      api<Student[]>("/api/students"),
    ]).then(([t, a, s]) => {
      setTerms(t); setArms(a); setStudents(s);
      const current = t.find((x) => x.is_current);
      if (current) setTermId(current.id);
    }).catch(() => setNotice({ kind: "err", text: "Could not load lists. Is the backend running?" }));
  }, []);

  const nameOf = useMemo(() => {
    const m = new Map(students.map((s) => [s.id, `${s.first_name} ${s.last_name}`]));
    return (id: string) => m.get(id) ?? "Unknown";
  }, [students]);
  const admOf = useMemo(() => {
    const m = new Map(students.map((s) => [s.id, s.admission_number]));
    return (id: string) => m.get(id) ?? "";
  }, [students]);

  const load = useCallback(async () => {
    if (!termId) return;
    try {
      const [sum, invs] = await Promise.all([
        api<Summary>(`/api/fees/summary?term_id=${termId}`),
        api<Invoice[]>(`/api/fees/invoices?term_id=${termId}`),
      ]);
      setSummary(sum);
      setInvoices(invs.sort((a, b) => b.balance - a.balance));
    } catch (e) {
      setNotice({
        kind: "err",
        text: e instanceof ApiError && e.status === 403
          ? "Fees are visible to the bursar and school admin only."
          : "Could not load fees data.",
      });
    }
  }, [termId]);

  useEffect(() => { load(); }, [load]);

  async function generate() {
    if (!genArmId) return;
    setBusy("generate"); setNotice(null);
    try {
      const res = await api<{ created: number; skipped_already_invoiced: number; amount_per_student: number }>(
        "/api/fees/invoices/generate",
        { method: "POST", body: JSON.stringify({ arm_id: genArmId, term_id: termId }) },
      );
      setNotice({
        kind: "ok",
        text: `Generated ${res.created} invoice${res.created === 1 ? "" : "s"} at ${ngn(res.amount_per_student)} each` +
          (res.skipped_already_invoiced ? ` (${res.skipped_already_invoiced} already invoiced).` : "."),
      });
      await load();
    } catch (e) {
      setNotice({
        kind: "err",
        text: e instanceof ApiError ? e.message : "Invoice generation failed.",
      });
    } finally { setBusy(null); }
  }

  function openPay(inv: Invoice) {
    setPayOpen(inv.id);
    setPay({ amount: String(inv.balance > 0 ? inv.balance : ""), method: "cash", reference: "" });
    setNotice(null);
  }

  async function recordPayment(inv: Invoice) {
    const amount = Number(pay.amount);
    if (!pay.reference.trim() || Number.isNaN(amount) || amount <= 0) {
      setNotice({ kind: "err", text: "Enter a positive amount and a reference (e.g. teller or transfer number)." });
      return;
    }
    setBusy(inv.id); setNotice(null);
    try {
      const res = await api<{ payment_id: string; duplicate: boolean; invoice: Invoice }>(
        "/api/fees/payments",
        { method: "POST", body: JSON.stringify({
            invoice_id: inv.id, method: pay.method, reference: pay.reference.trim(), amount }) },
      );
      setLastReceipt((prev) => ({ ...prev, [inv.id]: res.payment_id }));
      setNotice({
        kind: "ok",
        text: res.duplicate
          ? "That reference was already recorded — money counted once. Receipt available."
          : `Payment recorded. New balance: ${ngn(res.invoice.balance)}.`,
      });
      setPayOpen(null);
      await load();
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Payment failed." });
    } finally { setBusy(null); }
  }

  async function receipt(invoiceId: string) {
    const pid = lastReceipt[invoiceId];
    if (!pid) return;
    setBusy(`r-${invoiceId}`);
    try { await openPdf(`/api/fees/payments/${pid}/receipt`); }
    catch { setNotice({ kind: "err", text: "Could not open the receipt." }); }
    finally { setBusy(null); }
  }

  const cards = summary && [
    { label: "Expected", value: ngn(summary.expected) },
    { label: "Collected", value: ngn(summary.collected) },
    { label: "Outstanding", value: ngn(summary.outstanding) },
    { label: "Collection rate", value: `${summary.collection_rate}%` },
  ];

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">Fees</h1>
        <p className="text-sm text-ink-soft mt-1">
          Bill a class, record payments as they come in, and see where the term stands.
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="block text-xs font-medium text-ink-soft mb-1">Term</span>
          <select value={termId} onChange={(e) => setTermId(e.target.value)}
                  className="rounded-md border border-line bg-white px-3 py-2 text-sm">
            <option value="">Select term…</option>
            {terms.map((t) => (
              <option key={t.id} value={t.id}>{t.name} term · {t.session}</option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="block text-xs font-medium text-ink-soft mb-1">Generate invoices for</span>
          <select value={genArmId} onChange={(e) => setGenArmId(e.target.value)}
                  className="rounded-md border border-line bg-white px-3 py-2 text-sm">
            <option value="">Select class…</option>
            {arms.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
          </select>
        </label>
        <button onClick={generate} disabled={!termId || !genArmId || busy !== null}
                className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
          {busy === "generate" ? "Generating…" : "Generate invoices"}
        </button>
        {notice && (
          <span role="status"
                className={`text-sm ${notice.kind === "ok" ? "text-ledger" : "text-sanction"}`}>
            {notice.text}
          </span>
        )}
      </div>

      {cards && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {cards.map((c) => (
            <div key={c.label} className="rounded-lg border border-line bg-card p-4">
              <p className="text-xs text-ink-soft">{c.label}</p>
              <p className="text-xl font-semibold tabular mt-1">{c.value}</p>
            </div>
          ))}
        </div>
      )}

      {summary && (
        <p className="text-xs text-ink-soft">
          {summary.invoices} invoice{summary.invoices === 1 ? "" : "s"} ·{" "}
          {summary.by_status["paid"] ?? 0} paid · {summary.by_status["part_paid"] ?? 0} part-paid ·{" "}
          {summary.by_status["unpaid"] ?? 0} unpaid
        </p>
      )}

      {termId && invoices.length === 0 && (
        <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-6 max-w-xl">
          No invoices for this term yet. Set up fee categories and structures, then generate invoices for a class.
        </p>
      )}

      {invoices.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-line bg-card">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-ink text-white text-left">
                <th className="px-3 py-2 font-medium">Student</th>
                <th className="px-3 py-2 font-medium">Invoice</th>
                <th className="px-3 py-2 font-medium text-right">Amount</th>
                <th className="px-3 py-2 font-medium text-right">Paid</th>
                <th className="px-3 py-2 font-medium text-right">Balance</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((inv, i) => (
                <FragmentRow key={inv.id} zebra={i % 2 === 1}>
                  <tr className={i % 2 ? "bg-paper" : "bg-card"}>
                    <td className="px-3 py-2 whitespace-nowrap">
                      <span className="tabular text-ink-soft mr-2">{admOf(inv.student_id)}</span>
                      {nameOf(inv.student_id)}
                    </td>
                    <td className="px-3 py-2 tabular">{inv.invoice_number}</td>
                    <td className="px-3 py-2 text-right tabular">{ngn(inv.amount)}</td>
                    <td className="px-3 py-2 text-right tabular">{ngn(inv.paid)}</td>
                    <td className={`px-3 py-2 text-right tabular font-medium ${inv.balance > 0 ? "text-sanction" : "text-ledger"}`}>
                      {ngn(inv.balance)}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                        inv.status === "paid" ? "bg-ledger/10 text-ledger"
                          : inv.status === "part_paid" ? "bg-brass/15 text-ink"
                          : "bg-sanction/10 text-sanction"}`}>
                        {inv.status.replace("_", " ")}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">
                      {inv.balance > 0 && (
                        <button onClick={() => openPay(inv)} disabled={busy !== null}
                                className="text-ink underline underline-offset-2 hover:text-ink-soft disabled:opacity-50 mr-3">
                          Record payment
                        </button>
                      )}
                      {lastReceipt[inv.id] && (
                        <button onClick={() => receipt(inv.id)} disabled={busy !== null}
                                className="text-ink underline underline-offset-2 hover:text-ink-soft disabled:opacity-50">
                          {busy === `r-${inv.id}` ? "Opening…" : "Receipt"}
                        </button>
                      )}
                    </td>
                  </tr>
                  {payOpen === inv.id && (
                    <tr className={i % 2 ? "bg-paper" : "bg-card"}>
                      <td colSpan={7} className="px-3 pb-3">
                        <div className="flex flex-wrap items-end gap-3 rounded-md border border-line bg-white p-3">
                          <label className="block">
                            <span className="block text-xs text-ink-soft mb-1">Amount (NGN)</span>
                            <input inputMode="decimal" value={pay.amount}
                                   onChange={(e) => setPay({ ...pay, amount: e.target.value })}
                                   className="w-32 rounded border border-line px-2 py-1.5 text-sm tabular" />
                          </label>
                          <label className="block">
                            <span className="block text-xs text-ink-soft mb-1">Method</span>
                            <select value={pay.method}
                                    onChange={(e) => setPay({ ...pay, method: e.target.value })}
                                    className="rounded border border-line px-2 py-1.5 text-sm bg-white">
                              {METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
                            </select>
                          </label>
                          <label className="block grow max-w-xs">
                            <span className="block text-xs text-ink-soft mb-1">Reference (teller / transfer no.)</span>
                            <input value={pay.reference}
                                   onChange={(e) => setPay({ ...pay, reference: e.target.value })}
                                   className="w-full rounded border border-line px-2 py-1.5 text-sm" />
                          </label>
                          <button onClick={() => recordPayment(inv)} disabled={busy !== null}
                                  className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
                            {busy === inv.id ? "Saving…" : "Save payment"}
                          </button>
                          <button onClick={() => setPayOpen(null)} disabled={busy !== null}
                                  className="text-sm text-ink-soft underline underline-offset-2">
                            Cancel
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}
                </FragmentRow>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** Group a data row + its optional inline payment row without breaking table markup. */
function FragmentRow({ children }: { children: React.ReactNode; zebra?: boolean }) {
  return <>{children}</>;
}
