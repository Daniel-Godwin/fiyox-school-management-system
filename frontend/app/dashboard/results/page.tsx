"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { api, me, openPdf, User, ApiError } from "@/lib/api";

type Term = { id: string; name: string; session: string; is_current: boolean };
type Arm = { id: string; label: string };
type Row = {
  term_result_id: string;
  form_teacher_comment?: string;
  principal_comment?: string;
  student_id: string;
  admission_number: string;
  name: string;
  subjects_count: number;
  grand_total: number;
  average: number;
  position: number;
  class_size: number;
  is_published: boolean;
};

const ordinal = (n: number) =>
  n + (["th", "st", "nd", "rd"][(n % 100 >> 3) ^ 1 && n % 10] || "th");

export default function ResultsPage() {
  const [user, setUser] = useState<User | null>(null);
  const [terms, setTerms] = useState<Term[]>([]);
  const [arms, setArms] = useState<Arm[]>([]);
  const [termId, setTermId] = useState("");
  const [armId, setArmId] = useState("");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null); // "compute" | "publish" | pdf id
  const [editing, setEditing] = useState<string | null>(null);   // term_result_id
  const [draft, setDraft] = useState({ teacher: "", principal: "" });
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  useEffect(() => {
    Promise.all([me(), api<Term[]>("/api/academics/terms"), api<Arm[]>("/api/academics/arms")])
      .then(([u, t, a]) => {
        setUser(u);
        setTerms(t);
        setArms(a);
        const current = t.find((x) => x.is_current);
        if (current) setTermId(current.id);
      })
      .catch(() => setNotice({ kind: "err", text: "Could not load class lists. Is the backend running?" }));
  }, []);

  const ready = termId && armId;
  const isAdmin = user?.role === "school_admin" || user?.role === "super_admin";

  const load = useCallback(async () => {
    if (!ready) return;
    setNotice(null);
    try {
      const data = await api<Row[]>(`/api/results?arm_id=${armId}&term_id=${termId}`);
      setRows(data);
    } catch {
      setNotice({ kind: "err", text: "Could not load results." });
    }
  }, [ready, armId, termId]);

  useEffect(() => { load(); }, [load]);

  async function compute() {
    setBusy("compute");
    setNotice(null);
    try {
      const res = await api<{ students: number; subjects: number }>("/api/results/compute", {
        method: "POST",
        body: JSON.stringify({ arm_id: armId, term_id: termId }),
      });
      setNotice({
        kind: "ok",
        text: `Computed results for ${res.students} students across ${res.subjects} subject${res.subjects === 1 ? "" : "s"}.`,
      });
      await load();
    } catch (e) {
      setNotice({
        kind: "err",
        text: e instanceof ApiError && e.status === 403
          ? "Only the school admin can compute results."
          : "Compute failed. Are there scores entered for this class?",
      });
    } finally {
      setBusy(null);
    }
  }

  async function publishAll() {
    setBusy("publish");
    setNotice(null);
    try {
      const res = await api<{ published: number; already_published: number }>(
        "/api/results/publish",
        { method: "POST", body: JSON.stringify({ arm_id: armId, term_id: termId }) },
      );
      setNotice({
        kind: "ok",
        text: res.published > 0
          ? `Published ${res.published} result${res.published === 1 ? "" : "s"}. Parents and students can now view them.`
          : "Everything here is already published.",
      });
      await load();
    } catch {
      setNotice({ kind: "err", text: "Publish failed." });
    } finally {
      setBusy(null);
    }
  }

  function openComments(row: Row) {
    setEditing(row.term_result_id);
    setDraft({
      teacher: row.form_teacher_comment ?? "",
      principal: row.principal_comment ?? "",
    });
    setNotice(null);
  }

  async function saveComments(row: Row) {
    setBusy(`c-${row.term_result_id}`);
    setNotice(null);
    try {
      await api(`/api/term-results/${row.term_result_id}`, {
        method: "PATCH",
        body: JSON.stringify({
          form_teacher_comment: draft.teacher,
          principal_comment: draft.principal,
        }),
      });
      setNotice({ kind: "ok", text: `Comments saved for ${row.name}. Recomputing will not overwrite them.` });
      setEditing(null);
      await load();
    } catch {
      setNotice({ kind: "err", text: "Could not save the comments." });
    } finally { setBusy(null); }
  }

  async function pdf(row: Row) {
    setBusy(row.term_result_id);
    try {
      await openPdf(`/api/report/${row.student_id}/pdf?term_id=${termId}`);
    } catch {
      setNotice({ kind: "err", text: `Could not open ${row.name}'s report card.` });
    } finally {
      setBusy(null);
    }
  }

  const unpublished = rows?.filter((r) => !r.is_published).length ?? 0;

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">Results</h1>
        <p className="text-sm text-ink-soft mt-1">
          Compute a class&apos;s results from entered scores, review the ranking,
          then publish to parents and students.
        </p>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-xl">
        <label className="block">
          <span className="block text-xs font-medium text-ink-soft mb-1">Term</span>
          <select value={termId} onChange={(e) => setTermId(e.target.value)}
                  className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm">
            <option value="">Select term…</option>
            {terms.map((t) => (
              <option key={t.id} value={t.id}>{t.name} term · {t.session}</option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="block text-xs font-medium text-ink-soft mb-1">Class</span>
          <select value={armId} onChange={(e) => setArmId(e.target.value)}
                  className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm">
            <option value="">Select class…</option>
            {arms.map((a) => (
              <option key={a.id} value={a.id}>{a.label}</option>
            ))}
          </select>
        </label>
      </div>

      {!ready && (
        <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-6 max-w-xl">
          Results appear once a term and class are selected.
        </p>
      )}

      {ready && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            {isAdmin && (
              <>
                <button onClick={compute} disabled={busy !== null}
                        className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
                  {busy === "compute" ? "Computing…" : "Compute results"}
                </button>
                <button onClick={publishAll}
                        disabled={busy !== null || !rows || rows.length === 0 || unpublished === 0}
                        className="rounded-md border border-ink text-ink px-4 py-2 text-sm font-medium hover:bg-ink hover:text-white disabled:opacity-40">
                  {busy === "publish" ? "Publishing…" : `Publish all${unpublished ? ` (${unpublished})` : ""}`}
                </button>
              </>
            )}
            {notice && (
              <span role="status"
                    className={`text-sm ${notice.kind === "ok" ? "text-ledger" : "text-sanction"}`}>
                {notice.text}
              </span>
            )}
          </div>

          {rows && rows.length === 0 && (
            <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-6 max-w-xl">
              No computed results for this class yet.
              {isAdmin ? " Enter scores, then use Compute results." : " Ask the school admin to compute them."}
            </p>
          )}

          {rows && rows.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-line bg-card">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="bg-ink text-white text-left">
                    <th className="px-3 py-2 font-medium">Pos.</th>
                    <th className="px-3 py-2 font-medium">Student</th>
                    <th className="px-3 py-2 font-medium text-right">Subjects</th>
                    <th className="px-3 py-2 font-medium text-right">Total</th>
                    <th className="px-3 py-2 font-medium text-right">Average</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium text-right">Comments</th>
                    <th className="px-3 py-2 font-medium text-right">Report card</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                  <Fragment key={r.term_result_id}>
                    <tr className={i % 2 ? "bg-paper" : "bg-card"}>
                      <td className="px-3 py-2 tabular font-medium">
                        {ordinal(r.position)}
                        <span className="text-ink-soft font-normal"> / {r.class_size}</span>
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        <span className="tabular text-ink-soft mr-2">{r.admission_number}</span>
                        {r.name}
                      </td>
                      <td className="px-3 py-2 text-right tabular">{r.subjects_count}</td>
                      <td className="px-3 py-2 text-right tabular">{r.grand_total}</td>
                      <td className="px-3 py-2 text-right tabular">{r.average}%</td>
                      <td className="px-3 py-2">
                        {r.is_published ? (
                          <span className="inline-block rounded-full bg-ledger/10 text-ledger px-2 py-0.5 text-xs font-medium">
                            Published
                          </span>
                        ) : (
                          <span className="inline-block rounded-full bg-brass/15 text-ink px-2 py-0.5 text-xs font-medium">
                            Draft
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button onClick={() => openComments(r)} disabled={busy !== null}
                                className="text-ink underline underline-offset-2 hover:text-ink-soft disabled:opacity-50">
                          {editing === r.term_result_id ? "Editing…" : "Edit"}
                        </button>
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button onClick={() => pdf(r)} disabled={busy !== null}
                                className="text-ink underline underline-offset-2 hover:text-ink-soft disabled:opacity-50">
                          {busy === r.term_result_id ? "Opening…" : "Open PDF"}
                        </button>
                      </td>
                    </tr>
                    {editing === r.term_result_id && (
                      <tr className={i % 2 ? "bg-paper" : "bg-card"}>
                        <td colSpan={8} className="px-3 pb-3">
                          <div className="rounded-md border border-line bg-white p-3 space-y-2">
                            <p className="text-xs text-ink-soft">
                              Fiyox drafted these from {r.name.split(" ")[0]}&apos;s performance
                              against the class. Edit freely — your words are kept even if the
                              term is recomputed.
                            </p>
                            <label className="block">
                              <span className="block text-xs text-ink-soft mb-1">Form teacher&apos;s comment</span>
                              <textarea value={draft.teacher} rows={2} maxLength={500}
                                        onChange={(e) => setDraft({ ...draft, teacher: e.target.value })}
                                        className="w-full rounded border border-line px-2 py-1.5 text-sm" />
                            </label>
                            <label className="block">
                              <span className="block text-xs text-ink-soft mb-1">Principal&apos;s comment</span>
                              <textarea value={draft.principal} rows={2} maxLength={500}
                                        onChange={(e) => setDraft({ ...draft, principal: e.target.value })}
                                        className="w-full rounded border border-line px-2 py-1.5 text-sm" />
                            </label>
                            <div className="flex items-center gap-3">
                              <button onClick={() => saveComments(r)} disabled={busy !== null}
                                      className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
                                {busy === `c-${r.term_result_id}` ? "Saving…" : "Save comments"}
                              </button>
                              <button onClick={() => setEditing(null)} disabled={busy !== null}
                                      className="text-sm text-ink-soft underline underline-offset-2">
                                Cancel
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
