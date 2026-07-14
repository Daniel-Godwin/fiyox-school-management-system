"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

type Role = "school_admin" | "bursar" | "teacher" | "parent" | "student";
type UserRow = {
  id: string; email: string; role: Role; first_name: string; last_name: string;
  phone: string | null; is_active: boolean;
};
type Student = { id: string; admission_number: string; first_name: string; last_name: string };
type Arm = { id: string; label: string };
type Subject = { id: string; name: string };
type Assignment = {
  id: string; teacher_id: string; teacher_name: string;
  subject_id: string; subject_name: string; arm_id: string; class_label: string;
};

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
  const [arms, setArms] = useState<Arm[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [asg, setAsg] = useState({ teacher_id: "", subject_id: "", arm_id: "" });
  const [reveal, setReveal] = useState<{ email: string; temp: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const [u, s, a, subj, asgs] = await Promise.all([
        api<UserRow[]>(`/api/users${filter ? `?role=${filter}` : ""}`),
        api<Student[]>("/api/students"),
        api<Arm[]>("/api/academics/arms"),
        api<Subject[]>("/api/academics/subjects"),
        api<Assignment[]>("/api/users/assignments"),
      ]);
      setUsers(u);
      setStudents(s);
      setArms(a);
      setSubjects(subj);
      setAssignments(asgs);
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

  async function addAssignment() {
    if (!asg.teacher_id || !asg.subject_id || !asg.arm_id) {
      setNotice({ kind: "err", text: "Pick a teacher, a subject and a class." });
      return;
    }
    setBusy("assign"); setNotice(null);
    try {
      await api("/api/users/assignments", {
        method: "POST", body: JSON.stringify(asg),
      });
      setNotice({ kind: "ok", text: "Assigned. Only this teacher can now enter those scores." });
      setAsg({ teacher_id: "", subject_id: "", arm_id: "" });
      await load();
    } catch (e) {
      setNotice({
        kind: "err",
        text: e instanceof ApiError ? e.message : "Could not assign the teacher.",
      });
    } finally { setBusy(null); }
  }

  async function removeAssignment(id: string, who: string) {
    setBusy(`a-${id}`); setNotice(null);
    try {
      await api(`/api/users/assignments/${id}`, { method: "DELETE" });
      setNotice({ kind: "ok", text: `${who} can no longer enter those scores.` });
      await load();
    } catch { setNotice({ kind: "err", text: "Could not remove the assignment." }); }
    finally { setBusy(null); }
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

      {/* teaching assignments */}
      <section className="rounded-lg border border-line bg-card p-4 space-y-3 max-w-3xl">
        <div>
          <p className="text-sm font-medium">Teaching assignments</p>
          <p className="text-xs text-ink-soft">
            A teacher can only enter or view scores for the subjects and classes
            assigned here — nobody can alter another teacher&apos;s marks. Admins
            are not restricted and can correct any sheet.
          </p>
        </div>

        {assignments.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {assignments.map((a) => (
              <span key={a.id}
                    className="inline-flex items-center gap-1.5 rounded-full border border-line bg-paper px-3 py-1 text-xs">
                <b>{a.teacher_name}</b> · {a.subject_name} · {a.class_label}
                <button
                  onClick={() => {
                    if (confirm(`Remove ${a.teacher_name} from ${a.subject_name} (${a.class_label})?`))
                      removeAssignment(a.id, a.teacher_name);
                  }}
                  disabled={busy !== null}
                  aria-label="Remove assignment"
                  className="text-ink-soft hover:text-sanction disabled:opacity-40"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-4 gap-2">
          <select value={asg.teacher_id}
                  onChange={(e) => setAsg({ ...asg, teacher_id: e.target.value })}
                  className="rounded border border-line px-2 py-1.5 text-sm bg-white">
            <option value="">Teacher…</option>
            {users.filter((u) => u.role === "teacher" && u.is_active).map((u) => (
              <option key={u.id} value={u.id}>{u.first_name} {u.last_name}</option>
            ))}
          </select>
          <select value={asg.subject_id}
                  onChange={(e) => setAsg({ ...asg, subject_id: e.target.value })}
                  className="rounded border border-line px-2 py-1.5 text-sm bg-white">
            <option value="">Subject…</option>
            {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <select value={asg.arm_id}
                  onChange={(e) => setAsg({ ...asg, arm_id: e.target.value })}
                  className="rounded border border-line px-2 py-1.5 text-sm bg-white">
            <option value="">Class…</option>
            {arms.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
          </select>
          <button onClick={addAssignment} disabled={busy !== null}
                  className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
            {busy === "assign" ? "Assigning…" : "Assign"}
          </button>
        </div>
        {users.filter((u) => u.role === "teacher").length === 0 && (
          <p className="text-xs text-ink-soft">
            Create a teacher account above first, then assign their subjects here.
          </p>
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
