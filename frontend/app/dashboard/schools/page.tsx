"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

type SchoolRow = {
  id: string; name: string; slug: string; state: string | null;
  phone: string | null; students: number; users: number;
  created_at: string | null;
};

function slugify(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
}

export default function SchoolsConsole() {
  const [schools, setSchools] = useState<SchoolRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [slugTouched, setSlugTouched] = useState(false);
  const [form, setForm] = useState({
    name: "", slug: "", state: "", phone: "",
    admin_first_name: "", admin_last_name: "", admin_email: "", admin_password: "",
  });
  // shown exactly once after creation — the credentials you hand to the school
  const [handover, setHandover] = useState<{ school: string; email: string; password: string } | null>(null);

  const load = useCallback(async () => {
    try { setSchools(await api<SchoolRow[]>("/api/schools")); }
    catch { setNotice({ kind: "err", text: "Could not load the schools list." }); }
  }, []);
  useEffect(() => { load(); }, [load]);

  function setName(name: string) {
    setForm((f) => ({ ...f, name, slug: slugTouched ? f.slug : slugify(name) }));
  }

  function generatePassword() {
    const chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789";
    let out = "";
    const rnd = new Uint32Array(10);
    crypto.getRandomValues(rnd);
    for (const n of rnd) out += chars[n % chars.length];
    setForm((f) => ({ ...f, admin_password: out }));
  }

  async function createSchool() {
    const required = ["name", "slug", "admin_first_name", "admin_last_name",
                      "admin_email", "admin_password"] as const;
    if (required.some((k) => !form[k].trim())) {
      setNotice({ kind: "err", text: "School name, slug, and the admin's name, email and password are all required." });
      return;
    }
    setBusy(true); setNotice(null);
    try {
      await api("/api/schools", {
        method: "POST",
        body: JSON.stringify({
          name: form.name.trim(), slug: form.slug.trim(),
          state: form.state.trim() || null, phone: form.phone.trim() || null,
          admin_first_name: form.admin_first_name.trim(),
          admin_last_name: form.admin_last_name.trim(),
          admin_email: form.admin_email.trim().toLowerCase(),
          admin_password: form.admin_password,
        }),
      });
      setHandover({ school: form.name.trim(), email: form.admin_email.trim().toLowerCase(),
                    password: form.admin_password });
      setForm({ name: "", slug: "", state: "", phone: "",
                admin_first_name: "", admin_last_name: "", admin_email: "", admin_password: "" });
      setSlugTouched(false);
      await load();
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not create the school." });
    } finally { setBusy(false); }
  }

  return (
    <div className="max-w-4xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Schools</h1>
        <p className="text-sm text-ink-soft mt-1">
          The platform console. Each school you create here is a fully isolated
          tenant with its own admin — nothing is shared between schools.
        </p>
      </header>

      {notice && (
        <p role="status" className={`text-sm ${notice.kind === "ok" ? "text-ledger" : "text-sanction"}`}>
          {notice.text}
        </p>
      )}

      {/* credentials handover — shown once */}
      {handover && (
        <section className="rounded-lg border border-ledger/40 bg-ledger/10 p-4 space-y-2">
          <p className="text-sm font-semibold">{handover.school} is ready.</p>
          <p className="text-sm">
            Send these sign-in details to the school&apos;s admin — they are shown
            only this once:
          </p>
          <div className="rounded-md bg-white border border-line p-3 font-mono text-sm space-y-1">
            <div>Site: &nbsp;{typeof window !== "undefined" ? window.location.origin : ""}/login</div>
            <div>Email: {handover.email}</div>
            <div>Password: {handover.password}</div>
          </div>
          <p className="text-xs text-ink-soft">
            Advise them to change the password after first sign-in (Account page).
            When they sign in, a setup checklist walks them through sessions,
            classes, subjects, students and staff.
          </p>
          <button onClick={() => setHandover(null)}
                  className="text-xs text-ink-soft underline underline-offset-2">
            I have copied these — dismiss
          </button>
        </section>
      )}

      {/* create a school */}
      <section className="rounded-lg border border-line bg-card p-4 space-y-3">
        <p className="text-sm font-medium">Onboard a new school</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <input value={form.name} placeholder="School name — e.g. ECWA Academy Gyawana"
                 onChange={(e) => setName(e.target.value)}
                 className="rounded border border-line px-2 py-1.5 text-sm sm:col-span-2" />
          <input value={form.slug} placeholder="slug (web-safe id, auto-filled)"
                 onChange={(e) => { setSlugTouched(true); setForm({ ...form, slug: e.target.value }); }}
                 className="rounded border border-line px-2 py-1.5 text-sm font-mono" />
          <input value={form.state} placeholder="State (e.g. Adamawa)"
                 onChange={(e) => setForm({ ...form, state: e.target.value })}
                 className="rounded border border-line px-2 py-1.5 text-sm" />
          <input value={form.phone} placeholder="School phone (optional)"
                 onChange={(e) => setForm({ ...form, phone: e.target.value })}
                 className="rounded border border-line px-2 py-1.5 text-sm sm:col-span-2" />
        </div>

        <p className="text-xs font-medium text-ink-soft pt-1">The school&apos;s first admin</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <input value={form.admin_first_name} placeholder="First name"
                 onChange={(e) => setForm({ ...form, admin_first_name: e.target.value })}
                 className="rounded border border-line px-2 py-1.5 text-sm" />
          <input value={form.admin_last_name} placeholder="Last name"
                 onChange={(e) => setForm({ ...form, admin_last_name: e.target.value })}
                 className="rounded border border-line px-2 py-1.5 text-sm" />
          <input value={form.admin_email} placeholder="Admin email" type="email"
                 onChange={(e) => setForm({ ...form, admin_email: e.target.value })}
                 className="rounded border border-line px-2 py-1.5 text-sm" />
          <div className="flex gap-2">
            <input value={form.admin_password} placeholder="Temporary password"
                   onChange={(e) => setForm({ ...form, admin_password: e.target.value })}
                   className="flex-1 rounded border border-line px-2 py-1.5 text-sm font-mono" />
            <button onClick={generatePassword}
                    className="rounded-md border border-line px-3 py-1.5 text-xs hover:border-ink">
              Generate
            </button>
          </div>
        </div>

        <button onClick={createSchool} disabled={busy}
                className="rounded-md bg-ink text-white px-5 py-2.5 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
          {busy ? "Creating…" : "Create school + admin"}
        </button>
      </section>

      {/* the estate */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-ink-soft uppercase tracking-wide">
          All schools {schools ? `(${schools.length})` : ""}
        </h2>
        {schools === null && <p className="text-sm text-ink-soft">Loading…</p>}
        {schools && schools.length === 0 && (
          <p className="text-sm text-ink-soft">No schools yet — create the first above.</p>
        )}
        {schools && schools.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-line bg-card">
            <table className="min-w-[560px] w-full text-sm">
              <thead>
                <tr className="bg-ink text-white text-left">
                  <th className="px-3 py-2 font-medium">School</th>
                  <th className="px-3 py-2 font-medium">State</th>
                  <th className="px-3 py-2 font-medium text-right">Students</th>
                  <th className="px-3 py-2 font-medium text-right">Accounts</th>
                  <th className="px-3 py-2 font-medium">Onboarded</th>
                </tr>
              </thead>
              <tbody>
                {schools.map((s, i) => (
                  <tr key={s.id} className={i % 2 ? "bg-paper/50" : ""}>
                    <td className="px-3 py-2">
                      <div className="font-medium">{s.name}</div>
                      <div className="text-xs text-ink-soft font-mono">{s.slug}</div>
                    </td>
                    <td className="px-3 py-2">{s.state ?? "—"}</td>
                    <td className="px-3 py-2 text-right tabular">{s.students}</td>
                    <td className="px-3 py-2 text-right tabular">{s.users}</td>
                    <td className="px-3 py-2 text-xs text-ink-soft">{s.created_at ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
