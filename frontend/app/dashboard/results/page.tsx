"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { api, openPdf, User, ApiError } from "@/lib/api";
import { cachedGet, queuedPost, putCache } from "@/lib/offline/offlineApi";
import { Kpi, BRAND as C } from "@/components/Panels";
import { Columns } from "@/components/Charts";

type Term = { id: string; name: string; session: string; is_current: boolean };
type Arm = { id: string; label: string };
type Row = {
  term_result_id: string | null;
  form_teacher_comment?: string;
  principal_comment?: string;
  student_id: string;
  admission_number: string;
  name: string;
  subjects_count: number;
  grand_total: number;
  average: number | null;
  position: number;
  class_size: number;
  is_published: boolean;
  approval_status: "draft" | "submitted" | "approved" | "rejected" | "not_computed";
  approval_note: string;
  computed: boolean;
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
  const [suggestions, setSuggestions] = useState<{ teacher: string[]; principal: string[] }>({ teacher: [], principal: [] });
  const [gridOpen, setGridOpen] = useState(false);
  const [gridKind, setGridKind] = useState<"affective" | "psychomotor">("affective");
  const [gridTraits, setGridTraits] = useState<string[]>([]);
  const [gridRows, setGridRows] = useState<{ student_id: string; admission_number: string; name: string; ratings: Record<string, number> }[]>([]);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [approvalOn, setApprovalOn] = useState(false);

  useEffect(() => {
    Promise.all([
      cachedGet<User>("/api/auth/me"),
      cachedGet<Term[]>("/api/academics/terms"),
      cachedGet<Arm[]>("/api/academics/arms"),
    ])
      .then(([u, t, a]) => {
        setUser(u.data);
        setTerms(t.data);
        setArms(a.data);
        const current = t.data.find((x) => x.is_current);
        if (current) setTermId(current.id);
      })
      .catch(() => setNotice({ kind: "err", text: "Could not load class lists. Open this page once while online so it can be used offline later." }));
    // does this school route results through the approval gate?
    cachedGet<{ result_approval_required: boolean }>("/api/schools/me")
      .then((s) => setApprovalOn(!!s.data.result_approval_required))
      .catch(() => setApprovalOn(false));
  }, []);

  const ready = termId && armId;
  const isAdmin = user?.role === "school_admin" || user?.role === "super_admin";

  const load = useCallback(async () => {
    if (!ready) return;
    setNotice(null);
    try {
      const data = await cachedGet<Row[]>(`/api/results?arm_id=${armId}&term_id=${termId}`);
      setRows(data.data);
      if (data.stale) {
        setNotice({ kind: "ok", text: "You're offline — showing the last saved copy. Ratings you enter will sync automatically." });
      }
    } catch {
      setNotice({ kind: "err", text: "Could not load results. Open this page once while online to use it offline." });
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

  async function workflow(action: "submit" | "approve", label: string) {
    setBusy(action);
    setNotice(null);
    try {
      const res = await api<{ submitted?: number; approved?: number; note: string }>(
        `/api/results/${action}`,
        { method: "POST", body: JSON.stringify({ arm_id: armId, term_id: termId }) });
      setNotice({ kind: "ok", text: res.note });
      await load();
    } catch {
      setNotice({ kind: "err", text: `Could not ${label}.` });
    } finally { setBusy(null); }
  }

  async function returnToTeacher() {
    const reason = window.prompt(
      "Return these results to the form teacher. What needs correcting?");
    if (reason === null) return;
    setBusy("return");
    setNotice(null);
    try {
      const res = await api<{ returned: number; note: string }>(
        `/api/results/return?arm_id=${armId}&term_id=${termId}`,
        { method: "POST", body: JSON.stringify({ form_teacher_comment: reason }) });
      setNotice({ kind: "ok", text: res.note });
      await load();
    } catch {
      setNotice({ kind: "err", text: "Could not return the results." });
    } finally { setBusy(null); }
  }

  async function publishAll() {
    setBusy("publish");
    setNotice(null);
    try {
      const res = await api<{ published: number; already_published: number; blocked_unapproved: number; note?: string }>(
        "/api/results/publish",
        { method: "POST", body: JSON.stringify({ arm_id: armId, term_id: termId }) },
      );
      setNotice({
        kind: res.published > 0 || res.already_published > 0 ? "ok" : "err",
        text: res.published > 0
          ? `Published ${res.published} result${res.published === 1 ? "" : "s"}. Parents and students can now view them.`
          : res.note
            ? res.note
            : "Everything here is already published.",
      });
      await load();
    } catch {
      setNotice({ kind: "err", text: "Publish failed." });
    } finally {
      setBusy(null);
    }
  }

  async function openGrid(kind: "affective" | "psychomotor") {
    setBusy(kind === "affective" ? "grid-load" : "grid-load-psy"); setNotice(null);
    try {
      const gg = await cachedGet<{ traits: string[]; students: typeof gridRows }>(
        `/api/results/${kind}?arm_id=${armId}&term_id=${termId}`);
      const g = gg.data;
      setGridKind(kind);
      setGridTraits(g.traits);
      setGridRows(g.students);
      setGridOpen(true);
      if (g.traits.length === 0) {
        const what = kind === "affective" ? "character traits" : "psychomotor skills";
        setNotice({ kind: "err", text: `No ${what} set up yet — add them under School setup.` });
      }
    } catch {
      setNotice({ kind: "err", text: "Could not load the ratings grid." });
    } finally { setBusy(null); }
  }

  function setRating(studentId: string, trait: string, value: number) {
    setGridRows((rows) => rows.map((r) =>
      r.student_id === studentId
        ? { ...r, ratings: value === 0
            ? Object.fromEntries(Object.entries(r.ratings).filter(([k]) => k !== trait))
            : { ...r.ratings, [trait]: value } }
        : r));
  }

  async function saveGrid() {
    setBusy("grid-save"); setNotice(null);
    try {
      const ratings: Record<string, Record<string, number>> = {};
      for (const r of gridRows) ratings[r.student_id] = r.ratings;
      const what = gridKind === "affective" ? "Character" : "Skill";
      const cls = arms.find((a) => a.id === armId)?.label ?? "class";
      // upsert keyed by student+trait+term on the server, so a replay is harmless
      const r = await queuedPost<{ saved: number }>(
        `/api/results/${gridKind}`,
        { arm_id: armId, term_id: termId, ratings },
        `${what} ratings — ${cls}`,
      );
      if (r.queued) {
        // keep the entered ratings in the cache so reopening the grid shows them
        void putCache(
          `/api/results/${gridKind}?arm_id=${armId}&term_id=${termId}`,
          { traits: gridTraits, students: gridRows },
        );
        setNotice({ kind: "ok", text: "Ratings saved on this device — they will sync automatically when you're back online." });
      } else {
        const n = r.result?.saved ?? 0;
        setNotice({ kind: "ok", text: `${what} ratings saved for ${n} student${n === 1 ? "" : "s"}.` });
      }
      setGridOpen(false);
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not save the ratings." });
    } finally { setBusy(null); }
  }

  function openComments(row: Row) {
    setEditing(row.term_result_id);
    setDraft({
      teacher: row.form_teacher_comment ?? "",
      principal: row.principal_comment ?? "",
    });
    setSuggestions({ teacher: [], principal: [] });
    setNotice(null);
    // offer comment-bank entries that fit this student's average
    const avg = row.average;
    Promise.all([
      api<{ text: string }[]>(`/api/comment-bank/suggest?average=${avg}&audience=form_teacher`).catch(() => []),
      api<{ text: string }[]>(`/api/comment-bank/suggest?average=${avg}&audience=principal`).catch(() => []),
    ]).then(([t, p]) => setSuggestions({
      teacher: t.map((x) => x.text), principal: p.map((x) => x.text),
    }));
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

  const unpublished = rows?.filter((r) => r.computed && !r.is_published).length ?? 0;
  const notComputed = rows?.filter((r) => !r.computed).length ?? 0;
  // the arm moves through the workflow together; derive one status for the controls
  const hasRows = !!rows && rows.length > 0;
  const anyRejected = rows?.some((r) => r.approval_status === "rejected") ?? false;
  // a fresh draft or a corrected-after-rejection result can be submitted
  const anySubmittable = rows?.some((r) => r.approval_status === "draft" || r.approval_status === "rejected") ?? false;
  const anySubmitted = rows?.some((r) => r.approval_status === "submitted") ?? false;
  const anyApprovedUnpublished =
    rows?.some((r) => r.approval_status === "approved" && !r.is_published) ?? false;
  const returnNote = rows?.find((r) => r.approval_status === "rejected" && r.approval_note)?.approval_note ?? "";

  // class performance summary from the computed rows
  const computedRows = rows?.filter((r) => r.computed && r.average !== null) ?? [];
  const classAvg = computedRows.length
    ? Math.round(computedRows.reduce((s, r) => s + (r.average || 0), 0) / computedRows.length) : null;
  const passRate = computedRows.length
    ? Math.round((computedRows.filter((r) => (r.average || 0) >= 40).length / computedRows.length) * 100) : null;
  const topAvg = computedRows.length ? Math.max(...computedRows.map((r) => r.average || 0)) : null;
  const inBand = (lo: number, hi: number) => computedRows.filter((r) => (r.average || 0) >= lo && (r.average || 0) < hi).length;
  const bands = [
    { label: "70+", value: inBand(70, 1e9), color: C.ledger },
    { label: "60s", value: inBand(60, 70), color: C.ledger },
    { label: "50s", value: inBand(50, 60), color: C.brass },
    { label: "40s", value: inBand(40, 50), color: C.brass },
    { label: "<40", value: inBand(0, 40), color: C.sanction },
  ];

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
              <button onClick={compute} disabled={busy !== null}
                      className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
                {busy === "compute" ? "Computing…" : "Compute results"}
              </button>
            )}

            {hasRows && (
              <button onClick={() => openGrid("affective")} disabled={busy !== null}
                      className="rounded-md border border-ink text-ink px-4 py-2 text-sm font-medium hover:bg-ink hover:text-white disabled:opacity-40">
                {busy === "grid-load" ? "Loading…" : "Rate character"}
              </button>
            )}
            {hasRows && (
              <button onClick={() => openGrid("psychomotor")} disabled={busy !== null}
                      className="rounded-md border border-ink text-ink px-4 py-2 text-sm font-medium hover:bg-ink hover:text-white disabled:opacity-40">
                {busy === "grid-load-psy" ? "Loading…" : "Rate skills"}
              </button>
            )}

            {/* ---- approval gate ON: submit -> approve -> publish ---- */}
            {approvalOn && hasRows && anySubmittable && (
              <button onClick={() => workflow("submit", "submit for approval")}
                      disabled={busy !== null}
                      className="rounded-md bg-brass text-white px-4 py-2 text-sm font-medium hover:opacity-90 disabled:opacity-50">
                {busy === "submit" ? "Submitting…" : anyRejected ? "Resubmit for approval" : "Submit for approval"}
              </button>
            )}
            {approvalOn && isAdmin && hasRows && anySubmitted && (
              <>
                <button onClick={() => workflow("approve", "approve")}
                        disabled={busy !== null}
                        className="rounded-md bg-ledger text-white px-4 py-2 text-sm font-medium hover:opacity-90 disabled:opacity-50">
                  {busy === "approve" ? "Approving…" : "Approve"}
                </button>
                <button onClick={returnToTeacher} disabled={busy !== null}
                        className="rounded-md border border-sanction text-sanction px-4 py-2 text-sm font-medium hover:bg-sanction hover:text-white disabled:opacity-40">
                  {busy === "return" ? "Returning…" : "Return for revision"}
                </button>
              </>
            )}
            {approvalOn && isAdmin && hasRows && anyApprovedUnpublished && (
              <button onClick={publishAll} disabled={busy !== null}
                      className="rounded-md border border-ink text-ink px-4 py-2 text-sm font-medium hover:bg-ink hover:text-white disabled:opacity-40">
                {busy === "publish" ? "Publishing…" : `Publish to parents${unpublished ? ` (${unpublished})` : ""}`}
              </button>
            )}

            {/* ---- approval gate OFF (default): admin publishes directly ---- */}
            {!approvalOn && isAdmin && (
              <button onClick={publishAll}
                      disabled={busy !== null || !hasRows || unpublished === 0}
                      className="rounded-md border border-ink text-ink px-4 py-2 text-sm font-medium hover:bg-ink hover:text-white disabled:opacity-40">
                {busy === "publish" ? "Publishing…" : `Publish all${unpublished ? ` (${unpublished})` : ""}`}
              </button>
            )}
            {notice && (
              <span role="status"
                    className={`text-sm ${notice.kind === "ok" ? "text-ledger" : "text-sanction"}`}>
                {notice.text}
              </span>
            )}
          </div>

          {gridOpen && gridTraits.length > 0 && (
            <section className="rounded-lg border border-brass bg-brass/5 p-4 space-y-3">
              <div className="flex items-baseline justify-between gap-2">
                <p className="text-sm font-medium">{gridKind === "affective" ? "Character ratings (1–5)" : "Skill ratings (1–5)"}</p>
                <button onClick={() => setGridOpen(false)}
                        className="text-xs text-ink-soft underline underline-offset-2">Close</button>
              </div>
              <div className="overflow-x-auto rounded-lg border border-line bg-card">
                <table className="min-w-[560px] w-full text-sm">
                  <thead>
                    <tr className="bg-ink text-white text-left">
                      <th className="px-3 py-2 font-medium">Student</th>
                      {gridTraits.map((t) => (
                        <th key={t} className="px-2 py-2 font-medium text-center whitespace-nowrap">{t}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {gridRows.map((r, i) => (
                      <tr key={r.student_id} className={i % 2 ? "bg-paper" : "bg-card"}>
                        <td className="px-3 py-1.5 whitespace-nowrap">
                          <span className="tabular text-ink-soft mr-2">{r.admission_number}</span>{r.name}
                        </td>
                        {gridTraits.map((t) => (
                          <td key={t} className="px-2 py-1.5 text-center">
                            <select value={r.ratings[t] ?? 0}
                                    onChange={(e) => setRating(r.student_id, t, Number(e.target.value))}
                                    className="rounded border border-line px-1.5 py-1 text-sm">
                              <option value={0}>–</option>
                              {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
                            </select>
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button onClick={saveGrid} disabled={busy !== null}
                      className="rounded-md bg-ink text-white px-4 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
                {busy === "grid-save" ? "Saving…" : "Save ratings"}
              </button>
            </section>
          )}

          {returnNote && (
            <div className="rounded-lg border border-sanction/40 bg-sanction/5 p-3 max-w-2xl">
              <p className="text-sm">
                <span className="font-medium text-sanction">Rejected — reason: </span>
                {returnNote}
              </p>
              <p className="text-xs text-ink-soft mt-1">
                Correct the scores in Score Entry, recompute, then use
                “Resubmit for approval”. The reason stays here until you resubmit.
              </p>
            </div>
          )}

          {rows && rows.length === 0 && (
            <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-6 max-w-xl">
              No students in this class yet.
            </p>
          )}

          {rows && rows.length > 0 && notComputed > 0 && (
            <p className="text-sm text-ink-soft border border-dashed border-line rounded-lg p-3 max-w-2xl">
              <span className="font-medium text-ink">{notComputed} student{notComputed === 1 ? "" : "s"}</span> in
              this class {notComputed === 1 ? "has" : "have"} no computed result for this term yet
              {isAdmin ? " — enter their scores, then use Compute results." : "."}
            </p>
          )}

          {/* class performance summary */}
          {computedRows.length > 0 && (
            <div className="space-y-3 fiyox-rise">
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <Kpi label="Computed" value={computedRows.length.toString()}
                     hint={notComputed > 0 ? `${notComputed} still pending` : "whole class"} accent={C.ink} />
                <Kpi label="Class average" value={classAvg === null ? "—" : `${classAvg}%`}
                     accent={classAvg !== null && classAvg >= 50 ? C.ledger : C.brass} />
                <Kpi label="Pass rate" value={passRate === null ? "—" : `${passRate}%`}
                     hint="at or above 40%" accent={passRate !== null && passRate >= 60 ? C.ledger : C.brass} />
                <Kpi label="Top average" value={topAvg === null ? "—" : `${topAvg}%`} accent={C.ledger} />
              </div>
              <div className="bg-card border border-line rounded-xl p-5">
                <p className="text-xs text-ink-soft mb-3 uppercase tracking-wide">Average spread</p>
                <Columns data={bands} />
              </div>
            </div>
          )}

          {rows && rows.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-line bg-card">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="bg-ink text-white text-left">
                    <th className="px-3 py-2 font-medium">Pos.</th>
                    <th className="px-3 py-2 font-medium">Student</th>
                    <th className="px-3 py-2 font-medium text-right hidden sm:table-cell">Subjects</th>
                    <th className="px-3 py-2 font-medium text-right hidden sm:table-cell">Total</th>
                    <th className="px-3 py-2 font-medium text-right">Average</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium text-right">Comments</th>
                    <th className="px-3 py-2 font-medium text-right">Report card</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                  <Fragment key={r.student_id}>
                    {!r.computed ? (
                    <tr className={i % 2 ? "bg-paper" : "bg-card"}>
                      <td className="px-3 py-2 text-ink-soft">—</td>
                      <td className="px-3 py-2 sm:whitespace-nowrap">
                        <span className="tabular text-ink-soft block text-xs sm:inline sm:text-sm sm:mr-2">{r.admission_number}</span>
                        {r.name}
                      </td>
                      <td className="px-3 py-2 text-right text-ink-soft hidden sm:table-cell">—</td>
                      <td className="px-3 py-2 text-right text-ink-soft hidden sm:table-cell">—</td>
                      <td className="px-3 py-2 text-right text-ink-soft">—</td>
                      <td className="px-3 py-2">
                        <span className="inline-block rounded-full bg-brass/15 text-brass-ink px-2 py-0.5 text-xs font-medium">
                          Not computed
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right text-ink-soft text-xs">—</td>
                      <td className="px-3 py-2 text-right text-ink-soft text-xs">No result yet</td>
                    </tr>
                    ) : (
                    <>
                    <tr className={i % 2 ? "bg-paper" : "bg-card"}>
                      <td className="px-3 py-2 tabular font-medium">
                        {ordinal(r.position)}
                        <span className="text-ink-soft font-normal"> / {r.class_size}</span>
                      </td>
                      <td className="px-3 py-2 sm:whitespace-nowrap">
                        <span className="tabular text-ink-soft block text-xs sm:inline sm:text-sm sm:mr-2">{r.admission_number}</span>
                        {r.name}
                      </td>
                      <td className="px-3 py-2 text-right tabular hidden sm:table-cell">{r.subjects_count}</td>
                      <td className="px-3 py-2 text-right tabular hidden sm:table-cell">{r.grand_total}</td>
                      <td className="px-3 py-2 text-right tabular">{r.average}%</td>
                      <td className="px-3 py-2">
                        {r.is_published ? (
                          <span className="inline-block rounded-full bg-ledger/10 text-ledger px-2 py-0.5 text-xs font-medium">
                            Published
                          </span>
                        ) : r.approval_status === "approved" ? (
                          <span className="inline-block rounded-full bg-ledger/10 text-ledger px-2 py-0.5 text-xs font-medium">
                            Approved
                          </span>
                        ) : r.approval_status === "submitted" ? (
                          <span className="inline-block rounded-full bg-brass/20 text-ink px-2 py-0.5 text-xs font-medium">
                            Pending approval
                          </span>
                        ) : r.approval_status === "rejected" ? (
                          <span className="inline-block rounded-full bg-sanction/10 text-sanction px-2 py-0.5 text-xs font-medium">
                            Rejected
                          </span>
                        ) : (
                          <span className="inline-block rounded-full bg-line text-ink-soft px-2 py-0.5 text-xs font-medium">
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
                              {suggestions.teacher.length > 0 && (
                                <div className="mt-1 flex flex-wrap gap-1">
                                  {suggestions.teacher.map((s, k) => (
                                    <button key={k} type="button"
                                            onClick={() => setDraft((d) => ({ ...d, teacher: s }))}
                                            className="rounded-full border border-line bg-paper px-2 py-0.5 text-xs text-ink-soft hover:border-ink hover:text-ink">
                                      {s}
                                    </button>
                                  ))}
                                </div>
                              )}
                            </label>
                            <label className="block">
                              <span className="block text-xs text-ink-soft mb-1">Principal&apos;s comment</span>
                              <textarea value={draft.principal} rows={2} maxLength={500}
                                        onChange={(e) => setDraft({ ...draft, principal: e.target.value })}
                                        className="w-full rounded border border-line px-2 py-1.5 text-sm" />
                              {suggestions.principal.length > 0 && (
                                <div className="mt-1 flex flex-wrap gap-1">
                                  {suggestions.principal.map((s, k) => (
                                    <button key={k} type="button"
                                            onClick={() => setDraft((d) => ({ ...d, principal: s }))}
                                            className="rounded-full border border-line bg-paper px-2 py-0.5 text-xs text-ink-soft hover:border-ink hover:text-ink">
                                      {s}
                                    </button>
                                  ))}
                                </div>
                              )}
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
                    </>
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
