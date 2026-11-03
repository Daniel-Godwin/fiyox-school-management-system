"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";

type Applicant = {
  id: string; application_number: string; name: string; gender: string;
  applying_class: string; applying_class_id: string;
  guardian_name: string; guardian_phone: string; guardian_email: string | null;
  previous_school: string | null; status: string; status_note: string;
  proposed_status: string | null; proposal_source: string | null; decided_at: string | null;
  entrance_score: number | null; entrance_max: number | null; entrance_percent: number | null;
  entrance_taken: boolean; admitted_student_id: string | null; created_at: string;
};
type ListResp = { counts: Record<string, number>; total: number; pending: number; applicants: Applicant[] };
type Arm = { id: string; label: string };
type Me = { role: string };

const STATUSES = ["applied", "shortlisted", "admitted", "rejected"];
const DECISION_LABEL: Record<string, string> = {
  shortlisted: "Shortlist", admitted: "Admit", rejected: "Not successful",
};
const STATUS_STYLE: Record<string, string> = {
  applied: "bg-ink/10 text-ink-soft border-line",
  shortlisted: "bg-brass/15 text-brass-ink border-brass/30",
  admitted: "bg-ledger/10 text-ledger border-ledger/30",
  rejected: "bg-sanction/10 text-sanction border-sanction/30",
  withdrawn: "bg-ink/10 text-ink-soft border-line",
};

