"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

type Role = "school_admin" | "bursar" | "teacher" | "parent" | "student";
type UserRow = {
  id: string; email: string; role: Role; first_name: string; last_name: string;
  phone: string | null; is_active: boolean;
};
type Student = { id: string; admission_number: string; first_name: string; last_name: string };

const ROLES: { value: Role; label: string }[] = [
  { value: "teacher", label: "Teacher" },
  { value: "bursar", label: "Bursar" },
  { value: "parent", label: "Parent" },
  { value: "student", label: "Student" },
  { value: "school_admin", label: "School admin" },
];

const ROLE_LABEL: Record<string, string> = Object.fromEntries(
  ROLES.map((r) => [r.value, r.label]));

export default function UsersPage() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [students, setStudents] = useState<Student[]>([]);
  const [filter, setFilter] = useState<Role | "">("");
  const [form, setForm] = useState({
    email: "", role: "teacher" as Role, first_name: "", last_name: "",
    phone: "", password: "", student_id: "", ward_ids: [] as string[],
  });
  const [reveal, setReveal] = useState<{ email: string; temp: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const [u, s] = await Promise.all([
        api<UserRow[]>(`/api/users${filter ? `?role=${filter}` : ""}`),
        api<Student[]>("/api/students"),
      ]);
      setUsers(u);
      setStudents(s);
    } catch (e) {
      setNotice({
        kind: "err",
        text: e instanceof ApiError && e.status === 403
          ? "Only the school admin can manage users."
          : "Could not load users.",
      });
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  function toggleWard(id: string) {
    setForm((f) => ({
      ...f,
      ward_ids: f.ward_ids.includes(id)
        ? f.ward_ids.filter((w) => w !== id)
        : [...f.ward_ids, id],
    }));
  }

  async function createUser() {
    if (!form.email.trim() || !form.first_name.trim() || !form.last_name.trim()) {
      setNotice({ kind: "err", text: "Email, first name and last name are required." });
      return;
    }
    setBusy("create"); setNotice(null); setReveal(null);
    try {
      const body: Record<string, unknown> = {
        email: form.email.trim(), role: form.role,
        first_name: form.first_name.trim(), last_name: form.last_name.trim(),
        phone: form.phone.trim() || null,
      };
      if (form.password.trim()) body.password = form.password.trim();
      if (form.role === "student" && form.student_id) body.student_id = form.student_id;
      if (form.role === "parent") body.ward_student_ids = form.ward_ids;

      const res = await api<{ user: UserRow; temporary_password: string | null }>(
        "/api/users", { method: "POST", body: JSON.stringify(body) });

      if (res.temporary_password) {
        setReveal({ email: res.user.email, temp: res.temporary_password });
      }
      setNotice({ kind: "ok", text: `${ROLE_LABEL[res.user.role]} account created for ${res.user.email}.` });
      setForm({ email: "", role: form.role, first_name: "", last_name: "",
                phone: "", password: "", student_id: "", ward_ids: [] });
      await load();
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not create the user." });
    } finally { setBusy(null); }
  }

  async function setStatus(u: UserRow) {
    setBusy(u.id); setNotice(null);
    try {
      await api(`/api/users/${u.id}/status`,
        { method: "PATCH", body: JSON.stringify({ is_active: !u.is_active }) });
      await load();
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not update status." });
    } finally { setBusy(null); }
  }

  async function resetPassword(u: UserRow) {
    setBusy(`r-${u.id}`); setNotice(null);
    try {
      const res = await api<{ temporary_password: string }>(
        `/api/users/${u.id}/reset-password`, { method: "POST" });
      setReveal({ email: u.email, temp: res.temporary_password });
    } catch {
      setNotice({ kind: "err", text: "Could not reset the password." });
    } finally { setBusy(null); }
  }

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">Users</h1>
        <p className="text-sm text-ink-soft mt-1">
          Create accounts for staff, parents and students. Temporary passwords are
          shown once — the person changes it under Account after first sign-in.
        </p>
      </header>

      {/* create form */}
      <section className="rounded-lg border border-line bg-card p-4 space-y-3 max-w-3xl">
        <p className="text-sm font-medium">New account</p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <label className="block">
            <span className="block text-xs text-ink-soft mb-1">Role</span>
            <select value={form.role}
                    onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
                    className="w-full rounded border border-line px-2 py-1.5 text-sm bg-white">
              {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="block text-xs text-ink-soft mb-1">First name</span>
            <input value={form.first_name}
                   onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                   className="w-full rounded border border-line px-2 py-1.5 text-sm" />
          </label>
          <label className="block">
            <span className="block text-xs text-ink-soft mb-1">Last name</span>
            <input value={form.last_name}
                   onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                   className="w-full rounded border border-line px-2 py-1.5 text-sm" />
          </label>
          <label className="block">
            <span className="block text-xs text-ink-soft mb-1">Email</span>
            <input type="email" value={form.email}
                   onChange={(e) => setForm({ ...form, email: e.target.value })}
                   className="w-full rounded border border-line px-2 py-1.5 text-sm" />
          </label>
          <label className="block">
            <span className="block text-xs text-ink-soft mb-1">Phone (for SMS)</span>
            <input value={form.phone} placeholder="+234…"
                   onChange={(e) => setForm({ ...form, phone: e.target.value })}
                   className="w-full rounded border border-line px-2 py-1.5 text-sm" />
          </label>
          <label className="block">
            <span className="block text-xs text-ink-soft mb-1">
              Password <span className="text-ink-soft">(leave blank to auto-generate)</span>
            </span>
            <input value={form.password}
                   onChange={(e) => setForm({ ...form, password: e.target.value })}
                   className="w-full rounded border border-line px-2 py-1.5 text-sm" />
          </label>
        </div>

        {form.role === "student" && (
          <label className="block max-w-sm">
            <span className="block text-xs text-ink-soft mb-1">Link to student record</span>
            <select value={form.student_id}
                    onChange={(e) => setForm({ ...form, student_id: e.target.value })}
                    className="w-full rounded border border-line px-2 py-1.5 text-sm bg-white">
              <option value="">Select student…</option>
              {students.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.admission_number} — {s.first_name} {s.last_name}
                </option>
              ))}
            </select>
          </label>
        )}

        {form.role === "parent" && (
          <div>
            <span className="block text-xs text-ink-soft mb-1">Wards (tap to select)</span>
            <div className="flex flex-wrap gap-1.5">
              {students.map((s) => {
                const on = form.ward_ids.includes(s.id);
                return (
                  <button key={s.id} type="button" onClick={() => toggleWard(s.id)}
                          className={`rounded-full border px-3 py-1 text-xs ${
                            on ? "bg-ink text-white border-ink"
                               : "border-line bg-white text-ink-soft hover:border-ink"}`}>
                    {s.first_name} {s.last_name}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="flex items-center gap-3">
          <button onClick={createUser} disabled={busy !== null}
                  className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
            {busy === "create" ? "Creating…" : "Create account"}
          </button>
          {notice && (
            <span role="status"
                  className={`text-sm ${notice.kind === "ok" ? "text-ledger" : "text-sanction"}`}>
              {notice.text}
            </span>
          )}
        </div>

        {reveal && (
          <div className="rounded-md border border-brass bg-brass/10 p-3 text-sm">
            Temporary password for <b>{reveal.email}</b>:{" "}
            <code className="tabular font-semibold">{reveal.temp}</code>
            <span className="block text-xs text-ink-soft mt-1">
              Copy it now and share it securely — it will not be shown again.
            </span>
          </div>
        )}
      </section>

      {/* list */}
      <div className="flex flex-wrap gap-1.5">
        <button onClick={() => setFilter("")}
                className={`rounded-full border px-3 py-1 text-xs ${!filter ? "bg-ink text-white border-ink" : "border-line bg-white text-ink-soft"}`}>
          All
        </button>
        {ROLES.map((r) => (
          <button key={r.value} onClick={() => setFilter(r.value)}
                  className={`rounded-full border px-3 py-1 text-xs ${filter === r.value ? "bg-ink text-white border-ink" : "border-line bg-white text-ink-soft"}`}>
            {r.label}s
          </button>
        ))}
      </div>

      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="bg-ink text-white text-left">
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Email</th>
              <th className="px-3 py-2 font-medium">Role</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u, i) => (
              <tr key={u.id} className={i % 2 ? "bg-paper" : "bg-card"}>
                <td className="px-3 py-2 whitespace-nowrap">{u.first_name} {u.last_name}</td>
                <td className="px-3 py-2">{u.email}</td>
                <td className="px-3 py-2">{ROLE_LABEL[u.role] ?? u.role}</td>
                <td className="px-3 py-2">
                  <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                    u.is_active ? "bg-ledger/10 text-ledger" : "bg-sanction/10 text-sanction"}`}>
                    {u.is_active ? "Active" : "Deactivated"}
                  </span>
                </td>
                <td className="px-3 py-2 text-right whitespace-nowrap">
                  <button onClick={() => resetPassword(u)} disabled={busy !== null}
                          className="text-ink underline underline-offset-2 hover:text-ink-soft disabled:opacity-50 mr-3">
                    {busy === `r-${u.id}` ? "Resetting…" : "Reset password"}
                  </button>
                  <button onClick={() => setStatus(u)} disabled={busy !== null}
                          className="text-ink underline underline-offset-2 hover:text-ink-soft disabled:opacity-50">
                    {busy === u.id ? "Saving…" : u.is_active ? "Deactivate" : "Reactivate"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
