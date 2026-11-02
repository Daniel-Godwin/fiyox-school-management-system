"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";

type Overview = {
  start: string; end: string;
  fee_income: number; other_income: number; income_total: number;
  expenses: number; payroll: number; outflow: number; net: number;
  expenses_by_category: { category: string; amount: number }[];
};
type Category = { id: string; name: string };
type Expense = { id: string; spent_on: string; category: string | null; description: string; amount: number; payee: string | null; method: string };
type Income = { id: string; received_on: string; source: string; description: string | null; amount: number; method: string };

const field = "w-full rounded-md border border-line bg-white px-3 py-2 text-sm";
const naira = (n: number) => "₦" + Math.round(n).toLocaleString("en-NG");
const today = () => new Date().toISOString().slice(0, 10);

function Stat({ label, value, tone = "ink" }: { label: string; value: string; tone?: "ink" | "ledger" | "sanction" }) {
  const t = { ink: "text-ink", ledger: "text-ledger", sanction: "text-sanction" }[tone];
  return (
    <div className="bg-card border border-line rounded-xl p-4">
      <p className="text-xs uppercase tracking-wide text-ink-soft">{label}</p>
      <p className={`display text-xl font-bold mt-1 tabular ${t}`}>{value}</p>
    </div>
  );
}

export default function FinancePage() {
  const { ok, err } = useToast();
  const [ov, setOv] = useState<Overview | null>(null);
  const [tab, setTab] = useState<"expenses" | "income">("expenses");
  const [cats, setCats] = useState<Category[]>([]);
  const [expenses, setExpenses] = useState<{ total: number; expenses: Expense[] } | null>(null);
  const [income, setIncome] = useState<{ total: number; income: Income[] } | null>(null);

  const [exp, setExp] = useState({ spent_on: today(), category_id: "", description: "", amount: "", payee: "", method: "cash" });
  const [inc, setInc] = useState({ received_on: today(), source: "", description: "", amount: "", method: "cash" });
  const [newCat, setNewCat] = useState("");

  const loadOv = useCallback(() => { api<Overview>("/api/finance/overview").then(setOv).catch(() => err("Could not load overview")); }, [err]);
  const loadExp = useCallback(() => { api<{ total: number; expenses: Expense[] }>("/api/finance/expenses").then(setExpenses).catch(() => {}); }, []);
  const loadInc = useCallback(() => { api<{ total: number; income: Income[] }>("/api/finance/income").then(setIncome).catch(() => {}); }, []);
  const loadCats = useCallback(() => { api<Category[]>("/api/finance/expense-categories").then(setCats).catch(() => {}); }, []);

  useEffect(() => { loadOv(); loadExp(); loadInc(); loadCats(); }, [loadOv, loadExp, loadInc, loadCats]);

  async function addExpense() {
    if (!exp.description.trim() || !exp.amount) return err("Enter a description and amount");
    try {
      await api("/api/finance/expenses", { method: "POST", body: JSON.stringify({
        spent_on: exp.spent_on, category_id: exp.category_id || null, description: exp.description.trim(),
        amount: Number(exp.amount), payee: exp.payee.trim() || null, method: exp.method }) });
      ok("Expense recorded."); setExp({ ...exp, description: "", amount: "", payee: "" }); loadExp(); loadOv();
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not save"); }
  }
  async function addIncome() {
    if (!inc.source.trim() || !inc.amount) return err("Enter a source and amount");
    try {
      await api("/api/finance/income", { method: "POST", body: JSON.stringify({
        received_on: inc.received_on, source: inc.source.trim(), description: inc.description.trim() || null,
        amount: Number(inc.amount), method: inc.method }) });
      ok("Income recorded."); setInc({ ...inc, source: "", description: "", amount: "" }); loadInc(); loadOv();
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not save"); }
  }
  async function addCat() {
    if (!newCat.trim()) return;
    try { await api("/api/finance/expense-categories", { method: "POST", body: JSON.stringify({ name: newCat.trim() }) }); setNewCat(""); loadCats(); }
    catch (e) { err(e instanceof ApiError ? e.message : "Could not add category"); }
  }
  async function del(path: string) {
    try { await api(path, { method: "DELETE" }); loadExp(); loadInc(); loadOv(); } catch (e) { err("Could not delete"); }
  }

  if (!ov) return <div className="grid place-items-center py-20 text-ink-soft text-sm"><span className="spinner" /> Loading…</div>;
  const maxCat = Math.max(1, ...ov.expenses_by_category.map((c) => c.amount));

  return (
    <div className="max-w-4xl space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Finance</h1>
          <p className="text-ink-soft text-sm mt-1">This month ({ov.start} to {ov.end}).</p>
        </div>
        <Link href="/dashboard/finance/payroll" className="shrink-0 rounded-md border border-ink text-ink px-4 py-2 text-sm font-medium hover:bg-ink hover:text-white">Payroll</Link>
      </header>

      {/* overview */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Fee income" value={naira(ov.fee_income)} tone="ledger" />
        <Stat label="Other income" value={naira(ov.other_income)} tone="ledger" />
        <Stat label="Expenses + payroll" value={naira(ov.outflow)} tone="sanction" />
        <Stat label="Net position" value={naira(ov.net)} tone={ov.net >= 0 ? "ledger" : "sanction"} />
      </div>

      {ov.expenses_by_category.length > 0 && (
        <div className="bg-card border border-line rounded-xl p-4 space-y-2">
          <p className="text-xs text-ink-soft mb-1">Expenses by category</p>
          {ov.expenses_by_category.map((c) => (
            <div key={c.category} className="flex items-center gap-3 text-sm">
              <span className="w-28 shrink-0 text-ink-soft truncate">{c.category}</span>
              <div className="flex-1 h-5 rounded bg-paper border border-line overflow-hidden">
                <div className="h-full bg-sanction/70" style={{ width: `${Math.max(2, Math.round(c.amount / maxCat * 100))}%` }} />
              </div>
              <span className="w-24 shrink-0 text-right tabular font-medium">{naira(c.amount)}</span>
            </div>
          ))}
        </div>
      )}

      {/* tabs */}
      <div className="flex gap-2">
        <button onClick={() => setTab("expenses")} className={`rounded-full px-4 py-1.5 text-sm font-medium ${tab === "expenses" ? "bg-ink text-white" : "border border-line"}`}>Expenses</button>
        <button onClick={() => setTab("income")} className={`rounded-full px-4 py-1.5 text-sm font-medium ${tab === "income" ? "bg-ink text-white" : "border border-line"}`}>Other income</button>
      </div>

      {tab === "expenses" ? (
        <div className="space-y-4">
          <div className="bg-card border border-line rounded-xl p-4 space-y-3">
            <p className="text-sm font-semibold">Record an expense</p>
            <div className="grid sm:grid-cols-3 gap-2">
              <input type="date" className={field} value={exp.spent_on} onChange={e => setExp({ ...exp, spent_on: e.target.value })} />
              <select className={field} value={exp.category_id} onChange={e => setExp({ ...exp, category_id: e.target.value })}>
                <option value="">Category…</option>{cats.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
              <input className={field} placeholder="Amount (₦)" type="number" value={exp.amount} onChange={e => setExp({ ...exp, amount: e.target.value })} />
              <input className={`${field} sm:col-span-2`} placeholder="Description" value={exp.description} onChange={e => setExp({ ...exp, description: e.target.value })} />
              <input className={field} placeholder="Paid to (optional)" value={exp.payee} onChange={e => setExp({ ...exp, payee: e.target.value })} />
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <button onClick={addExpense} className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft">Add expense</button>
              <span className="text-ink-soft text-sm">·</span>
              <input className="rounded-md border border-line bg-white px-2 py-1.5 text-sm w-40" placeholder="New category" value={newCat} onChange={e => setNewCat(e.target.value)} />
              <button onClick={addCat} className="text-sm text-ink font-medium hover:underline">+ Add category</button>
            </div>
          </div>
          {expenses && expenses.expenses.length > 0 ? (
            <div className="overflow-x-auto rounded-xl border border-line bg-card">
              <table className="w-full text-sm">
                <thead><tr className="bg-ink text-white text-left"><th className="px-3 py-2 font-medium">Date</th><th className="px-3 py-2 font-medium">Description</th><th className="px-3 py-2 font-medium">Category</th><th className="px-3 py-2 font-medium text-right">Amount</th><th></th></tr></thead>
                <tbody>{expenses.expenses.map((e, i) => (
                  <tr key={e.id} className={i % 2 ? "bg-paper/50" : ""}>
                    <td className="px-3 py-2 tabular text-ink-soft">{e.spent_on}</td>
                    <td className="px-3 py-2">{e.description}{e.payee && <span className="text-ink-soft text-xs"> · {e.payee}</span>}</td>
                    <td className="px-3 py-2 text-ink-soft">{e.category ?? "—"}</td>
                    <td className="px-3 py-2 text-right tabular font-medium">{naira(e.amount)}</td>
                    <td className="px-3 py-2 text-right"><button onClick={() => del(`/api/finance/expenses/${e.id}`)} className="text-sanction text-xs hover:underline">Delete</button></td>
                  </tr>))}</tbody>
              </table>
            </div>
          ) : <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-5">No expenses recorded yet.</p>}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="bg-card border border-line rounded-xl p-4 space-y-3">
            <p className="text-sm font-semibold">Record other income</p>
            <div className="grid sm:grid-cols-3 gap-2">
              <input type="date" className={field} value={inc.received_on} onChange={e => setInc({ ...inc, received_on: e.target.value })} />
              <input className={field} placeholder="Source (e.g. PTA levy)" value={inc.source} onChange={e => setInc({ ...inc, source: e.target.value })} />
              <input className={field} placeholder="Amount (₦)" type="number" value={inc.amount} onChange={e => setInc({ ...inc, amount: e.target.value })} />
              <input className={`${field} sm:col-span-3`} placeholder="Description (optional)" value={inc.description} onChange={e => setInc({ ...inc, description: e.target.value })} />
            </div>
            <button onClick={addIncome} className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft">Add income</button>
          </div>
          {income && income.income.length > 0 ? (
            <div className="overflow-x-auto rounded-xl border border-line bg-card">
              <table className="w-full text-sm">
                <thead><tr className="bg-ink text-white text-left"><th className="px-3 py-2 font-medium">Date</th><th className="px-3 py-2 font-medium">Source</th><th className="px-3 py-2 font-medium text-right">Amount</th><th></th></tr></thead>
                <tbody>{income.income.map((x, i) => (
                  <tr key={x.id} className={i % 2 ? "bg-paper/50" : ""}>
                    <td className="px-3 py-2 tabular text-ink-soft">{x.received_on}</td>
                    <td className="px-3 py-2">{x.source}{x.description && <span className="text-ink-soft text-xs"> · {x.description}</span>}</td>
                    <td className="px-3 py-2 text-right tabular font-medium text-ledger">{naira(x.amount)}</td>
                    <td className="px-3 py-2 text-right"><button onClick={() => del(`/api/finance/income/${x.id}`)} className="text-sanction text-xs hover:underline">Delete</button></td>
                  </tr>))}</tbody>
              </table>
            </div>
          ) : <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-5">No other income recorded yet.</p>}
        </div>
      )}
    </div>
  );
}
