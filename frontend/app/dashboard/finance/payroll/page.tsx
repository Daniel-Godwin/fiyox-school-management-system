"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";

type Salary = { staff_user_id: string; name: string; role: string; gross: number; deduction: number; net: number; is_active: boolean; has_salary: boolean };
type Run = { id: string; month: string; label: string; status: string; total_net: number; note: string };
type Payslip = { id: string; name: string; gross: number; deduction: number; net: number; paid: boolean; paid_on: string | null };
type RunDetail = Run & { payslips: Payslip[]; staff_count: number; paid_count: number };

const naira = (n: number) => "₦" + Math.round(n).toLocaleString("en-NG");
const field = "rounded-md border border-line bg-white px-2 py-1.5 text-sm";
const ROLE_LABEL: Record<string, string> = { school_admin: "Admin", principal: "Principal", bursar: "Bursar", teacher: "Teacher" };

export default function PayrollPage() {
  const { ok, err } = useToast();
  const [salaries, setSalaries] = useState<Salary[]>([]);
  const [edits, setEdits] = useState<Record<string, { gross: string; deduction: string }>>({});
  const [runs, setRuns] = useState<Run[]>([]);
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [openRun, setOpenRun] = useState<RunDetail | null>(null);

  const loadSal = useCallback(() => { api<Salary[]>("/api/finance/salaries").then(setSalaries).catch(() => err("Could not load salaries")); }, [err]);
  const loadRuns = useCallback(() => { api<Run[]>("/api/finance/payroll").then(setRuns).catch(() => {}); }, []);
  useEffect(() => { loadSal(); loadRuns(); }, [loadSal, loadRuns]);

  function edit(id: string, k: "gross" | "deduction", v: string) {
    const cur = edits[id] ?? { gross: String(salaries.find(s => s.staff_user_id === id)?.gross ?? 0), deduction: String(salaries.find(s => s.staff_user_id === id)?.deduction ?? 0) };
    setEdits({ ...edits, [id]: { ...cur, [k]: v } });
  }
  async function saveSalary(s: Salary) {
    const e = edits[s.staff_user_id] ?? { gross: String(s.gross), deduction: String(s.deduction) };
    try {
      await api("/api/finance/salaries", { method: "PUT", body: JSON.stringify({
        staff_user_id: s.staff_user_id, gross: Number(e.gross) || 0, deduction: Number(e.deduction) || 0, is_active: true }) });
      ok(`Saved ${s.name}'s salary.`); loadSal();
    } catch (er) { err(er instanceof ApiError ? er.message : "Could not save"); }
  }
  async function createRun() {
    try { const r = await api<Run>("/api/finance/payroll", { method: "POST", body: JSON.stringify({ month }) }); ok(`Payroll created for ${r.label}.`); loadRuns(); openRunDetail(r.id); }
    catch (e) { err(e instanceof ApiError ? e.message : "Could not create run"); }
  }
  function openRunDetail(id: string) {
    if (openRun?.id === id) { setOpenRun(null); return; }
    api<RunDetail>(`/api/finance/payroll/${id}`).then(setOpenRun).catch(() => err("Could not load run"));
  }
  async function paySlip(runId: string, slipId: string) {
    try { await api(`/api/finance/payroll/${runId}/payslips/${slipId}/pay`, { method: "POST" }); openRunDetailReload(runId); loadRuns(); }
    catch (e) { err(e instanceof ApiError ? e.message : "Could not record"); }
  }
  async function payAll(runId: string) {
    try { await api(`/api/finance/payroll/${runId}/pay-all`, { method: "POST" }); ok("All staff marked paid."); openRunDetailReload(runId); loadRuns(); }
    catch (e) { err(e instanceof ApiError ? e.message : "Could not record"); }
  }
  function openRunDetailReload(id: string) { api<RunDetail>(`/api/finance/payroll/${id}`).then(setOpenRun).catch(() => {}); }
  async function delRun(id: string) {
    try { await api(`/api/finance/payroll/${id}`, { method: "DELETE" }); setOpenRun(null); loadRuns(); }
    catch (e) { err(e instanceof ApiError ? e.message : "Could not delete"); }
  }

  const monthlyTotal = salaries.reduce((t, s) => t + (s.gross - s.deduction), 0);

  return (
    <div className="max-w-3xl space-y-6">
      <div className="text-sm"><Link href="/dashboard/finance" className="text-ink-soft hover:underline">← Finance</Link></div>
      <header>
        <h1 className="text-2xl font-bold">Payroll</h1>
        <p className="text-ink-soft text-sm mt-1">Set each staff member’s salary, then run payroll month by month.</p>
      </header>

      {/* run payroll */}
      <div className="rounded-xl border border-line bg-card p-4 flex flex-wrap items-end gap-3">
        <div><label className="block text-xs text-ink-soft mb-1">Run payroll for</label>
          <input type="month" className={field} value={month} onChange={e => setMonth(e.target.value)} /></div>
        <button onClick={createRun} className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft">Run payroll</button>
        <p className="text-sm text-ink-soft ml-auto">Monthly salary bill: <span className="font-semibold text-ink tabular">{naira(monthlyTotal)}</span></p>
      </div>

      {/* runs */}
      {runs.length > 0 && (
        <div className="space-y-2">
          {runs.map((r) => (
            <div key={r.id} className="rounded-xl border border-line bg-card overflow-hidden">
              <button onClick={() => openRunDetail(r.id)} className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-paper/50">
                <div><p className="font-medium">{r.label}
                  <span className={`ml-2 inline-block rounded-full px-2 py-0.5 text-xs font-medium ${r.status === "paid" ? "bg-ledger/10 text-ledger" : "bg-brass/15 text-brass-ink"}`}>{r.status}</span></p></div>
                <span className="tabular font-semibold">{naira(r.total_net)}</span>
              </button>
              {openRun?.id === r.id && (
                <div className="border-t border-line px-4 py-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-sm text-ink-soft">{openRun.paid_count} of {openRun.staff_count} paid</p>
                    <div className="flex gap-2">
                      {openRun.status !== "paid" && <button onClick={() => payAll(r.id)} className="rounded-md bg-ledger text-white px-3 py-1.5 text-sm font-medium hover:opacity-90">Mark all paid</button>}
                      {openRun.status !== "paid" && <button onClick={() => delRun(r.id)} className="rounded-md border border-sanction text-sanction px-3 py-1.5 text-sm font-medium hover:bg-sanction hover:text-white">Delete run</button>}
                    </div>
                  </div>
                  <div className="overflow-x-auto rounded-lg border border-line">
                    <table className="w-full text-sm">
                      <thead><tr className="bg-ink text-white text-left"><th className="px-3 py-2 font-medium">Staff</th><th className="px-3 py-2 font-medium text-right">Gross</th><th className="px-3 py-2 font-medium text-right">Deduction</th><th className="px-3 py-2 font-medium text-right">Net</th><th className="px-3 py-2 font-medium text-right">Status</th></tr></thead>
                      <tbody>{openRun.payslips.map((p, i) => (
                        <tr key={p.id} className={i % 2 ? "bg-paper/50" : ""}>
                          <td className="px-3 py-2">{p.name}</td>
                          <td className="px-3 py-2 text-right tabular">{naira(p.gross)}</td>
                          <td className="px-3 py-2 text-right tabular text-ink-soft">{naira(p.deduction)}</td>
                          <td className="px-3 py-2 text-right tabular font-medium">{naira(p.net)}</td>
                          <td className="px-3 py-2 text-right">
                            {p.paid ? <span className="text-ledger text-xs font-medium">Paid {p.paid_on}</span>
                              : <button onClick={() => paySlip(r.id, p.id)} className="rounded-md border border-ledger text-ledger px-2.5 py-1 text-xs font-medium hover:bg-ledger hover:text-white">Mark paid</button>}
                          </td>
                        </tr>))}</tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* salaries */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-ink-soft uppercase tracking-wide">Staff salaries</h2>
        <div className="overflow-x-auto rounded-xl border border-line bg-card">
          <table className="w-full text-sm">
            <thead><tr className="bg-ink text-white text-left"><th className="px-3 py-2 font-medium">Staff</th><th className="px-3 py-2 font-medium">Gross (₦)</th><th className="px-3 py-2 font-medium">Deduction (₦)</th><th className="px-3 py-2 font-medium text-right">Net</th><th></th></tr></thead>
            <tbody>
              {salaries.map((s, i) => {
                const e = edits[s.staff_user_id];
                const gross = e ? Number(e.gross) || 0 : s.gross;
                const ded = e ? Number(e.deduction) || 0 : s.deduction;
                return (
                  <tr key={s.staff_user_id} className={i % 2 ? "bg-paper/50" : ""}>
                    <td className="px-3 py-2">{s.name} <span className="text-ink-soft text-xs">· {ROLE_LABEL[s.role] ?? s.role}</span></td>
                    <td className="px-3 py-2"><input type="number" className={`${field} w-28`} value={e ? e.gross : String(s.gross)} onChange={ev => edit(s.staff_user_id, "gross", ev.target.value)} /></td>
                    <td className="px-3 py-2"><input type="number" className={`${field} w-24`} value={e ? e.deduction : String(s.deduction)} onChange={ev => edit(s.staff_user_id, "deduction", ev.target.value)} /></td>
                    <td className="px-3 py-2 text-right tabular font-medium">{naira(gross - ded)}</td>
                    <td className="px-3 py-2 text-right"><button onClick={() => saveSalary(s)} className="rounded-md bg-ink text-white px-3 py-1 text-xs font-medium hover:bg-ink-soft">Save</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
