"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

type Term = { id: string; name: string; session: string; is_current: boolean };
type Arm = { id: string; label: string; class_id: string; class_name: string };
type Subject = { id: string; name: string; code: string | null };
type Component = { id: string; name: string; max_score: number; sequence: number };

export default function SetupPage() {
  const [terms, setTerms] = useState<Term[]>([]);
  const [arms, setArms] = useState<Arm[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [components, setComponents] = useState<Component[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  // quick setup form
  const [qs, setQs] = useState({
    session_name: "2025/2026",
    term: "first",
    classes: "JSS1, JSS2, JSS3",
    arms: "A",
    subjects: "Mathematics, English Language, Basic Science",
  });

  // individual adds
  const [newClass, setNewClass] = useState({ name: "", category: "junior" });
  const [newArm, setNewArm] = useState({ class_id: "", name: "" });
  const [newSubject, setNewSubject] = useState({ name: "", code: "" });

  const load = useCallback(async () => {
    try {
      const [t, a, s, c] = await Promise.all([
        api<Term[]>("/api/academics/terms"),
        api<Arm[]>("/api/academics/arms"),
        api<Subject[]>("/api/academics/subjects"),
        api<Component[]>("/api/assessment-components"),
      ]);
      setTerms(t); setArms(a); setSubjects(s);
      setComponents([...c].sort((x, y) => x.sequence - y.sequence));
    } catch (e) {
      setNotice({
        kind: "err",
        text: e instanceof ApiError && e.status === 403
          ? "Only the school admin can configure the school."
          : "Could not load the school structure.",
      });
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const configured = terms.length > 0;
  const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

  async function runQuickSetup() {
    setBusy("quick"); setNotice(null);
    try {
      const res = await api<{ classes: string[]; subjects: string[] }>(
        "/api/academics/quick-setup", {
          method: "POST",
          body: JSON.stringify({
            session_name: qs.session_name.trim(),
            term: qs.term,
            classes: split(qs.classes),
            arms: split(qs.arms),
            subjects: split(qs.subjects),
            with_default_components: true,
          }),
        });
      setNotice({
        kind: "ok",
        text: `School configured — ${res.classes.length} classes, ${res.subjects.length} subjects, and the standard CA/Exam columns. You can now admit students.`,
      });
      await load();
    } catch (e) {
      setNotice({
        kind: "err",
        text: e instanceof ApiError ? e.message : "Setup failed.",
      });
    } finally { setBusy(null); }
  }

  async function addClass() {
    if (!newClass.name.trim()) return;
    setBusy("class"); setNotice(null);
    try {
      await api("/api/academics/classes", {
        method: "POST",
        body: JSON.stringify({ name: newClass.name.trim(), category: newClass.category }),
      });
      setNewClass({ name: "", category: newClass.category });
      await load();
    } catch { setNotice({ kind: "err", text: "Could not add the class." }); }
    finally { setBusy(null); }
  }

  async function addArm() {
    if (!newArm.class_id || !newArm.name.trim()) {
      setNotice({ kind: "err", text: "Pick a class and name the arm (e.g. B)." });
      return;
    }
    setBusy("arm"); setNotice(null);
    try {
      await api("/api/academics/arms", {
        method: "POST",
        body: JSON.stringify({ class_id: newArm.class_id, name: newArm.name.trim() }),
      });
      setNewArm({ class_id: "", name: "" });
      await load();
    } catch { setNotice({ kind: "err", text: "Could not add the arm." }); }
    finally { setBusy(null); }
  }

  async function addSubject() {
    if (!newSubject.name.trim()) return;
    setBusy("subject"); setNotice(null);
    try {
      await api("/api/academics/subjects", {
        method: "POST",
        body: JSON.stringify({ name: newSubject.name.trim(),
                               code: newSubject.code.trim() || null }),
      });
      setNewSubject({ name: "", code: "" });
      await load();
    } catch { setNotice({ kind: "err", text: "Could not add the subject." }); }
    finally { setBusy(null); }
  }

  // unique classes from arms
  const classes = Array.from(
    new Map(arms.map((a) => [a.class_id, a.class_name])).entries(),
  ).map(([id, name]) => ({ id, name }));

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">School setup</h1>
        <p className="text-sm text-ink-soft mt-1">
          Sessions, terms, classes, arms, subjects and the score columns. Do this
          once — everything else in Fiyox depends on it.
        </p>
      </header>

      {notice && (
        <p role="status"
           className={`text-sm ${notice.kind === "ok" ? "text-ledger" : "text-sanction"}`}>
          {notice.text}
        </p>
      )}

      {!configured && (
        <section className="rounded-lg border border-brass bg-brass/10 p-4 space-y-3">
          <div>
            <p className="font-medium">Quick setup</p>
            <p className="text-sm text-ink-soft">
              This school has no academic structure yet. One click creates the
              session, current term, classes with arms, subjects, and the standard
              Nigerian CA/Exam columns (Test 1, Test 2, Assignment /10 each + Exam /70).
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="block">
              <span className="block text-xs text-ink-soft mb-1">Session</span>
              <input value={qs.session_name}
                     onChange={(e) => setQs({ ...qs, session_name: e.target.value })}
                     className="w-full rounded border border-line px-2 py-1.5 text-sm bg-white" />
            </label>
            <label className="block">
              <span className="block text-xs text-ink-soft mb-1">Current term</span>
              <select value={qs.term} onChange={(e) => setQs({ ...qs, term: e.target.value })}
                      className="w-full rounded border border-line px-2 py-1.5 text-sm bg-white">
                <option value="first">First</option>
                <option value="second">Second</option>
                <option value="third">Third</option>
              </select>
            </label>
            <label className="block">
              <span className="block text-xs text-ink-soft mb-1">Classes (comma separated)</span>
              <input value={qs.classes}
                     onChange={(e) => setQs({ ...qs, classes: e.target.value })}
                     className="w-full rounded border border-line px-2 py-1.5 text-sm bg-white" />
            </label>
            <label className="block">
              <span className="block text-xs text-ink-soft mb-1">Arms per class</span>
              <input value={qs.arms}
                     onChange={(e) => setQs({ ...qs, arms: e.target.value })}
                     className="w-full rounded border border-line px-2 py-1.5 text-sm bg-white" />
            </label>
            <label className="block sm:col-span-2">
              <span className="block text-xs text-ink-soft mb-1">Subjects (comma separated)</span>
              <input value={qs.subjects}
                     onChange={(e) => setQs({ ...qs, subjects: e.target.value })}
                     className="w-full rounded border border-line px-2 py-1.5 text-sm bg-white" />
            </label>
          </div>
          <button onClick={runQuickSetup} disabled={busy !== null}
                  className="rounded-md bg-ink text-white px-5 py-2.5 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
            {busy === "quick" ? "Setting up…" : "Set up my school"}
          </button>
        </section>
      )}

      {/* current structure */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="rounded-lg border border-line bg-card p-4">
          <p className="text-sm font-medium mb-2">Terms</p>
          {terms.length === 0 ? (
            <p className="text-sm text-ink-soft">None yet.</p>
          ) : (
            <ul className="text-sm space-y-1">
              {terms.map((t) => (
                <li key={t.id}>
                  {t.name} term · {t.session}{" "}
                  {t.is_current && (
                    <span className="rounded-full bg-ledger/10 text-ledger px-2 py-0.5 text-xs font-medium">
                      current
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-lg border border-line bg-card p-4">
          <p className="text-sm font-medium mb-2">Score columns</p>
          {components.length === 0 ? (
            <p className="text-sm text-ink-soft">None yet.</p>
          ) : (
            <p className="text-sm">
              {components.map((c) => `${c.name} /${c.max_score}`).join(" · ")}
              <span className="text-ink-soft">
                {" "}(total {components.reduce((s, c) => s + c.max_score, 0)})
              </span>
            </p>
          )}
        </section>

        <section className="rounded-lg border border-line bg-card p-4 space-y-3">
          <p className="text-sm font-medium">Classes &amp; arms</p>
          {arms.length === 0 ? (
            <p className="text-sm text-ink-soft">None yet.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {arms.map((a) => (
                <span key={a.id}
                      className="rounded-full border border-line bg-paper px-3 py-1 text-xs">
                  {a.label}
                </span>
              ))}
            </div>
          )}
          <div className="flex flex-wrap items-end gap-2 pt-1">
            <label className="block">
              <span className="block text-xs text-ink-soft mb-1">New class</span>
              <input value={newClass.name} placeholder="SS1"
                     onChange={(e) => setNewClass({ ...newClass, name: e.target.value })}
                     className="w-24 rounded border border-line px-2 py-1.5 text-sm" />
            </label>
            <select value={newClass.category}
                    onChange={(e) => setNewClass({ ...newClass, category: e.target.value })}
                    className="rounded border border-line px-2 py-1.5 text-sm bg-white">
              <option value="junior">Junior</option>
              <option value="senior">Senior</option>
            </select>
            <button onClick={addClass} disabled={busy !== null}
                    className="rounded-md border border-ink text-ink px-3 py-1.5 text-xs font-medium hover:bg-ink hover:text-white disabled:opacity-40">
              {busy === "class" ? "Adding…" : "Add class"}
            </button>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="block">
              <span className="block text-xs text-ink-soft mb-1">New arm in</span>
              <select value={newArm.class_id}
                      onChange={(e) => setNewArm({ ...newArm, class_id: e.target.value })}
                      className="rounded border border-line px-2 py-1.5 text-sm bg-white">
                <option value="">Class…</option>
                {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
            <input value={newArm.name} placeholder="B"
                   onChange={(e) => setNewArm({ ...newArm, name: e.target.value })}
                   className="w-20 rounded border border-line px-2 py-1.5 text-sm" />
            <button onClick={addArm} disabled={busy !== null}
                    className="rounded-md border border-ink text-ink px-3 py-1.5 text-xs font-medium hover:bg-ink hover:text-white disabled:opacity-40">
              {busy === "arm" ? "Adding…" : "Add arm"}
            </button>
          </div>
        </section>

        <section className="rounded-lg border border-line bg-card p-4 space-y-3">
          <p className="text-sm font-medium">Subjects</p>
          {subjects.length === 0 ? (
            <p className="text-sm text-ink-soft">None yet.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {subjects.map((s) => (
                <span key={s.id}
                      className="rounded-full border border-line bg-paper px-3 py-1 text-xs">
                  {s.name}{s.code ? ` (${s.code})` : ""}
                </span>
              ))}
            </div>
          )}
          <div className="flex flex-wrap items-end gap-2 pt-1">
            <input value={newSubject.name} placeholder="Civic Education"
                   onChange={(e) => setNewSubject({ ...newSubject, name: e.target.value })}
                   className="rounded border border-line px-2 py-1.5 text-sm" />
            <input value={newSubject.code} placeholder="CIV"
                   onChange={(e) => setNewSubject({ ...newSubject, code: e.target.value })}
                   className="w-20 rounded border border-line px-2 py-1.5 text-sm" />
            <button onClick={addSubject} disabled={busy !== null}
                    className="rounded-md border border-ink text-ink px-3 py-1.5 text-xs font-medium hover:bg-ink hover:text-white disabled:opacity-40">
              {busy === "subject" ? "Adding…" : "Add subject"}
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
