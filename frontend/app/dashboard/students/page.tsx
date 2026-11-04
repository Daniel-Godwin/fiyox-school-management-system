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
type RenumRow = { student_id: string; name: string; old: string; new: string; conflict: boolean };

export default function StudentsPage() {
  const [students, setStudents] = useState<Student[] | null>(null);
  const [arms, setArms] = useState<Arm[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");

  // renumber a class (admin only)
  const [role, setRole] = useState("");
  const [schoolPrefix, setSchoolPrefix] = useState("");
  const [rOpen, setROpen] = useState(false);
  const [rForm, setRForm] = useState({ arm_id: "", prefix: "", year: "", start: "1" });
  const [rPreview, setRPreview] = useState<RenumRow[] | null>(null);
  const [rBusy, setRBusy] = useState(false);
  const isAdmin = role === "school_admin" || role === "super_admin";

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
  useEffect(() => {
    api<{ role: string }>("/api/auth/me").then((m) => setRole(m.role)).catch(() => {});
    api<{ admission_prefix: string | null }>("/api/schools/me")
      .then((s) => setSchoolPrefix(s.admission_prefix ?? "")).catch(() => {});
  }, []);

  async function renumber(apply: boolean) {
    if (!rForm.arm_id || !rForm.year.trim()) {
      setNotice({ kind: "err", text: "Choose a class and a year." }); return;
    }
    setRBusy(true); setNotice(null);
    try {
      const res = await api<{ preview: RenumRow[]; count: number; conflicts: number; applied: boolean }>(
        "/api/students/renumber", { method: "POST", body: JSON.stringify({
          arm_id: rForm.arm_id, year: rForm.year.trim(),
          prefix: rForm.prefix.trim() || null, start: Number(rForm.start) || 1, apply }) });
      if (res.applied) {
        setNotice({ kind: "ok", text: `Renumbered ${res.count} student(s).` });
        setRPreview(null); setRForm({ arm_id: "", prefix: "", year: "", start: "1" }); load();
      } else {
        setRPreview(res.preview);
        if (res.conflicts) setNotice({ kind: "err",
          text: `${res.conflicts} new number(s) clash with students in other classes — change the year or start number.` });
      }
    } catch (e) { setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not renumber." }); }
    finally { setRBusy(false); }
  }

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

      {/* ---- Renumber a class (admin only) ---- */}
      {isAdmin && (
        <section className="mt-3 rounded-lg border border-line bg-card">
          <button onClick={() => setROpen(!rOpen)}
                  className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium">
            <span>Renumber a class</span>
            <span aria-hidden className="text-ink-soft">{rOpen ? "▴" : "▾"}</span>
          </button>
          {rOpen && (
            <div className="border-t border-line px-4 py-4 space-y-3">
              <p className="text-xs text-ink-soft">
                Re-sequence a whole class&apos;s admission numbers into your school&apos;s format. Set the year to the
                students&apos; intake year (e.g. 25), preview the changes, then apply. Nothing changes until you apply.
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <label className="block col-span-2 sm:col-span-1">
                  <span className="block text-xs text-ink-soft mb-1">Class</span>
                  <select value={rForm.arm_id} onChange={(e) => { setRForm({ ...rForm, arm_id: e.target.value }); setRPreview(null); }}
                          className="w-full rounded border border-line px-2 py-1.5 text-sm bg-white">
                    <option value="">Select class…</option>
                    {arms.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
                  </select>
                </label>
                <label className="block">
                  <span className="block text-xs text-ink-soft mb-1">Prefix</span>
                  <input value={rForm.prefix} onChange={(e) => { setRForm({ ...rForm, prefix: e.target.value.toUpperCase() }); setRPreview(null); }}
                         placeholder={schoolPrefix || "FAD"} maxLength={12}
                         className="w-full rounded border border-line px-2 py-1.5 text-sm" />
                </label>
                <label className="block">
                  <span className="block text-xs text-ink-soft mb-1">Year</span>
                  <input value={rForm.year} onChange={(e) => { setRForm({ ...rForm, year: e.target.value }); setRPreview(null); }}
                         placeholder="25" maxLength={4}
                         className="w-full rounded border border-line px-2 py-1.5 text-sm" />
                </label>
                <label className="block">
                  <span className="block text-xs text-ink-soft mb-1">Start at</span>
                  <input type="number" min={1} value={rForm.start} onChange={(e) => { setRForm({ ...rForm, start: e.target.value }); setRPreview(null); }}
                         className="w-full rounded border border-line px-2 py-1.5 text-sm" />
                </label>
              </div>
              <div className="flex items-center gap-3">
                <button onClick={() => renumber(false)} disabled={rBusy}
                        className="rounded-md border border-ink text-ink px-4 py-2 text-sm font-medium hover:bg-ink hover:text-white disabled:opacity-50">
                  {rBusy ? "Working…" : "Preview"}
                </button>
                {notice && (
                  <span role="status" className={`text-sm ${notice.kind === "ok" ? "text-ledger" : "text-sanction"}`}>{notice.text}</span>
                )}
              </div>

              {rPreview && rPreview.length > 0 && (() => {
                const conflicts = rPreview.filter((r) => r.conflict).length;
                return (
                  <div className="space-y-3">
                    <ul className="rounded-lg border border-line divide-y divide-line overflow-hidden">
                      {rPreview.map((r) => (
                        <li key={r.student_id} className={`px-3 py-2 ${r.conflict ? "bg-sanction/10" : ""}`}>
                          <p className="font-medium truncate">{r.name}</p>
                          <p className="text-sm tabular text-ink-soft">
                            {r.old} <span className="text-ink">→</span> <span className="font-semibold text-ink">{r.new}</span>
                            {r.conflict && <span className="text-sanction"> · clashes with another class</span>}
                          </p>
                        </li>
                      ))}
                    </ul>
                    <button onClick={() => renumber(true)} disabled={rBusy || conflicts > 0}
                            className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
                      {rBusy ? "Applying…" : `Apply to ${rPreview.length} student${rPreview.length === 1 ? "" : "s"}`}
                    </button>
                    {conflicts > 0 && <span className="ml-3 text-sm text-sanction">Resolve the clashes before applying.</span>}
                  </div>
                );
              })()}
            </div>
          )}
        </section>
      )}

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

        {/* ---- phones: one tappable card per student (no sideways scroll) ---- */}
        <ul className="md:hidden mt-6 space-y-2">
          {shown.map((s) => {
            const on = selected.includes(s.id);
            return (
              <li
                key={s.id}
                className={`flex items-center gap-3 rounded-xl border bg-card p-3 ${
                  on ? "border-brass bg-brass/5" : "border-line"
                }`}
              >
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() => toggleSelect(s.id)}
                  aria-label={`Select ${s.first_name} ${s.last_name}`}
                  className="h-5 w-5 shrink-0"
                />
                <div className="min-w-0 flex-1">
                  <p className="font-medium truncate">{s.first_name} {s.last_name}</p>
                  <p className="text-xs text-ink-soft mt-0.5">
                    <span className="tabular">{s.admission_number}</span>
                    <span className="capitalize"> · {s.gender}</span>
                  </p>
                </div>
                <span
                  className={`shrink-0 inline-block rounded-full px-2 py-0.5 text-xs ${
                    s.is_active ? "bg-ledger/10 text-ledger" : "bg-sanction/10 text-sanction"
                  }`}
                >
                  {s.is_active ? "Active" : "Inactive"}
                </span>
              </li>
            );
          })}
          {shown.length === 0 && (
            <li className="rounded-xl border border-dashed border-line bg-card px-4 py-8 text-center text-ink-soft text-sm">
              {q ? "No student matches that search." : "No students yet. Import a class list to begin."}
            </li>
          )}
        </ul>

        {/* ---- tablet / desktop: the full register table ---- */}
        <div className="hidden md:block mt-6 bg-card border border-line rounded-xl overflow-hidden overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
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
