"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

type Role = "school_admin" | "bursar" | "teacher" | "parent" | "student";
type UserRow = {
  id: string; email: string; role: Role; first_name: string; last_name: string;
  phone: string | null; phone_verified: boolean; email_verified: boolean;
  is_active: boolean;
};
type Student = { id: string; admission_number: string; first_name: string; last_name: string };
type Arm = { id: string; label: string };
type Subject = { id: string; name: string };
type Assignment = {
  id: string; teacher_id: string; teacher_name: string;
  subject_id: string; subject_name: string; arm_id: string; class_label: string;
};
type Ward = {
  student_id: string; name: string; admission_number: string;
  class_label: string; relationship: string | null;
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
  const [wardsFor, setWardsFor] = useState<UserRow | null>(null);
  const [editing, setEditing] = useState<UserRow | null>(null);
  const [editForm, setEditForm] = useState({ first_name: "", last_name: "", email: "", phone: "" });
  const [wardList, setWardList] = useState<Ward[] | null>(null);
  const [addWardId, setAddWardId] = useState("");
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

  async function addAssignment(allowCoTeacher = false) {
    if (!asg.teacher_id || !asg.subject_id || !asg.arm_id) {
      setNotice({ kind: "err", text: "Pick a teacher, a subject and a class." });
      return;
    }
    setBusy("assign"); setNotice(null);
    try {
      await api("/api/users/assignments", {
        method: "POST",
        body: JSON.stringify({ ...asg, allow_co_teacher: allowCoTeacher }),
      });
      setNotice({
        kind: "ok",
        text: allowCoTeacher
          ? "Added as a co-teacher. Both teachers can now enter those scores."
          : "Assigned. Only this teacher can enter those scores.",
      });
      setAsg({ teacher_id: "", subject_id: "", arm_id: "" });
      await load();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Could not assign the teacher.";
      // the subject is already owned: make the admin choose deliberately
      if (e instanceof ApiError && e.status === 409 && msg.includes("already assigned to")) {
        if (confirm(`${msg}\n\nAdd as a co-teacher anyway? Both will be able to enter and change these marks.`)) {
          setBusy(null);
          await addAssignment(true);
          return;
        }
        setNotice({ kind: "err", text: msg });
      } else {
        setNotice({ kind: "err", text: msg });
      }
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

  async function openWards(u: UserRow) {
    setWardsFor(u);
    setWardList(null);
    setAddWardId("");
    setNotice(null);
    try {
      setWardList(await api<Ward[]>(`/api/users/${u.id}/wards`));
    } catch {
      setNotice({ kind: "err", text: "Could not load this parent's children." });
    }
  }

  async function linkWard() {
    if (!wardsFor || !addWardId) return;
    setBusy("link"); setNotice(null);
    try {
      await api(`/api/users/${wardsFor.id}/wards`, {
        method: "POST",
        body: JSON.stringify({ student_id: addWardId }),
      });
      const child = students.find((s) => s.id === addWardId);
      setNotice({
        kind: "ok",
        text: `${child ? `${child.first_name} ${child.last_name}` : "The child"} is now linked to ${wardsFor.first_name} ${wardsFor.last_name}. They will see this child on their next sign-in.`,
      });
      setAddWardId("");
      setWardList(await api<Ward[]>(`/api/users/${wardsFor.id}/wards`));
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not link the child." });
    } finally { setBusy(null); }
  }

  async function unlinkWard(w: Ward) {
    if (!wardsFor) return;
    if (!confirm(`Unlink ${w.name} from ${wardsFor.first_name} ${wardsFor.last_name}? They will no longer see this child's results, fees or timetable. The student's records are not deleted.`)) return;
    setBusy(`u-${w.student_id}`); setNotice(null);
    try {
      await api(`/api/users/${wardsFor.id}/wards/${w.student_id}`, { method: "DELETE" });
      setWardList(await api<Ward[]>(`/api/users/${wardsFor.id}/wards`));
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not unlink the child." });
    } finally { setBusy(null); }
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

  function openEdit(u: UserRow) {
    setEditing(u);
    setEditForm({ first_name: u.first_name, last_name: u.last_name,
                  email: u.email, phone: u.phone ?? "" });
    setWardsFor(null);
    setNotice(null);
  }

  async function saveEdit() {
    if (!editing) return;
    setBusy("edit"); setNotice(null);
    try {
      const r = await api<{ updated: boolean; changed?: string[] }>(`/api/users/${editing.id}`, {
        method: "PATCH", body: JSON.stringify(editForm),
      });
      setNotice({
        kind: "ok",
        text: r.updated
          ? `Saved. Changed: ${r.changed?.join(", ")}. A changed email or phone must be verified again.`
          : "Nothing changed.",
      });
      setEditing(null);
      await load();
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not save the changes." });
    } finally { setBusy(null); }
  }

  async function offboard(u: UserRow) {
    const consequences: Record<string, string> = {
      teacher: "Their sign-in stops immediately and their subject assignments end so the sheets can be reassigned. Marks they entered remain, with their name on the audit trail.",
      parent: "Their sign-in stops immediately and their links to children are removed. The students themselves are untouched.",
      bursar: "Their sign-in stops immediately. Payments they recorded remain on the record under their name.",
      school_admin: "Their sign-in stops immediately. The school must always keep at least one active admin.",
      student: "Their sign-in stops immediately. Their academic records are untouched.",
    };
    if (!confirm(
      `Offboard ${u.first_name} ${u.last_name} (${ROLE_LABEL[u.role] ?? u.role})?

` +
      `${consequences[u.role] ?? "Their sign-in stops immediately."}

` +
      `Their email is released so a future account can reuse it. This is for someone who has LEFT the school — for a temporary block, use Deactivate instead.`
    )) return;
    setBusy(`o-${u.id}`); setNotice(null);
    try {
      const r = await api<{ note: string }>(`/api/users/${u.id}`, { method: "DELETE" });
      setNotice({ kind: "ok", text: `${u.first_name} ${u.last_name} has been offboarded. ${r.note}` });
      await load();
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not offboard this account." });
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
            {assignments.map((a) => {
              const shared = assignments.filter(
                (x) => x.subject_id === a.subject_id && x.arm_id === a.arm_id).length > 1;
              return (
              <span key={a.id}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs ${
                      shared ? "border-brass bg-brass/15" : "border-line bg-paper"}`}>
                <b>{a.teacher_name}</b> · {a.subject_name} · {a.class_label}
                {shared && <span className="text-ink-soft">(co-taught)</span>}
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
              );
            })}
          </div>
        )}

        {asg.subject_id && asg.arm_id && (() => {
          const owners = assignments.filter(
            (a) => a.subject_id === asg.subject_id && a.arm_id === asg.arm_id);
          if (owners.length === 0) return null;
          return (
            <p className="text-xs text-sanction bg-sanction/5 border border-sanction/30 rounded px-2 py-1.5">
              Already assigned to {owners.map((o) => o.teacher_name).join(" and ")}.
              Assigning another teacher will ask you to confirm co-teaching.
            </p>
          );
        })()}

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
          <button onClick={() => addAssignment(false)} disabled={busy !== null}
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

      {/* correct a mistake in an account */}
      {editing && (
        <section className="rounded-lg border border-brass bg-brass/10 p-4 space-y-3 max-w-3xl">
          <div className="flex items-baseline justify-between gap-2">
            <p className="text-sm font-medium">
              Edit {editing.first_name} {editing.last_name}
              <span className="ml-2 font-normal text-xs text-ink-soft">{ROLE_LABEL[editing.role] ?? editing.role}</span>
            </p>
            <button onClick={() => setEditing(null)}
                    className="text-xs text-ink-soft underline underline-offset-2">Close</button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <input value={editForm.first_name} placeholder="First name"
                   onChange={(e) => setEditForm({ ...editForm, first_name: e.target.value })}
                   className="rounded border border-line px-2 py-1.5 text-sm" />
            <input value={editForm.last_name} placeholder="Last name"
                   onChange={(e) => setEditForm({ ...editForm, last_name: e.target.value })}
                   className="rounded border border-line px-2 py-1.5 text-sm" />
            <input value={editForm.email} placeholder="Email" type="email"
                   onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                   className="rounded border border-line px-2 py-1.5 text-sm" />
            <input value={editForm.phone} placeholder="Phone (e.g. 0803…)" inputMode="tel"
                   onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                   className="rounded border border-line px-2 py-1.5 text-sm" />
          </div>
          <p className="text-xs text-ink-soft">
            The role cannot be changed here — a wrong-role account should be offboarded
            and recreated correctly. Changing the email or phone clears its verified tick
            until it is verified again.
          </p>
          <button onClick={saveEdit} disabled={busy !== null}
                  className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
            {busy === "edit" ? "Saving…" : "Save changes"}
          </button>
        </section>
      )}

      {/* ward management: reconcile an existing parent with their children */}
      {wardsFor && (
        <section className="rounded-lg border border-brass bg-brass/10 p-4 space-y-3 max-w-3xl">
          <div className="flex items-baseline justify-between gap-2">
            <p className="text-sm font-medium">
              Children linked to {wardsFor.first_name} {wardsFor.last_name}
              <span className="ml-2 font-normal text-xs text-ink-soft">{wardsFor.email}</span>
            </p>
            <button onClick={() => { setWardsFor(null); setWardList(null); }}
                    className="text-xs text-ink-soft underline underline-offset-2">
              Close
            </button>
          </div>

          {wardList === null && <p className="text-sm text-ink-soft">Loading…</p>}

          {wardList && wardList.length === 0 && (
            <p className="text-sm text-sanction">
              No children linked yet — this parent currently sees nothing.
            </p>
          )}

          {wardList && wardList.length > 0 && (
            <ul className="space-y-1">
              {wardList.map((w) => (
                <li key={w.student_id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded border border-line bg-white px-3 py-1.5 text-sm">
                  <span>
                    <span className="tabular text-ink-soft mr-2">{w.admission_number}</span>
                    {w.name}
                    <span className="ml-2 text-xs text-ink-soft">{w.class_label}</span>
                  </span>
                  <button onClick={() => unlinkWard(w)} disabled={busy !== null}
                          className="text-xs text-ink-soft underline underline-offset-2 hover:text-sanction disabled:opacity-40">
                    {busy === `u-${w.student_id}` ? "Removing…" : "Unlink"}
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="flex flex-wrap items-end gap-2 pt-1">
            <label className="block">
              <span className="block text-xs text-ink-soft mb-1">
                Link another child (e.g. a sibling admitted later)
              </span>
              <select value={addWardId} onChange={(e) => setAddWardId(e.target.value)}
                      className="rounded border border-line px-2 py-1.5 text-sm bg-white min-w-64">
                <option value="">Select student…</option>
                {students
                  .filter((s) => !(wardList ?? []).some((w) => w.student_id === s.id))
                  .map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.admission_number} — {s.first_name} {s.last_name}
                    </option>
                  ))}
              </select>
            </label>
            <button onClick={linkWard} disabled={busy !== null || !addWardId}
                    className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
              {busy === "link" ? "Linking…" : "Link child"}
            </button>
          </div>
        </section>
      )}

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
                <td className="px-3 py-2 whitespace-nowrap">
                  {u.first_name} {u.last_name}
                  {u.role === "parent" && u.phone && (
                    <span
                      title={u.phone_verified
                        ? "Phone number verified — SMS reaches this parent"
                        : "Phone number not yet verified"}
                      className={`ml-2 inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                        u.phone_verified
                          ? "bg-ledger/10 text-ledger"
                          : "bg-paper text-ink-soft border border-line"}`}>
                      {u.phone_verified ? "✓ phone" : "unverified"}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2">{u.email}</td>
                <td className="px-3 py-2">{ROLE_LABEL[u.role] ?? u.role}</td>
                <td className="px-3 py-2">
                  <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                    u.is_active ? "bg-ledger/10 text-ledger" : "bg-sanction/10 text-sanction"}`}>
                    {u.is_active ? "Active" : "Deactivated"}
                  </span>
                </td>
                <td className="px-3 py-2 text-right">
                  <div className="flex flex-wrap justify-end gap-x-3 gap-y-1">
                    <button onClick={() => openEdit(u)} disabled={busy !== null}
                            className="text-ink underline underline-offset-2 hover:text-ink-soft disabled:opacity-50">
                      Edit
                    </button>
                    {u.role === "parent" && (
                      <button onClick={() => openWards(u)} disabled={busy !== null}
                              className="text-ink underline underline-offset-2 hover:text-ink-soft disabled:opacity-50">
                        Children
                      </button>
                    )}
                    <button onClick={() => resetPassword(u)} disabled={busy !== null}
                            className="text-ink underline underline-offset-2 hover:text-ink-soft disabled:opacity-50">
                      {busy === `r-${u.id}` ? "Resetting…" : "Reset password"}
                    </button>
                    <button onClick={() => setStatus(u)} disabled={busy !== null}
                            className="text-ink underline underline-offset-2 hover:text-ink-soft disabled:opacity-50">
                      {busy === u.id ? "Saving…" : u.is_active ? "Deactivate" : "Reactivate"}
                    </button>
                    <button onClick={() => offboard(u)} disabled={busy !== null}
                            className="text-sanction underline underline-offset-2 hover:opacity-70 disabled:opacity-50">
                      {busy === `o-${u.id}` ? "Offboarding…" : "Offboard"}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
