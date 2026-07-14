"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, me, User } from "@/lib/api";

type Period = {
  id: string; name: string; sequence: number;
  start_time: string | null; end_time: string | null; is_break: boolean;
};
type Lesson = {
  id: string; arm_id: string; arm_label: string; day: string; period_id: string;
  subject_id: string; subject_name: string;
  teacher_id: string | null; teacher_name: string | null; room: string | null;
};
type Ward = { student_id: string; name: string; arm_id: string };
type Grid = { wards: Ward[]; days: string[]; periods: Period[]; lessons: Lesson[] };
type Arm = { id: string; label: string };
type Subject = { id: string; name: string };
type Teacher = { id: string; first_name: string; last_name: string; role: string };

const DAY_LABEL: Record<string, string> = {
  monday: "Mon", tuesday: "Tue", wednesday: "Wed",
  thursday: "Thu", friday: "Fri", saturday: "Sat",
};

export default function TimetablePage() {
  const [user, setUser] = useState<User | null>(null);
  const [grid, setGrid] = useState<Grid | null>(null);
  const [arms, setArms] = useState<Arm[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [teachers, setTeachers] = useState<Teacher[]>([]);
  const [armId, setArmId] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const [newPeriod, setNewPeriod] = useState({
    name: "", sequence: "", start_time: "", end_time: "", is_break: false,
  });
  const [slot, setSlot] = useState<{ day: string; period_id: string } | null>(null);
  const [lessonForm, setLessonForm] = useState({ subject_id: "", teacher_id: "", room: "" });

  const isAdmin = user?.role === "school_admin" || user?.role === "super_admin";
  const isTeacher = user?.role === "teacher";
  const isFamily = user?.role === "parent" || user?.role === "student";
  const wards = grid?.wards ?? [];
  const multiWard = wards.length > 1;

  const load = useCallback(async () => {
    try {
      const q = armId ? `?arm_id=${armId}` : "";
      const g = await api<Grid>(`/api/timetable${q}`);
      setGrid(g);
    } catch {
      setNotice({ kind: "err", text: "Could not load the timetable." });
    }
  }, [armId]);

  useEffect(() => {
    Promise.all([me(), api<Arm[]>("/api/academics/arms")])
      .then(([u, a]) => {
        setUser(u);
        setArms(a);
        if ((u.role === "school_admin" || u.role === "super_admin") && a[0]) {
          setArmId(a[0].id);
        }
        if (u.role === "school_admin" || u.role === "super_admin") {
          api<Subject[]>("/api/academics/subjects").then(setSubjects).catch(() => {});
          api<Teacher[]>("/api/users?role=teacher").then(setTeachers).catch(() => {});
        }
      })
      .catch(() => setNotice({ kind: "err", text: "Could not load the page." }));
  }, []);

  useEffect(() => { load(); }, [load]);

  async function addPeriod() {
    if (!newPeriod.name.trim() || !newPeriod.sequence) {
      setNotice({ kind: "err", text: "A period needs a name and a row number." });
      return;
    }
    setBusy("period"); setNotice(null);
    try {
      await api("/api/timetable/periods", {
        method: "POST",
        body: JSON.stringify({
          name: newPeriod.name.trim(),
          sequence: Number(newPeriod.sequence),
          start_time: newPeriod.start_time || null,
          end_time: newPeriod.end_time || null,
          is_break: newPeriod.is_break,
        }),
      });
      setNewPeriod({ name: "", sequence: "", start_time: "", end_time: "", is_break: false });
      await load();
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not add the period." });
    } finally { setBusy(null); }
  }

  async function saveLesson() {
    if (!slot || !lessonForm.subject_id) {
      setNotice({ kind: "err", text: "Pick a subject." });
      return;
    }
    setBusy("lesson"); setNotice(null);
    try {
      await api("/api/timetable/lessons", {
        method: "POST",
        body: JSON.stringify({
          arm_id: armId, day: slot.day, period_id: slot.period_id,
          subject_id: lessonForm.subject_id,
          teacher_id: lessonForm.teacher_id || null,
          room: lessonForm.room.trim() || null,
        }),
      });
      setSlot(null);
      setLessonForm({ subject_id: "", teacher_id: "", room: "" });
      await load();
    } catch (e) {
      // the clash messages are the whole point — show them verbatim
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not schedule the lesson." });
    } finally { setBusy(null); }
  }

  async function removeLesson(id: string) {
    setBusy(id);
    try {
      await api(`/api/timetable/lessons/${id}`, { method: "DELETE" });
      await load();
    } catch { setNotice({ kind: "err", text: "Could not remove the lesson." }); }
    finally { setBusy(null); }
  }

  const cellAll = (day: string, periodId: string) =>
    (grid?.lessons ?? []).filter((l) => l.day === day && l.period_id === periodId);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">Timetable</h1>
        <p className="text-sm text-ink-soft mt-1">
          {isTeacher
            ? "Your lessons this week."
            : "The week's lesson grid. Fiyox refuses any clash — a class cannot be in two lessons at once, and a teacher cannot be in two classrooms at once."}
        </p>
      </header>

      {isFamily && multiWard && (
        <div className="flex flex-wrap items-center gap-1.5">
          <button onClick={() => setArmId("")}
                  className={`rounded-full border px-3 py-1 text-xs ${
                    !armId ? "bg-ink text-white border-ink"
                           : "border-line bg-white text-ink-soft hover:border-ink"}`}>
            All children
          </button>
          {wards.map((w) => (
            <button key={w.student_id} onClick={() => setArmId(w.arm_id)}
                    className={`rounded-full border px-3 py-1 text-xs ${
                      armId === w.arm_id ? "bg-ink text-white border-ink"
                                         : "border-line bg-white text-ink-soft hover:border-ink"}`}>
              {w.name}
            </button>
          ))}
        </div>
      )}

      {isFamily && wards.length === 1 && (
        <p className="text-xs text-ink-soft">
          {wards[0].name}&apos;s week.
        </p>
      )}

      {isFamily && wards.length === 0 && (
        <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-6 max-w-xl">
          No children are linked to your account yet. Ask the school to link them.
        </p>
      )}

      {isAdmin && (
        <div className="flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="block text-xs font-medium text-ink-soft mb-1">Class</span>
            <select value={armId} onChange={(e) => setArmId(e.target.value)}
                    className="rounded-md border border-line bg-white px-3 py-2 text-sm">
              {arms.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
            </select>
          </label>
          {notice && (
            <span role="status"
                  className={`text-sm ${notice.kind === "ok" ? "text-ledger" : "text-sanction"}`}>
              {notice.text}
            </span>
          )}
        </div>
      )}

      {!isAdmin && notice && (
        <p className={`text-sm ${notice.kind === "ok" ? "text-ledger" : "text-sanction"}`}>
          {notice.text}
        </p>
      )}

      {/* periods setup */}
      {isAdmin && (
        <section className="rounded-lg border border-line bg-card p-4 space-y-3">
          <p className="text-sm font-medium">Periods</p>
          {grid && grid.periods.length === 0 && (
            <p className="text-sm text-sanction">
              No periods yet — add them below (Period 1, Period 2, Break…). The grid
              needs rows before lessons can be placed.
            </p>
          )}
          <div className="flex flex-wrap items-end gap-2">
            <label className="block">
              <span className="block text-xs text-ink-soft mb-1">Name</span>
              <input value={newPeriod.name} placeholder="Period 1"
                     onChange={(e) => setNewPeriod({ ...newPeriod, name: e.target.value })}
                     className="w-28 rounded border border-line px-2 py-1.5 text-sm" />
            </label>
            <label className="block">
              <span className="block text-xs text-ink-soft mb-1">Row</span>
              <input value={newPeriod.sequence} inputMode="numeric" placeholder="1"
                     onChange={(e) => setNewPeriod({ ...newPeriod, sequence: e.target.value })}
                     className="w-14 rounded border border-line px-2 py-1.5 text-sm" />
            </label>
            <label className="block">
              <span className="block text-xs text-ink-soft mb-1">From</span>
              <input type="time" value={newPeriod.start_time}
                     onChange={(e) => setNewPeriod({ ...newPeriod, start_time: e.target.value })}
                     className="rounded border border-line px-2 py-1.5 text-sm" />
            </label>
            <label className="block">
              <span className="block text-xs text-ink-soft mb-1">To</span>
              <input type="time" value={newPeriod.end_time}
                     onChange={(e) => setNewPeriod({ ...newPeriod, end_time: e.target.value })}
                     className="rounded border border-line px-2 py-1.5 text-sm" />
            </label>
            <label className="flex items-center gap-1.5 pb-2 text-xs">
              <input type="checkbox" checked={newPeriod.is_break}
                     onChange={(e) => setNewPeriod({ ...newPeriod, is_break: e.target.checked })} />
              Break / assembly
            </label>
            <button onClick={addPeriod} disabled={busy !== null}
                    className="rounded-md border border-ink text-ink px-3 py-1.5 text-sm font-medium hover:bg-ink hover:text-white disabled:opacity-40">
              {busy === "period" ? "Adding…" : "Add period"}
            </button>
          </div>
        </section>
      )}

      {/* the grid */}
      {grid && grid.periods.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-line bg-card">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-ink text-white text-left">
                <th className="px-3 py-2 font-medium">Period</th>
                {grid.days.map((d) => (
                  <th key={d} className="px-3 py-2 font-medium">{DAY_LABEL[d] ?? d}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grid.periods.map((p, i) => (
                <tr key={p.id} className={p.is_break ? "bg-paper" : i % 2 ? "bg-paper/50" : ""}>
                  <td className="px-3 py-2 whitespace-nowrap align-top">
                    <div className="font-medium">{p.name}</div>
                    {p.start_time && (
                      <div className="text-xs text-ink-soft tabular">
                        {p.start_time}–{p.end_time}
                      </div>
                    )}
                  </td>
                  {grid.days.map((d) => {
                    if (p.is_break) {
                      return (
                        <td key={d} className="px-3 py-2 text-center text-xs text-ink-soft italic">
                          {p.name}
                        </td>
                      );
                    }
                    const here = cellAll(d, p.id);
                    return (
                      <td key={d} className="px-2 py-1.5 align-top">
                        {here.length > 0 ? (
                          <div className="space-y-1">
                            {here.map((l) => (
                          <div key={l.id} className="rounded border border-line bg-white px-2 py-1.5">
                            <div className="font-medium">{l.subject_name}</div>
                            {(isTeacher || (isFamily && !armId && multiWard)) && (
                              <div className="text-xs text-ink-soft">{l.arm_label}</div>
                            )}
                            {l.teacher_name && !isTeacher && (
                              <div className="text-xs text-ink-soft">{l.teacher_name}</div>
                            )}
                            {l.room && <div className="text-xs text-ink-soft">{l.room}</div>}
                            {isAdmin && (
                              <button onClick={() => removeLesson(l.id)} disabled={busy !== null}
                                      className="mt-0.5 text-xs text-ink-soft underline hover:text-sanction disabled:opacity-40">
                                remove
                              </button>
                            )}
                          </div>
                            ))}
                          </div>
                        ) : isAdmin ? (
                          <button
                            onClick={() => { setSlot({ day: d, period_id: p.id }); setNotice(null); }}
                            className="w-full rounded border border-dashed border-line px-2 py-2 text-xs text-ink-soft hover:border-ink hover:text-ink"
                          >
                            +
                          </button>
                        ) : (
                          <span className="text-xs text-ink-soft">—</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {grid && grid.periods.length > 0 && grid.lessons.length === 0 && isTeacher && (
        <p className="text-sm text-ink-soft">You have no lessons timetabled yet.</p>
      )}

      {/* place a lesson */}
      {isAdmin && slot && (
        <section className="rounded-lg border border-brass bg-brass/10 p-4 space-y-3 max-w-2xl">
          <p className="text-sm font-medium">
            Place a lesson — {DAY_LABEL[slot.day]},{" "}
            {grid?.periods.find((p) => p.id === slot.period_id)?.name}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <select value={lessonForm.subject_id}
                    onChange={(e) => setLessonForm({ ...lessonForm, subject_id: e.target.value })}
                    className="rounded border border-line px-2 py-1.5 text-sm bg-white">
              <option value="">Subject…</option>
              {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <select value={lessonForm.teacher_id}
                    onChange={(e) => setLessonForm({ ...lessonForm, teacher_id: e.target.value })}
                    className="rounded border border-line px-2 py-1.5 text-sm bg-white">
              <option value="">Teacher (optional)…</option>
              {teachers.map((t) => (
                <option key={t.id} value={t.id}>{t.first_name} {t.last_name}</option>
              ))}
            </select>
            <input value={lessonForm.room} placeholder="Room (optional)"
                   onChange={(e) => setLessonForm({ ...lessonForm, room: e.target.value })}
                   className="rounded border border-line px-2 py-1.5 text-sm" />
          </div>
          <div className="flex items-center gap-3">
            <button onClick={saveLesson} disabled={busy !== null}
                    className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
              {busy === "lesson" ? "Saving…" : "Place lesson"}
            </button>
            <button onClick={() => setSlot(null)} disabled={busy !== null}
                    className="text-sm text-ink-soft underline underline-offset-2">
              Cancel
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
