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
type Category = { id: string; name: string };
type Structure = { id: string; class_id: string; term_id: string; category_id: string; amount: number };

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

  // fee setup
  const [categories, setCategories] = useState<Category[]>([]);
  const [structures, setStructures] = useState<Structure[]>([]);
  const [setupOpen, setSetupOpen] = useState(false);
  const [newCat, setNewCat] = useState("");
  const [newStruct, setNewStruct] = useState({ class_id: "", category_id: "", amount: "" });

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
      const [sum, invs, cats, structs] = await Promise.all([
        api<Summary>(`/api/fees/summary?term_id=${termId}`),
        api<Invoice[]>(`/api/fees/invoices?term_id=${termId}`),
        api<Category[]>("/api/fees/categories"),
        api<Structure[]>(`/api/fees/structures?term_id=${termId}`),
      ]);
      setSummary(sum);
      setInvoices(invs.sort((a, b) => b.balance - a.balance));
      setCategories(cats);
      setStructures(structs);
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

  // unique classes derived from arms (structures are per class, not per arm)
  const classes = useMemo(() => {
    const seen = new Map<string, string>();
    for (const a of arms as (Arm & { class_id?: string; class_name?: string })[]) {
      if (a.class_id && !seen.has(a.class_id)) seen.set(a.class_id, a.class_name || a.label);
    }
    return [...seen.entries()].map(([id, name]) => ({ id, name }));
  }, [arms]);

  const catName = useMemo(() => {
    const m = new Map(categories.map((c) => [c.id, c.name]));
    return (id: string) => m.get(id) ?? "?";
  }, [categories]);
  const className = useMemo(() => {
    const m = new Map(classes.map((c) => [c.id, c.name]));
    return (id: string) => m.get(id) ?? "?";
  }, [classes]);

  async function addCategory() {
    if (!newCat.trim()) return;
    setBusy("cat"); setNotice(null);
    try {
      await api("/api/fees/categories", { method: "POST", body: JSON.stringify({ name: newCat.trim() }) });
      setNewCat("");
      await load();
    } catch { setNotice({ kind: "err", text: "Could not add the category." }); }
    finally { setBusy(null); }
  }

  async function addStructure() {
    const amount = Number(newStruct.amount);
    if (!newStruct.class_id || !newStruct.category_id || Number.isNaN(amount) || amount <= 0) {
      setNotice({ kind: "err", text: "Pick a class and category, and enter a positive amount." });
      return;
    }
    setBusy("struct"); setNotice(null);
    try {
      await api("/api/fees/structures", {
        method: "POST",
        body: JSON.stringify({ class_id: newStruct.class_id, term_id: termId,
                               category_id: newStruct.category_id, amount }),
      });
      setNewStruct({ class_id: "", category_id: "", amount: "" });
      setNotice({ kind: "ok", text: "Fee added. Repeat for other categories, then generate invoices." });
      await load();
    } catch (e) {
      setNotice({
        kind: "err",
        text: e instanceof ApiError && e.status === 409
          ? "That class already has a fee for this category this term."
          : "Could not add the fee.",
      });
    } finally { setBusy(null); }
  }

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
      const msg = e instanceof ApiError ? e.message : "Invoice generation failed.";
      if (msg.includes("no fee structure")) setSetupOpen(true);
      setNotice({
        kind: "err",
        text: msg.includes("no fee structure")
          ? "No fees set for this class and term yet — add them in Fee setup above, then try again."
          : msg,
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

      {/* ---- Fee setup (categories + per-class amounts for this term) ---- */}
      <section className="rounded-lg border border-line bg-card">
        <button onClick={() => setSetupOpen(!setupOpen)}
                className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium">
          <span>
            Fee setup
            <span className="ml-2 font-normal text-ink-soft">
              {categories.length} categor{categories.length === 1 ? "y" : "ies"} ·{" "}
              {structures.length} fee{structures.length === 1 ? "" : "s"} this term
            </span>
          </span>
          <span aria-hidden className="text-ink-soft">{setupOpen ? "▴" : "▾"}</span>
        </button>

        {setupOpen && (
          <div className="border-t border-line px-4 py-4 space-y-4">
            <p className="text-xs text-ink-soft">
              Invoices are the sum of a class&apos;s fees for the term. Add categories
              once (School Fees, Exam Fees…), then set each class&apos;s amount below —
              after that, Generate invoices will work.
            </p>

            {/* categories */}
            <div className="flex flex-wrap items-center gap-2">
              {categories.map((c) => (
                <span key={c.id}
                      className="rounded-full border border-line bg-paper px-3 py-1 text-xs">
                  {c.name}
                </span>
              ))}
              <input value={newCat} onChange={(e) => setNewCat(e.target.value)}
                     onKeyDown={(e) => e.key === "Enter" && addCategory()}
                     placeholder="New category e.g. School Fees"
                     className="rounded border border-line px-2 py-1.5 text-xs w-52" />
              <button onClick={addCategory} disabled={busy !== null || !newCat.trim()}
                      className="rounded-md border border-ink text-ink px-3 py-1.5 text-xs font-medium hover:bg-ink hover:text-white disabled:opacity-40">
                {busy === "cat" ? "Adding…" : "Add category"}
              </button>
            </div>

            {/* structures for this term */}
            {structures.length > 0 && (
              <table className="text-sm">
                <thead>
                  <tr className="text-left text-xs text-ink-soft">
                    <th className="pr-6 py-1 font-medium">Class</th>
                    <th className="pr-6 py-1 font-medium">Category</th>
                    <th className="py-1 font-medium text-right">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {structures.map((s) => (
                    <tr key={s.id}>
                      <td className="pr-6 py-1">{className(s.class_id)}</td>
                      <td className="pr-6 py-1">{catName(s.category_id)}</td>
                      <td className="py-1 text-right tabular">{ngn(s.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <div className="flex flex-wrap items-end gap-3">
              <label className="block">
                <span className="block text-xs text-ink-soft mb-1">Class</span>
                <select value={newStruct.class_id}
                        onChange={(e) => setNewStruct({ ...newStruct, class_id: e.target.value })}
                        className="rounded border border-line px-2 py-1.5 text-sm bg-white">
                  <option value="">Select…</option>
                  {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </label>
              <label className="block">
                <span className="block text-xs text-ink-soft mb-1">Category</span>
                <select value={newStruct.category_id}
                        onChange={(e) => setNewStruct({ ...newStruct, category_id: e.target.value })}
                        className="rounded border border-line px-2 py-1.5 text-sm bg-white">
                  <option value="">Select…</option>
                  {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </label>
              <label className="block">
                <span className="block text-xs text-ink-soft mb-1">Amount (NGN)</span>
                <input inputMode="decimal" value={newStruct.amount}
                       onChange={(e) => setNewStruct({ ...newStruct, amount: e.target.value })}
                       className="w-32 rounded border border-line px-2 py-1.5 text-sm tabular" />
              </label>
              <button onClick={addStructure} disabled={busy !== null || !termId}
                      className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
                {busy === "struct" ? "Adding…" : "Add fee for class"}
              </button>
            </div>
          </div>
        )}
      </section>

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
