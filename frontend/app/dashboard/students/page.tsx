"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

type Student = {
  id: string;
  admission_number: string;
  first_name: string;
  last_name: string;
  gender: "male" | "female";
  is_active: boolean;
};

type Arm = { id: string; label: string };

export default function StudentsPage() {
  const [students, setStudents] = useState<Student[] | null>(null);
  const [arms, setArms] = useState<Arm[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");

  // admit form
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    admission_number: "", first_name: "", last_name: "",
    gender: "male", arm_id: "",
  });
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  // transfer between arms
  const [selected, setSelected] = useState<string[]>([]);
  const [toArm, setToArm] = useState("");

  const load = useCallback(() => {
    api<Student[]>("/api/students")
      .then(setStudents)
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Could not load students"),
      );
    api<Arm[]>("/api/academics/arms").then(setArms).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  function toggleSelect(id: string) {
    setSelected((p) => p.includes(id) ? p.filter((x) => x !== id) : [...p, id]);
  }

  async function transfer() {
    if (selected.length === 0 || !toArm) {
      setNotice({ kind: "err", text: "Select students and choose the class to move them to." });
      return;
    }
    setSaving(true); setNotice(null);
    try {
      const res = await api<{ moved: number }>("/api/academics/students/transfer", {
        method: "POST",
        body: JSON.stringify({ student_ids: selected, to_arm_id: toArm }),
      });
      const label = arms.find((a) => a.id === toArm)?.label ?? "the new class";
      setNotice({ kind: "ok", text: `${res.moved} student(s) moved to ${label}.` });
      setSelected([]); setToArm("");
      load();
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Transfer failed." });
    } finally { setSaving(false); }
  }

  async function admit() {
    if (!form.admission_number.trim() || !form.first_name.trim() ||
        !form.last_name.trim() || !form.arm_id) {
      setNotice({ kind: "err", text: "Admission number, names and class are all required." });
      return;
    }
    setSaving(true); setNotice(null);
    try {
      await api("/api/students", {
        method: "POST",
        body: JSON.stringify({
          admission_number: form.admission_number.trim(),
          first_name: form.first_name.trim(),
          last_name: form.last_name.trim(),
          gender: form.gender,
          current_arm_id: form.arm_id,
        }),
      });
      setNotice({ kind: "ok", text: `${form.first_name} ${form.last_name} admitted.` });
      setForm({ admission_number: "", first_name: "", last_name: "",
                gender: form.gender, arm_id: form.arm_id });
      load();
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not admit the student." });
    } finally { setSaving(false); }
  }

  const shown = (students ?? []).filter((s) =>
    `${s.admission_number} ${s.first_name} ${s.last_name}`
      .toLowerCase()
      .includes(q.toLowerCase()),
  );

  return (
    <div className="max-w-4xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Students</h1>
          <p className="text-ink-soft text-sm mt-1">
            The school register — {students ? `${students.length} enrolled` : "loading"}.
          </p>
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search name or admission no."
          className="rounded-md border border-line bg-white px-3 py-2 text-sm w-64"
        />
      </div>

      {/* ---- Admit a student ---- */}
      <section className="mt-5 rounded-lg border border-line bg-card">
        <button onClick={() => setOpen(!open)}
                className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium">
          <span>Admit a student</span>
          <span aria-hidden className="text-ink-soft">{open ? "▴" : "▾"}</span>
        </button>
        {open && (
          <div className="border-t border-line px-4 py-4 space-y-3">
            {arms.length === 0 ? (
              <p className="text-sm text-sanction">
                No classes exist yet — set up the school first (School setup in the sidebar).
              </p>
            ) : (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <label className="block">
                    <span className="block text-xs text-ink-soft mb-1">Admission number</span>
                    <input value={form.admission_number} placeholder="FDC/26/001"
                           onChange={(e) => setForm({ ...form, admission_number: e.target.value })}
                           className="w-full rounded border border-line px-2 py-1.5 text-sm" />
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
                    <span className="block text-xs text-ink-soft mb-1">Gender</span>
                    <select value={form.gender}
                            onChange={(e) => setForm({ ...form, gender: e.target.value })}
                            className="w-full rounded border border-line px-2 py-1.5 text-sm bg-white">
                      <option value="male">Male</option>
                      <option value="female">Female</option>
                    </select>
                  </label>
                  <label className="block">
                    <span className="block text-xs text-ink-soft mb-1">Class</span>
                    <select value={form.arm_id}
                            onChange={(e) => setForm({ ...form, arm_id: e.target.value })}
                            className="w-full rounded border border-line px-2 py-1.5 text-sm bg-white">
                      <option value="">Select class…</option>
                      {arms.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
                    </select>
                  </label>
                </div>
                <div className="flex items-center gap-3">
                  <button onClick={admit} disabled={saving}
                          className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
                    {saving ? "Admitting…" : "Admit student"}
                  </button>
                  {notice && (
                    <span role="status"
                          className={`text-sm ${notice.kind === "ok" ? "text-ledger" : "text-sanction"}`}>
                      {notice.text}
                    </span>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </section>

      {error && (
        <p role="alert" className="mt-6 text-sanction text-sm">
          {error}
        </p>
      )}

      {students && (
        <>
        {selected.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-brass bg-brass/10 p-3">
            <span className="text-sm font-medium">
              {selected.length} student{selected.length === 1 ? "" : "s"} selected
            </span>
            <label className="flex items-center gap-2">
              <span className="text-xs text-ink-soft">Move to</span>
              <select value={toArm} onChange={(e) => setToArm(e.target.value)}
                      className="rounded border border-line px-2 py-1.5 text-sm bg-white">
                <option value="">Select class…</option>
                {arms.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
              </select>
            </label>
            <button onClick={transfer} disabled={saving || !toArm}
                    className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
              {saving ? "Moving…" : "Move students"}
            </button>
            <button onClick={() => setSelected([])} disabled={saving}
                    className="text-sm text-ink-soft underline underline-offset-2">
              Clear
            </button>
          </div>
        )}

        <div className="mt-6 bg-card border border-line rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-ink text-white text-left">
                <th className="px-3 py-2.5 font-medium w-8"><span className="sr-only">Select</span></th>
                <th className="px-4 py-2.5 font-medium">Admission No.</th>
                <th className="px-4 py-2.5 font-medium">Name</th>
                <th className="px-4 py-2.5 font-medium">Gender</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((s, i) => (
                <tr key={s.id} className={i % 2 ? "bg-paper/60" : ""}>
                  <td className="px-3 py-2.5">
                    <input type="checkbox" checked={selected.includes(s.id)}
                           onChange={() => toggleSelect(s.id)}
                           aria-label={`Select ${s.first_name} ${s.last_name}`}
                           className="h-4 w-4" />
                  </td>
                  <td className="px-4 py-2.5 tabular">{s.admission_number}</td>
                  <td className="px-4 py-2.5">
                    {s.first_name} {s.last_name}
                  </td>
                  <td className="px-4 py-2.5 capitalize">{s.gender}</td>
                  <td className="px-4 py-2.5">
                    <span
                      className={`inline-block rounded-full px-2 py-0.5 text-xs ${
                        s.is_active
                          ? "bg-ledger/10 text-ledger"
                          : "bg-sanction/10 text-sanction"
                      }`}
                    >
                      {s.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                </tr>
              ))}
              {shown.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-ink-soft">
                    {q
                      ? "No student matches that search."
                      : "No students yet. Import a class list to begin."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        </>
      )}
    </div>
  );
}
