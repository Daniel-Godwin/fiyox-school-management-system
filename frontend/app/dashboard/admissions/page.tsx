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
  entrance_score: number | null; entrance_max: number | null; entrance_percent: number | null;
  admitted_student_id: string | null; created_at: string;
};
type ListResp = { counts: Record<string, number>; total: number; applicants: Applicant[] };
type Arm = { id: string; label: string };

const STATUSES = ["applied", "shortlisted", "admitted", "rejected"];
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

export default function AdmissionsPage() {
  const { ok, err } = useToast();
  const [data, setData] = useState<ListResp | null>(null);
  const [filter, setFilter] = useState<string>("");
  const [arms, setArms] = useState<Arm[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [applyPath, setApplyPath] = useState<string>("");
  const [admNo, setAdmNo] = useState(""); const [admArm, setAdmArm] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    const q = filter ? `?status=${filter}` : "";
    api<ListResp>(`/api/admissions/applicants${q}`).then(setData).catch(() => err("Could not load applicants"));
  }, [filter, err]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api<Arm[]>("/api/academics/arms").then(setArms).catch(() => {});
    api<{ apply_path: string }>("/api/admissions/link").then((r) => setApplyPath(r.apply_path)).catch(() => {});
  }, []);

  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const fullLink = applyPath ? `${origin}${applyPath}` : "";

  async function setStatus(a: Applicant, status: string) {
    try {
      await api(`/api/admissions/applicants/${a.id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
      ok(`Marked ${status}.`); load();
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not update"); }
  }

  async function admit(a: Applicant) {
    if (!admNo.trim()) return err("Enter an admission number");
    setBusy(true);
    try {
      await api(`/api/admissions/applicants/${a.id}/admit`, { method: "POST",
        body: JSON.stringify({ admission_number: admNo.trim(), arm_id: admArm || null }) });
      ok(`${a.name} admitted as a student.`); setOpenId(null); setAdmNo(""); setAdmArm(""); load();
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not admit"); }
    setBusy(false);
  }

  if (!data) return <div className="grid place-items-center py-20 text-ink-soft text-sm"><span className="spinner" /> Loading…</div>;

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

      {/* status filters */}
      <div className="flex flex-wrap gap-2">
        <button onClick={() => setFilter("")}
                className={`rounded-full px-3.5 py-1.5 text-sm font-medium ${filter===""?"bg-ink text-white":"border border-line"}`}>
          All <span className="tabular">{data.total}</span>
        </button>
        {STATUSES.map((s) => (
          <button key={s} onClick={() => setFilter(s)}
                  className={`rounded-full px-3.5 py-1.5 text-sm font-medium capitalize ${filter===s?"bg-ink text-white":"border border-line"}`}>
            {s} <span className="tabular">{data.counts[s] ?? 0}</span>
          </button>
        ))}
      </div>

      {data.applicants.length === 0 ? (
        <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-6">
          No applications yet. Share your admissions link above to start receiving them.
        </p>
      ) : (
        <div className="space-y-2">
          {data.applicants.map((a) => (
            <div key={a.id} className="rounded-xl border border-line bg-card overflow-hidden">
              <button onClick={() => { setOpenId(openId === a.id ? null : a.id); setAdmNo(""); setAdmArm(""); }}
                      className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-paper/50">
                <div className="min-w-0">
                  <p className="font-medium truncate">{a.name} <span className="text-ink-soft text-xs">· {a.applying_class}</span></p>
                  <p className="text-xs text-ink-soft">{a.application_number} · {a.created_at}</p>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  {a.entrance_percent !== null && (
                    <span className={`text-xs tabular font-medium ${a.entrance_percent >= 50 ? "text-ledger" : "text-sanction"}`}>{a.entrance_percent}%</span>
                  )}
                  <Badge s={a.status} />
                </div>
              </button>

              {openId === a.id && (
                <div className="border-t border-line px-4 py-4 space-y-3 text-sm">
                  <div className="grid sm:grid-cols-2 gap-x-6 gap-y-1 text-ink-soft">
                    <p>Guardian: <span className="text-ink">{a.guardian_name}</span></p>
                    <p>Phone: <span className="text-ink">{a.guardian_phone}</span></p>
                    {a.guardian_email && <p>Email: <span className="text-ink">{a.guardian_email}</span></p>}
                    {a.previous_school && <p>Previous school: <span className="text-ink">{a.previous_school}</span></p>}
                    {a.entrance_max != null && <p>Entrance test: <span className="text-ink">{a.entrance_score}/{a.entrance_max}</span></p>}
                  </div>

                  {a.status === "admitted" ? (
                    <p className="text-ledger font-medium">✓ Admitted as a student{a.admitted_student_id ? "." : ""}</p>
                  ) : (
                    <>
                      <div className="flex flex-wrap gap-2">
                        {a.status !== "shortlisted" && <button onClick={() => setStatus(a, "shortlisted")} className="rounded-md border border-brass text-brass-ink px-3 py-1.5 text-sm font-medium hover:bg-brass/10">Shortlist</button>}
                        {a.status !== "applied" && <button onClick={() => setStatus(a, "applied")} className="rounded-md border border-line px-3 py-1.5 text-sm font-medium hover:border-ink">Reset to applied</button>}
                        {a.status !== "rejected" && <button onClick={() => setStatus(a, "rejected")} className="rounded-md border border-sanction text-sanction px-3 py-1.5 text-sm font-medium hover:bg-sanction hover:text-white">Not successful</button>}
                      </div>
                      <div className="rounded-lg border border-ledger/30 bg-ledger/5 p-3">
                        <p className="text-sm font-medium mb-2">Admit this applicant</p>
                        <div className="flex flex-wrap items-end gap-2">
                          <div><label className="block text-xs text-ink-soft mb-1">Admission number</label>
                            <input className="rounded-md border border-line bg-white px-3 py-2 text-sm" value={admNo} onChange={e=>setAdmNo(e.target.value)} placeholder="GSS/26/001" /></div>
                          <div><label className="block text-xs text-ink-soft mb-1">Class / arm</label>
                            <select className="rounded-md border border-line bg-white px-3 py-2 text-sm" value={admArm} onChange={e=>setAdmArm(e.target.value)}>
                              <option value="">Unassigned</option>
                              {arms.map(x=><option key={x.id} value={x.id}>{x.label}</option>)}</select></div>
                          <button onClick={() => admit(a)} disabled={busy}
                                  className="rounded-md bg-ledger text-white px-4 py-2 text-sm font-medium hover:opacity-90 disabled:opacity-50">
                            {busy ? "Admitting…" : "Admit → create student"}</button>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
