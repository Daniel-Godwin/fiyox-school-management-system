"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, getToken, ApiError } from "@/lib/api";

const CONTACT_EMAIL = process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? "";
const CONTACT_PHONE = process.env.NEXT_PUBLIC_CONTACT_PHONE ?? "";

const FEATURES: { title: string; body: string; icon: React.ReactNode }[] = [
  {
    title: "Results & report cards",
    body: "Teachers enter scores once. Totals, averages, positions and grades compute themselves, and branded report cards print at the click of a button.",
    icon: (<path d="M6 3h9l5 5v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm9 1.5V8h3.5M8 13h8M8 16h8M8 10h3" />),
  },
  {
    title: "Fees & receipts",
    body: "Record payments, print itemised receipts with the school's stamp, and see at a glance who has paid and who still owes.",
    icon: (<path d="M3 7h18v10H3V7Zm0 3h18M7 14h4M17 14h.01" />),
  },
  {
    title: "Attendance",
    body: "A daily register that takes seconds to mark and rolls up into each student's report card automatically.",
    icon: (<path d="M4 5h16v16H4V5Zm0 4h16M9 3v4M15 3v4m-7 8 2 2 4-4" />),
  },
  {
    title: "Parent portal",
    body: "Parents sign in to see their children's published results and outstanding fees — no calls to the office.",
    icon: (<path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 8a7 7 0 0 1 14 0" />),
  },
  {
    title: "Daily reconciliation",
    body: "When both the admin and bursar take cash, the day's takings are counted against the system — every naira named, timed and referenced.",
    icon: (<path d="M4 4h16v16H4V4Zm4 4h8M8 12h8M8 16h5" />),
  },
  {
    title: "Your records, yours",
    body: "Export every student, result and payment to one Excel file whenever you like. The school's records belong to the school.",
    icon: (<path d="M12 3v12m0 0 4-4m-4 4-4-4M5 21h14" />),
  },
];

export default function Landing() {
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => { setSignedIn(!!getToken()); }, []);

  return (
    <div className="min-h-screen bg-paper text-ink">
      {/* top bar */}
      <header className="sticky top-0 z-40 border-b border-white/10 bg-ink text-white">
        <div className="mx-auto max-w-6xl flex items-center justify-between px-5 h-14">
          <span className="text-xl font-extrabold tracking-tight">Fiyox</span>
          <nav className="flex items-center gap-5 text-sm">
            <a href="#features" className="hidden sm:inline text-white/75 hover:text-white">What it does</a>
            <a href="#demo" className="hidden sm:inline text-white/75 hover:text-white">Request a demo</a>
            <Link href={signedIn ? "/dashboard" : "/login"}
                  className="rounded-md border border-brass/70 text-brass px-3 py-1.5 font-medium hover:bg-brass hover:text-ink transition-colors">
              {signedIn ? "Go to dashboard" : "Sign in"}
            </Link>
          </nav>
        </div>
      </header>

      {/* hero */}
      <section className="bg-ink text-white">
        <div className="mx-auto max-w-6xl grid lg:grid-cols-[1.05fr_0.95fr] gap-10 px-5 pt-14 pb-16 lg:pt-20 lg:pb-24 items-center">
          <div>
            <h1 className="text-4xl sm:text-5xl font-extrabold leading-[1.08] tracking-tight">
              The whole school, in one place your staff can actually run.
            </h1>
            <p className="mt-5 text-base sm:text-lg text-white/80 max-w-xl leading-relaxed">
              Fiyox keeps results, fees, attendance and parent communication together —
              built for the way Nigerian secondary schools really work, from continuous
              assessment to WAEC-style grades and term report cards.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <a href="#demo"
                 className="rounded-md bg-brass text-ink px-5 py-3 text-sm font-semibold hover:brightness-105">
                Request a demo
              </a>
              <Link href="/login"
                    className="rounded-md border border-white/25 px-5 py-3 text-sm font-semibold text-white hover:bg-white/10">
                Sign in
              </Link>
            </div>
            <p className="mt-6 text-sm text-white/55">
              Set up for your school, with staff trained live. Free to pilot for a term.
            </p>
          </div>

          {/* hero visual: the report card, the product's signature artifact */}
          <div className="relative">
            <div className="absolute -inset-3 rounded-2xl bg-brass/10 blur-xl" aria-hidden />
            <div className="relative rounded-xl bg-white text-ink shadow-2xl ring-1 ring-black/5 overflow-hidden">
              <div className="bg-ink text-white px-5 py-3 flex items-center gap-3">
                <span className="grid h-9 w-9 place-items-center rounded-full bg-brass text-ink font-bold">GS</span>
                <div className="leading-tight">
                  <div className="text-sm font-semibold">Government Secondary School</div>
                  <div className="text-[11px] text-white/70">Student report card · First term</div>
                </div>
              </div>
              <div className="p-5">
                <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-3 text-[13px]">
                  <div className="font-semibold text-ink-soft pb-1">Subject</div>
                  <div className="font-semibold text-ink-soft pb-1 text-right">Total</div>
                  <div className="font-semibold text-ink-soft pb-1 text-right">Grade</div>
                  <div className="font-semibold text-ink-soft pb-1 text-right">Pos.</div>
                  {[
                    ["Mathematics", "77", "A1", "2nd"],
                    ["English Language", "63", "C4", "2nd"],
                    ["Basic Science", "71", "B2", "3rd"],
                    ["Civic Education", "87", "A1", "1st"],
                  ].map((r) => (
                    <div key={r[0]} className="contents">
                      <div className="border-t border-line py-1.5">{r[0]}</div>
                      <div className="border-t border-line py-1.5 text-right tabular-nums">{r[1]}</div>
                      <div className="border-t border-line py-1.5 text-right font-medium">{r[2]}</div>
                      <div className="border-t border-line py-1.5 text-right text-ink-soft">{r[3]}</div>
                    </div>
                  ))}
                </div>
                <div className="mt-4 flex items-center justify-between rounded-lg bg-paper px-4 py-3">
                  <div>
                    <div className="text-[11px] text-ink-soft">Average</div>
                    <div className="text-lg font-bold tabular-nums">74.5%</div>
                  </div>
                  <div className="text-right">
                    <div className="text-[11px] text-ink-soft">Position in class</div>
                    <div className="text-lg font-bold">1 of 42</div>
                  </div>
                  <div className="text-right">
                    <div className="text-[11px] text-ink-soft">Status</div>
                    <div className="text-lg font-bold text-ledger">Promoted</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* features */}
      <section id="features" className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
        <h2 className="text-2xl sm:text-3xl font-bold tracking-tight max-w-2xl">
          Everything a term asks of your office, handled in one system.
        </h2>
        <div className="mt-10 grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-xl border border-line bg-card p-5">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
                   strokeLinecap="round" strokeLinejoin="round"
                   className="h-7 w-7 text-brass">
                {f.icon}
              </svg>
              <h3 className="mt-4 font-semibold">{f.title}</h3>
              <p className="mt-1.5 text-sm text-ink-soft leading-relaxed">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* trust band */}
      <section className="bg-ink text-white">
        <div className="mx-auto max-w-6xl px-5 py-14 grid sm:grid-cols-3 gap-8">
          {[
            ["Built for Nigerian schools", "Sessions, three terms, class arms, CA-and-exam grading and WAEC-style bands — the way your school already works, not a foreign template bent to fit."],
            ["Every change is accountable", "Who changed a score, who took a payment, and when — each action is logged. Accountability your proprietor can see."],
            ["Works on the phones you have", "Teachers, bursars and parents use it from an ordinary phone browser. Nothing to install."],
          ].map(([t, b]) => (
            <div key={t}>
              <h3 className="font-semibold text-brass">{t}</h3>
              <p className="mt-2 text-sm text-white/75 leading-relaxed">{b}</p>
            </div>
          ))}
        </div>
      </section>

      {/* request a demo */}
      <section id="demo" className="mx-auto max-w-6xl px-5 py-16 lg:py-20 grid lg:grid-cols-[0.9fr_1.1fr] gap-10 items-start">
        <div>
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">See it with your own school in mind.</h2>
          <p className="mt-4 text-ink-soft leading-relaxed max-w-md">
            Tell us about your school and we will arrange a short walkthrough. There is
            no cost and no obligation — the aim is simply to show you whether Fiyox would
            make your term lighter.
          </p>
          {(CONTACT_EMAIL || CONTACT_PHONE) && (
            <div className="mt-6 text-sm text-ink-soft space-y-1">
              {CONTACT_PHONE && <p>Call or WhatsApp: <span className="text-ink font-medium">{CONTACT_PHONE}</span></p>}
              {CONTACT_EMAIL && <p>Email: <span className="text-ink font-medium">{CONTACT_EMAIL}</span></p>}
            </div>
          )}
        </div>
        <DemoForm />
      </section>

      {/* footer */}
      <footer className="bg-ink text-white/70">
        <div className="mx-auto max-w-6xl px-5 py-8 flex flex-col sm:flex-row items-center justify-between gap-3 text-sm">
          <span className="font-extrabold text-white text-lg">Fiyox</span>
          <span>School management for Nigerian secondary schools.</span>
          <Link href="/login" className="text-brass hover:underline">Sign in</Link>
        </div>
      </footer>
    </div>
  );
}