function Badge({ s }: { s: string }) {
  return <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${STATUS_STYLE[s] ?? "border-line"}`}>{s}</span>;
}
const DECISION_SHORT: Record<string, string> = {
  shortlisted: "Shortlist", admitted: "Admit", rejected: "Reject",
};
function ProposedBadge({ s }: { s: string }) {
  // compact on the row (the full "Proposed: … · source" shows in the detail panel)
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-dashed border-ink/40 bg-ink/5 px-2 py-0.5 text-xs font-medium text-ink whitespace-nowrap">
      <span className="h-1.5 w-1.5 rounded-full bg-brass" /> {DECISION_SHORT[s] ?? s}
    </span>
  );
}

export default function AdmissionsPage() {
  const { ok, err } = useToast();
  const [data, setData] = useState<ListResp | null>(null);
  const [role, setRole] = useState<string>("");
  const [filter, setFilter] = useState<string>("");
  const [arms, setArms] = useState<Arm[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [applyPath, setApplyPath] = useState<string>("");
  const [admNo, setAdmNo] = useState(""); const [admArm, setAdmArm] = useState("");
  const [busy, setBusy] = useState(false);
  const [sel, setSel] = useState<Set<string>>(new Set());

  // auto-reconcile panel
  const [autoOpen, setAutoOpen] = useState(false);
  const [passMark, setPassMark] = useState("50");
  const [seats, setSeats] = useState("");

  const canApprove = role === "principal" || role === "super_admin";
  const canEnrol = role === "school_admin" || role === "super_admin";

  const load = useCallback(() => {
    const q = filter ? `?status=${filter}` : "";
    api<ListResp>(`/api/admissions/applicants${q}`).then(setData).catch(() => err("Could not load applicants"));
  }, [filter, err]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api<Me>("/api/auth/me").then((m) => setRole(m.role)).catch(() => {});
    api<Arm[]>("/api/academics/arms").then(setArms).catch(() => {});
    api<{ apply_path: string }>("/api/admissions/link").then((r) => setApplyPath(r.apply_path)).catch(() => {});
  }, []);

  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const fullLink = applyPath ? `${origin}${applyPath}` : "";

  function toggle(id: string) {
    setSel((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }
  function clearSel() { setSel(new Set()); }

  async function autoReconcile() {
    setBusy(true);
    try {
      const r = await api<{ proposed_total: number; not_tested: number }>("/api/admissions/reconcile/auto", {
        method: "POST", body: JSON.stringify({
          pass_mark: Number(passMark) || 0,
          seats_per_class: seats.trim() ? Number(seats) : null }) });
      ok(`Proposed ${r.proposed_total} decision${r.proposed_total === 1 ? "" : "s"}${r.not_tested ? ` · ${r.not_tested} not yet tested` : ""}.`);
      setAutoOpen(false); load();
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not reconcile"); }
    setBusy(false);
  }

  async function propose(status: string) {
    if (sel.size === 0) return;
    try {
      const r = await api<{ proposed: number }>("/api/admissions/reconcile/manual", {
        method: "POST", body: JSON.stringify({ applicant_ids: [...sel], proposed_status: status }) });
      ok(`Proposed ${DECISION_LABEL[status]} for ${r.proposed}.`); clearSel(); load();
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not propose"); }
  }

  async function clearProposals(ids: string[] | null) {
    try {
      const r = await api<{ cleared: number }>("/api/admissions/proposals/clear", {
        method: "POST", body: JSON.stringify({ applicant_ids: ids }) });
      ok(`Returned ${r.cleared} to review.`); clearSel(); load();
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not clear"); }
  }

  async function approve(ids: string[] | null) {
    setBusy(true);
    try {
      const r = await api<{ approved_total: number }>("/api/admissions/proposals/approve", {
        method: "POST", body: JSON.stringify({ applicant_ids: ids }) });
      ok(`Approved ${r.approved_total} decision${r.approved_total === 1 ? "" : "s"}.`); clearSel(); load();
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not approve"); }
    setBusy(false);
  }

  async function setStatus(a: Applicant, status: string) {
    try {
      await api(`/api/admissions/applicants/${a.id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
      ok(status === "applied" ? "Returned to the pool." : `Marked ${status}.`); load();
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not update"); }
  }

  async function admit(a: Applicant) {
    if (!admNo.trim()) return err("Enter an admission number");
    setBusy(true);
    try {
      await api(`/api/admissions/applicants/${a.id}/admit`, { method: "POST",
        body: JSON.stringify({ admission_number: admNo.trim(), arm_id: admArm || null }) });
      ok(`${a.name} enrolled as a student.`); setOpenId(null); setAdmNo(""); setAdmArm(""); load();
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not enrol"); }
    setBusy(false);
  }

  if (!data) return <div className="grid place-items-center py-20 text-ink-soft text-sm"><span className="spinner" /> Loading…</div>;
  const pending = data.pending ?? 0;

  return (
    <div className="max-w-4xl space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Admissions</h1>
          <p className="text-ink-soft text-sm mt-1">Applications from your school’s public admissions link.</p>
        </div>
        <Link href="/dashboard/admissions/test"
              className="shrink-0 rounded-md border border-ink text-ink px-4 py-2 text-sm font-medium hover:bg-ink hover:text-white">
          Entrance test
        </Link>
      </header>

      {/* shareable link */}
      {fullLink && (
        <div className="rounded-xl border border-line bg-card p-4 flex flex-wrap items-center gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs text-ink-soft">Your admissions link — share on WhatsApp or your website</p>
            <p className="font-medium truncate">{fullLink}</p>
          </div>
          <button onClick={() => { navigator.clipboard?.writeText(fullLink); ok("Link copied."); }}
                  className="shrink-0 rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft">Copy link</button>
        </div>
      )}

      {/* reconcile — automatic */}
      <div className="rounded-xl border border-line bg-card p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="font-semibold">Reconcile applications</p>
            <p className="text-xs text-ink-soft">Propose decisions in bulk, then the principal approves. Nothing reaches applicants until approval.</p>
          </div>
          <button onClick={() => setAutoOpen((o) => !o)}
                  className="shrink-0 rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft">
            {autoOpen ? "Close" : "Auto by score"}
          </button>
        </div>
        {autoOpen && (
          <div className="rounded-lg border border-line bg-paper/50 p-3 space-y-3">
            <p className="text-sm text-ink-soft">
              Applicants who sat the entrance test are ranked by score. Those at or above the pass mark are
              proposed for admission (up to the seats per class, if set); any above the mark but beyond the
              seats are proposed for shortlisting; the rest are proposed as not successful.
            </p>
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <label className="block text-xs text-ink-soft mb-1">Pass mark (%)</label>
                <input type="number" min={0} max={100} value={passMark} onChange={e => setPassMark(e.target.value)}
                       className="w-24 rounded-md border border-line bg-white px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs text-ink-soft mb-1">Seats per class (optional)</label>
                <input type="number" min={1} value={seats} onChange={e => setSeats(e.target.value)} placeholder="no limit"
                       className="w-32 rounded-md border border-line bg-white px-3 py-2 text-sm" />
              </div>
              <button onClick={autoReconcile} disabled={busy}
                      className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
                {busy ? "Working…" : "Propose from scores"}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* pending principal approval */}
      {pending > 0 && (
        <div className="rounded-xl border border-brass/40 bg-brass/5 p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="font-semibold text-ink">{pending} decision{pending === 1 ? "" : "s"} awaiting principal approval</p>
              <p className="text-xs text-ink-soft">
                {canApprove ? "Review below, then approve. Approved decisions become visible to applicants."
                            : "The principal must approve these before they take effect."}
              </p>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setFilter("pending")}
                      className="shrink-0 rounded-md border border-ink text-ink px-3 py-2 text-sm font-medium hover:bg-ink hover:text-white">Review</button>
              {canApprove && (
                <button onClick={() => approve(null)} disabled={busy}
                        className="shrink-0 rounded-md bg-ledger text-white px-4 py-2 text-sm font-medium hover:opacity-90 disabled:opacity-50">
                  {busy ? "Approving…" : "Approve all"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* status filters */}
      <div className="flex flex-wrap gap-2">
        <button onClick={() => { setFilter(""); clearSel(); }}
                className={`rounded-full px-3.5 py-1.5 text-sm font-medium ${filter===""?"bg-ink text-white":"border border-line"}`}>
          All <span className="tabular">{data.total}</span>
        </button>
        <button onClick={() => { setFilter("pending"); clearSel(); }}
                className={`rounded-full px-3.5 py-1.5 text-sm font-medium ${filter==="pending"?"bg-ink text-white":"border border-line"}`}>
          Pending approval <span className="tabular">{pending}</span>
        </button>
        {STATUSES.map((s) => (
          <button key={s} onClick={() => { setFilter(s); clearSel(); }}
                  className={`rounded-full px-3.5 py-1.5 text-sm font-medium capitalize ${filter===s?"bg-ink text-white":"border border-line"}`}>
            {s} <span className="tabular">{data.counts[s] ?? 0}</span>
          </button>
        ))}
      </div>

      {/* bulk action bar */}
      {sel.size > 0 && (
        <div className="sticky top-2 z-10 rounded-xl border border-ink bg-card shadow-sm p-3 flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium mr-1">{sel.size} selected</span>
          <button onClick={() => propose("shortlisted")} className="rounded-md border border-brass text-brass-ink px-3 py-1.5 text-sm font-medium hover:bg-brass/10">Propose shortlist</button>
          <button onClick={() => propose("admitted")} className="rounded-md border border-ledger text-ledger px-3 py-1.5 text-sm font-medium hover:bg-ledger hover:text-white">Propose admit</button>
          <button onClick={() => propose("rejected")} className="rounded-md border border-sanction text-sanction px-3 py-1.5 text-sm font-medium hover:bg-sanction hover:text-white">Propose reject</button>
          {canApprove && <button onClick={() => approve([...sel])} disabled={busy} className="rounded-md bg-ledger text-white px-3 py-1.5 text-sm font-medium hover:opacity-90 disabled:opacity-50">Approve selected</button>}
          <button onClick={() => clearProposals([...sel])} className="rounded-md border border-line px-3 py-1.5 text-sm font-medium hover:border-ink">Return</button>
          <button onClick={clearSel} className="ml-auto text-sm text-ink-soft underline underline-offset-2">Clear</button>
        </div>
      )}

      {data.applicants.length === 0 ? (
        <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-6">
          {filter === "pending" ? "No decisions are awaiting approval." : "No applications here yet."}
        </p>
      ) : (
        <div className="space-y-2">
          {data.applicants.map((a) => {
            const decided = a.status === "admitted" || a.status === "rejected";
            return (
            <div key={a.id} className="rounded-xl border border-line bg-card overflow-hidden">
              <div className="flex items-center gap-2 px-3 py-3">
                <input type="checkbox" aria-label={`Select ${a.name}`} checked={sel.has(a.id)}
                       onChange={() => toggle(a.id)} className="h-4 w-4 shrink-0" />
                <button onClick={() => { setOpenId(openId === a.id ? null : a.id); setAdmNo(""); setAdmArm(""); }}
                        className="min-w-0 flex-1 flex items-center justify-between gap-3 text-left">
                  <div className="min-w-0">
                    <p className="font-medium truncate">{a.name} <span className="text-ink-soft text-xs">· {a.applying_class}</span></p>
                    <p className="text-xs text-ink-soft truncate">{a.application_number} · {a.created_at}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {a.entrance_percent !== null && (
                      <span className={`text-xs tabular font-medium ${a.entrance_percent >= 50 ? "text-ledger" : "text-sanction"}`}>{a.entrance_percent}%</span>
                    )}
                    {a.proposed_status ? <ProposedBadge s={a.proposed_status} /> : <Badge s={a.status} />}
                  </div>
                </button>
              </div>

              {openId === a.id && (
                <div className="border-t border-line px-4 py-4 space-y-3 text-sm">
                  <div className="grid sm:grid-cols-2 gap-x-6 gap-y-1 text-ink-soft">
                    <p>Guardian: <span className="text-ink">{a.guardian_name}</span></p>
                    <p>Phone: <span className="text-ink">{a.guardian_phone}</span></p>
                    {a.guardian_email && <p>Email: <span className="text-ink">{a.guardian_email}</span></p>}
                    {a.previous_school && <p>Previous school: <span className="text-ink">{a.previous_school}</span></p>}
                    <p>Entrance test: <span className="text-ink">
                      {a.entrance_max != null ? `${a.entrance_score}/${a.entrance_max} (${a.entrance_percent}%)` : a.entrance_taken ? "taken" : "not taken"}
                    </span></p>
                    <p>Current status: <span className="text-ink capitalize">{a.status}</span>{a.decided_at ? <span className="text-ink-soft"> · approved {a.decided_at}</span> : null}</p>
                  </div>

                  {/* a decision is pending approval */}
                  {a.proposed_status && (
                    <div className="rounded-lg border border-brass/40 bg-brass/5 p-3 flex flex-wrap items-center gap-2">
                      <p className="text-sm">Proposed: <span className="font-semibold">{DECISION_LABEL[a.proposed_status]}</span>
                        {a.proposal_source ? <span className="text-ink-soft"> ({a.proposal_source})</span> : null} — awaiting principal approval.</p>
                      {canApprove && <button onClick={() => approve([a.id])} disabled={busy} className="rounded-md bg-ledger text-white px-3 py-1.5 text-sm font-medium hover:opacity-90 disabled:opacity-50">Approve</button>}
                      <button onClick={() => clearProposals([a.id])} className="rounded-md border border-line px-3 py-1.5 text-sm font-medium hover:border-ink">Return</button>
                    </div>
                  )}

                  {/* enrolment — only once admission is approved */}
                  {a.status === "admitted" && (
                    a.admitted_student_id ? (
                      <p className="text-ledger font-medium">✓ Enrolled as a student.</p>
                    ) : canEnrol ? (
                      <div className="rounded-lg border border-ledger/30 bg-ledger/5 p-3">
                        <p className="text-sm font-medium mb-2">Enrol this admitted applicant</p>
                        <div className="flex flex-wrap items-end gap-2">
                          <div><label className="block text-xs text-ink-soft mb-1">Admission number</label>
                            <input className="rounded-md border border-line bg-white px-3 py-2 text-sm" value={admNo} onChange={e=>setAdmNo(e.target.value)} placeholder="GSS/26/001" /></div>
                          <div><label className="block text-xs text-ink-soft mb-1">Class / arm</label>
                            <select className="rounded-md border border-line bg-white px-3 py-2 text-sm" value={admArm} onChange={e=>setAdmArm(e.target.value)}>
                              <option value="">Unassigned</option>
                              {arms.map(x=><option key={x.id} value={x.id}>{x.label}</option>)}</select></div>
                          <button onClick={() => admit(a)} disabled={busy}
                                  className="rounded-md bg-ledger text-white px-4 py-2 text-sm font-medium hover:opacity-90 disabled:opacity-50">
                            {busy ? "Enrolling…" : "Enrol → create student"}</button>
                        </div>
                      </div>
                    ) : (
                      <p className="text-ink-soft">Admitted — the school admin will enrol this applicant.</p>
                    )
                  )}

                  {/* administrative reset — available while no pending proposal */}
                  {!a.proposed_status && a.status !== "admitted" && (
                    <div className="flex flex-wrap gap-2">
                      {a.status !== "applied" && <button onClick={() => setStatus(a, "applied")} className="rounded-md border border-line px-3 py-1.5 text-sm font-medium hover:border-ink">Return to pool</button>}
                    </div>
                  )}
                  {decided && !a.proposed_status && a.status === "rejected" && (
                    <button onClick={() => setStatus(a, "applied")} className="rounded-md border border-line px-3 py-1.5 text-sm font-medium hover:border-ink">Return to pool</button>
                  )}
                </div>
              )}
            </div>
          );})}
        </div>
      )}
    </div>
  );
}
