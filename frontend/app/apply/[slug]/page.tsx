"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";

type Info = {
  school: { name: string; slug: string; state: string | null; logo_url: string | null; primary_color: string | null };
  classes: { id: string; name: string }[];
};
type ApplyResult = {
  application_number: string; access_code: string;
  entrance_test: { title: string; duration_minutes: number; question_count: number } | null;
  message: string;
};
type Status = {
  application_number: string; name: string; applying_class: string; status: string;
  entrance_available: boolean; entrance_taken: boolean;
  entrance_score: number | null; entrance_max: number | null;
};

const field = "w-full rounded-md border border-line bg-white px-3 py-2 text-sm";
const label = "block text-xs font-medium text-ink-soft mb-1";
const STATUS_LABEL: Record<string, string> = {
  applied: "Received", shortlisted: "Shortlisted", admitted: "Admitted",
  rejected: "Not successful", withdrawn: "Withdrawn",
};

export default function ApplyPage() {
  const { slug } = useParams<{ slug: string }>();
  const [info, setInfo] = useState<Info | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [mode, setMode] = useState<"apply" | "status">("apply");

  const [form, setForm] = useState({
    first_name: "", last_name: "", other_names: "", gender: "male",
    date_of_birth: "", applying_class_id: "", previous_school: "", address: "",
    guardian_name: "", guardian_phone: "", guardian_email: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<ApplyResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // status check
  const [sNo, setSNo] = useState(""); const [sCode, setSCode] = useState("");
  const [status, setStatus] = useState<Status | null>(null);
  const [sErr, setSErr] = useState<string | null>(null);

  useEffect(() => {
    api<Info>(`/api/admissions/${slug}/info`).then(setInfo).catch(() => setNotFound(true));
  }, [slug]);

  const submit = useCallback(async () => {
    setErr(null);
    if (!form.first_name || !form.last_name) return setErr("Enter the applicant's name");
    if (!form.applying_class_id) return setErr("Choose the class you are applying for");
    if (!form.guardian_name || !form.guardian_phone) return setErr("Enter a parent/guardian name and phone");
    setSubmitting(true);
    try {
      const payload: Record<string, unknown> = { ...form };
      if (!payload.date_of_birth) delete payload.date_of_birth;
      if (!payload.guardian_email) delete payload.guardian_email;
      const res = await api<ApplyResult>(`/api/admissions/${slug}/apply`, {
        method: "POST", body: JSON.stringify(payload) });
      setResult(res);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not submit your application.");
    }
    setSubmitting(false);
  }, [form, slug]);

  async function check() {
    setSErr(null); setStatus(null);
    try {
      const s = await api<Status>(`/api/admissions/${slug}/status`, {
        method: "POST", body: JSON.stringify({ application_number: sNo.trim(), access_code: sCode.trim() }) });
      setStatus(s);
    } catch (e) {
      setSErr(e instanceof ApiError ? e.message : "Could not find that application.");
    }
  }

  if (notFound) {
    return <main className="min-h-screen grid place-items-center bg-paper px-5">
      <p className="text-ink-soft text-sm">This admissions page isn’t available.</p></main>;
  }
  if (!info) {
    return <main className="min-h-screen grid place-items-center bg-paper text-ink-soft text-sm">
      <span className="spinner" /> Loading…</main>;
  }

  return (
    <main className="min-h-screen bg-paper">
      <header className="bg-ink text-white">
        <div className="mx-auto max-w-2xl px-5 py-5 flex items-center gap-3">
          {info.school.logo_url
            ? <img src={info.school.logo_url} alt="" style={{ height: 40, width: "auto" }} />
            : <img src="/fiyox-logo-white.png" alt="Fiyox" style={{ height: 28, width: "auto" }} />}
          <div>
            <h1 className="font-bold leading-tight">{info.school.name}</h1>
            <p className="text-xs text-white/70">Admissions{info.school.state ? ` · ${info.school.state}` : ""}</p>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-2xl px-5 py-8">
        {/* confirmation */}
        {result ? (
          <div className="bg-card border border-line rounded-xl p-6 card">
            <p className="text-3xl mb-2">✓</p>
            <h2 className="text-xl font-bold">Application received</h2>
            <p className="text-ink-soft text-sm mt-1">{result.message}</p>
            <div className="mt-4 grid sm:grid-cols-2 gap-3">
              <div className="rounded-lg border border-line p-3">
                <p className="text-xs text-ink-soft">Application number</p>
                <p className="font-bold tabular text-lg">{result.application_number}</p>
              </div>
              <div className="rounded-lg border border-line p-3">
                <p className="text-xs text-ink-soft">Access code</p>
                <p className="font-bold tabular text-lg tracking-widest">{result.access_code}</p>
              </div>
            </div>
            <p className="text-xs text-sanction mt-2">Write these down — you need them to check your status{result.entrance_test ? " and to sit the entrance test" : ""}.</p>
            {result.entrance_test && (
              <Link href={`/apply/${slug}/test?app=${encodeURIComponent(result.application_number)}&code=${encodeURIComponent(result.access_code)}`}
                    className="mt-4 inline-block rounded-md bg-ink text-white px-5 py-2.5 text-sm font-medium hover:bg-ink-soft">
                Take the entrance test now ({result.entrance_test.question_count} questions · {result.entrance_test.duration_minutes} min)
              </Link>
            )}
            <div className="mt-4">
              <button onClick={() => { setResult(null); setMode("status"); setSNo(result.application_number); setSCode(result.access_code); }}
                      className="text-sm text-ink underline underline-offset-2">Check application status</button>
            </div>
          </div>
        ) : (
          <>
            <div className="flex gap-2 mb-5">
              <button onClick={() => setMode("apply")}
                      className={`rounded-full px-4 py-1.5 text-sm font-medium ${mode==="apply"?"bg-ink text-white":"border border-line"}`}>Apply</button>
              <button onClick={() => setMode("status")}
                      className={`rounded-full px-4 py-1.5 text-sm font-medium ${mode==="status"?"bg-ink text-white":"border border-line"}`}>Check status</button>
            </div>

            {mode === "apply" ? (
              <div className="bg-card border border-line rounded-xl p-5 sm:p-6 card space-y-4">
                <div>
                  <h2 className="text-lg font-bold">Apply for admission</h2>
                  <p className="text-ink-soft text-sm">Fill in the applicant’s details. It takes about two minutes.</p>
                </div>
                <div className="grid sm:grid-cols-2 gap-3">
                  <div><label className={label}>First name *</label><input className={field} value={form.first_name} onChange={e=>setForm({...form,first_name:e.target.value})} /></div>
                  <div><label className={label}>Last name *</label><input className={field} value={form.last_name} onChange={e=>setForm({...form,last_name:e.target.value})} /></div>
                  <div><label className={label}>Other names</label><input className={field} value={form.other_names} onChange={e=>setForm({...form,other_names:e.target.value})} /></div>
                  <div><label className={label}>Gender</label>
                    <select className={field} value={form.gender} onChange={e=>setForm({...form,gender:e.target.value})}>
                      <option value="male">Male</option><option value="female">Female</option></select></div>
                  <div><label className={label}>Date of birth</label><input type="date" className={field} value={form.date_of_birth} onChange={e=>setForm({...form,date_of_birth:e.target.value})} /></div>
                  <div><label className={label}>Class applying for *</label>
                    <select className={field} value={form.applying_class_id} onChange={e=>setForm({...form,applying_class_id:e.target.value})}>
                      <option value="">Select…</option>
                      {info.classes.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
                  <div className="sm:col-span-2"><label className={label}>Previous school</label><input className={field} value={form.previous_school} onChange={e=>setForm({...form,previous_school:e.target.value})} /></div>
                  <div className="sm:col-span-2"><label className={label}>Home address</label><input className={field} value={form.address} onChange={e=>setForm({...form,address:e.target.value})} /></div>
                </div>
                <div className="pt-2 border-t border-line">
                  <p className="text-sm font-semibold mb-2">Parent / guardian</p>
                  <div className="grid sm:grid-cols-3 gap-3">
                    <div><label className={label}>Name *</label><input className={field} value={form.guardian_name} onChange={e=>setForm({...form,guardian_name:e.target.value})} /></div>
                    <div><label className={label}>Phone *</label><input className={field} value={form.guardian_phone} onChange={e=>setForm({...form,guardian_phone:e.target.value})} /></div>
                    <div><label className={label}>Email</label><input className={field} value={form.guardian_email} onChange={e=>setForm({...form,guardian_email:e.target.value})} /></div>
                  </div>
                </div>
                {err && <p className="text-sm text-sanction">{err}</p>}
                <button onClick={submit} disabled={submitting}
                        className="rounded-md bg-ink text-white px-6 py-2.5 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
                  {submitting ? "Submitting…" : "Submit application"}
                </button>
              </div>
            ) : (
              <div className="bg-card border border-line rounded-xl p-5 sm:p-6 card space-y-4">
                <div>
                  <h2 className="text-lg font-bold">Check your application</h2>
                  <p className="text-ink-soft text-sm">Enter the application number and access code you were given.</p>
                </div>
                <div className="grid sm:grid-cols-2 gap-3">
                  <div><label className={label}>Application number</label><input className={field} value={sNo} onChange={e=>setSNo(e.target.value)} placeholder="APP/26/0001" /></div>
                  <div><label className={label}>Access code</label><input className={field} value={sCode} onChange={e=>setSCode(e.target.value)} placeholder="6-character code" /></div>
                </div>
                {sErr && <p className="text-sm text-sanction">{sErr}</p>}
                <button onClick={check} className="rounded-md bg-ink text-white px-5 py-2 text-sm font-medium hover:bg-ink-soft">Check</button>

                {status && (
                  <div className="rounded-lg border border-line p-4 mt-2">
                    <p className="font-semibold">{status.name} · {status.applying_class}</p>
                    <p className="mt-1 text-sm">Status: <span className="font-medium text-ink">{STATUS_LABEL[status.status] ?? status.status}</span></p>
                    {status.entrance_taken && status.entrance_max
                      ? <p className="text-sm text-ink-soft mt-1">Entrance test: {status.entrance_score}/{status.entrance_max}</p>
                      : status.entrance_available
                        ? <Link href={`/apply/${slug}/test?app=${encodeURIComponent(status.application_number)}&code=${encodeURIComponent(sCode.trim())}`}
                                className="mt-2 inline-block rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft">Take the entrance test</Link>
                        : null}
                  </div>
                )}
              </div>
            )}
          </>
        )}

        <p className="text-center text-xs text-ink-soft mt-8">Powered by Fiyox</p>
      </div>
    </main>
  );
}