function DemoForm() {
  const [form, setForm] = useState({ school_name: "", contact_name: "", email: "", phone: "", message: "" });
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!form.school_name.trim() || !form.contact_name.trim() || !form.email.trim()) {
      setError("Please give your school name, your name and an email."); return;
    }
    setBusy(true);
    try {
      await api("/api/demo-requests", { method: "POST", body: JSON.stringify(form) });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send your request. Please try again.");
    } finally { setBusy(false); }
  }

  if (done) {
    return (
      <div className="rounded-xl border border-ledger/40 bg-ledger/5 p-6">
        <h3 className="font-semibold text-ledger">Request received.</h3>
        <p className="mt-2 text-sm text-ink-soft">
          Thank you, {form.contact_name.split(" ")[0] || "there"}. We will be in touch
          shortly to arrange a time that suits {form.school_name || "your school"}.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="rounded-xl border border-line bg-card p-5 sm:p-6 space-y-3">
      <div className="grid sm:grid-cols-2 gap-3">
        <Field label="School name" value={form.school_name} onChange={set("school_name")} placeholder="e.g. Government Secondary School" />
        <Field label="Your name" value={form.contact_name} onChange={set("contact_name")} placeholder="Principal / proprietor" />
        <Field label="Email" type="email" value={form.email} onChange={set("email")} placeholder="you@example.com" />
        <Field label="Phone (optional)" value={form.phone} onChange={set("phone")} placeholder="080…" />
      </div>
      <label className="block">
        <span className="block text-xs font-medium text-ink-soft mb-1">Anything you'd like us to know (optional)</span>
        <textarea value={form.message} onChange={set("message")} rows={3}
                  className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm"
                  placeholder="Number of students, when your term starts, questions…" />
      </label>
      {error && <p className="text-sm text-sanction">{error}</p>}
      <button type="submit" disabled={busy}
              className="w-full rounded-md bg-ledger text-white px-4 py-3 text-sm font-semibold hover:brightness-110 disabled:opacity-50">
        {busy ? "Sending…" : "Request a demo"}
      </button>
      <p className="text-xs text-ink-soft text-center">We use your details only to contact you about Fiyox.</p>
    </form>
  );
}

function Field({ label, value, onChange, placeholder, type = "text" }: {
  label: string; value: string; placeholder?: string; type?: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-ink-soft mb-1">{label}</span>
      <input type={type} value={value} onChange={onChange} placeholder={placeholder}
             className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm" />
    </label>
  );
}
