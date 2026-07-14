"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

type Arm = { id: string; label: string };
type Term = { id: string; name: string; session: string; is_current: boolean };
type Row = { student_id: string; admission_number: string; name: string };
type Preview = {
  from: string; to: string | null; graduating_class: boolean;
  promoted: Row[]; repeated: Row[]; graduated: Row[]; committed: boolean;
};
type Risk = {
  student_id: string; name: string; admission_number: string; class_label: string;
  average: number; position: number; class_size: number;
  attendance_pct: number | null; owes_fees: boolean;
  level: "high" | "moderate" | "watch"; score: number;
  reasons: string[]; recommended_action: string;
};
type AiStatus = { llm_configured: boolean; message: string };

const LEVEL_STYLE: Record<string, string> = {
  high: "bg-sanction/10 text-sanction border-sanction/40",
  moderate: "bg-brass/15 text-ink border-brass",
  watch: "bg-paper text-ink-soft border-line",
};

export default function EndOfTermPage() {
  const [arms, setArms] = useState<Arm[]>([]);
  const [terms, setTerms] = useState<Term[]>([]);
  const [termId, setTermId] = useState("");
  const [armId, setArmId] = useState("");

  const [preview, setPreview] = useState<Preview | null>(null);
  const [repeats, setRepeats] = useState<string[]>([]);
  const [risks, setRisks] = useState<Risk[] | null>(null);
  const [ai, setAi] = useState<AiStatus | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  useEffect(() => {
    Promise.all([
      api<Arm[]>("/api/academics/arms"),
      api<Term[]>("/api/academics/terms"),
      api<AiStatus>("/api/ai/status"),
    ]).then(([a, t, s]) => {
      setArms(a);
      setTerms(t);
      setAi(s);
      if (a[0]) setArmId(a[0].id);
      const cur = t.find((x) => x.is_current);
      if (cur) setTermId(cur.id);
    }).catch(() => setNotice({ kind: "err", text: "Could not load the page." }));
  }, []);

  const loadRisks = useCallback(async () => {
    if (!termId) return;
    try {
      const r = await api<Risk[]>(`/api/ai/at-risk?term_id=${termId}`);
      setRisks(r);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) return;
      setRisks([]);
    }
  }, [termId]);

  useEffect(() => { loadRisks(); }, [loadRisks]);

  async function runPreview() {
    if (!armId) return;
    setBusy("preview"); setNotice(null);
    try {
      const p = await api<Preview>("/api/promotion/preview", {
        method: "POST",
        body: JSON.stringify({ from_arm_id: armId, repeat_student_ids: repeats }),
      });
      setPreview(p);
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not preview." });
    } finally { setBusy(null); }
  }

  async function commitPromotion() {
    if (!preview) return;
    const what = preview.graduating_class
      ? `Graduate ${preview.graduated.length} student(s)? Their accounts will be deactivated (records are kept).`
      : `Promote ${preview.promoted.length} student(s) from ${preview.from} to ${preview.to}? ${preview.repeated.length} will repeat.`;
    if (!confirm(what)) return;

    setBusy("commit"); setNotice(null);
    try {
      const r = await api<Preview>("/api/promotion/run", {
        method: "POST",
        body: JSON.stringify({
          from_arm_id: armId, repeat_student_ids: repeats, commit: true,
        }),
      });
      setNotice({
        kind: "ok",
        text: r.graduating_class
          ? `${r.graduated.length} student(s) graduated.`
          : `${r.promoted.length} promoted to ${r.to}; ${r.repeated.length} repeating.`,
      });
      setPreview(null);
      setRepeats([]);
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Promotion failed." });
    } finally { setBusy(null); }
  }

  async function regenerateComments() {
    if (!armId || !termId) return;
    setBusy("ai"); setNotice(null);
    try {
      const r = await api<{ ai_written: number; rules_written: number; kept_human_edits: number }>(
        "/api/ai/comments/regenerate", {
          method: "POST",
          body: JSON.stringify({ arm_id: armId, term_id: termId, keep_edited: true }),
        });
      const bits = [];
      if (r.ai_written) bits.push(`${r.ai_written} written by AI`);
      if (r.rules_written) bits.push(`${r.rules_written} written by the built-in engine`);
      if (r.kept_human_edits) bits.push(`${r.kept_human_edits} teacher edits kept untouched`);
      setNotice({ kind: "ok", text: bits.join(" · ") + "." });
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not regenerate." });
    } finally { setBusy(null); }
  }

  const toggleRepeat = (id: string) =>
    setRepeats((p) => p.includes(id) ? p.filter((x) => x !== id) : [...p, id]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">End of term</h1>
        <p className="text-sm text-ink-soft mt-1">
          Students who need attention, report-card comments, and end-of-session promotion.
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="block text-xs font-medium text-ink-soft mb-1">Term</span>
          <select value={termId} onChange={(e) => setTermId(e.target.value)}
                  className="rounded-md border border-line bg-white px-3 py-2 text-sm">
            {terms.map((t) => (
              <option key={t.id} value={t.id}>{t.name} term · {t.session}</option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="block text-xs font-medium text-ink-soft mb-1">Class</span>
          <select value={armId} onChange={(e) => { setArmId(e.target.value); setPreview(null); }}
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

      {/* at-risk register */}
      <section className="space-y-2">
        <div>
          <h2 className="text-lg font-semibold">Students needing attention</h2>
          <p className="text-xs text-ink-soft">
            Flagged from marks, attendance and fees. Every flag lists its reasons —
            no black box.
          </p>
        </div>

        {risks === null && <p className="text-sm text-ink-soft">Checking…</p>}
        {risks?.length === 0 && (
          <p className="text-sm text-ledger">
            No students flagged this term.
          </p>
        )}
        {risks && risks.length > 0 && (
          <div className="space-y-2">
            {risks.map((r) => (
              <div key={r.student_id}
                   className={`rounded-lg border p-3 ${LEVEL_STYLE[r.level]}`}>
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-medium">
                    {r.name}
                    <span className="ml-2 text-xs font-normal opacity-70">
                      {r.admission_number} · {r.class_label}
                    </span>
                  </span>
                  <span className="text-xs font-semibold uppercase tracking-wide">
                    {r.level} risk
                  </span>
                </div>
                <ul className="mt-1.5 text-sm list-disc list-inside space-y-0.5">
                  {r.reasons.map((reason, i) => <li key={i}>{reason}</li>)}
                </ul>
                {r.recommended_action && (
                  <p className="mt-1.5 text-xs font-medium">
                    → {r.recommended_action}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* AI comments */}
      <section className="rounded-lg border border-line bg-card p-4 space-y-2">
        <h2 className="text-sm font-medium">Report-card comments</h2>
        <p className="text-xs text-ink-soft">{ai?.message}</p>
        <button onClick={regenerateComments} disabled={busy !== null || !armId || !termId}
                className="rounded-md border border-ink text-ink px-4 py-2 text-sm font-medium hover:bg-ink hover:text-white disabled:opacity-40">
          {busy === "ai" ? "Writing…" : "Regenerate comments for this class"}
        </button>
        <p className="text-xs text-ink-soft">
          Comments a teacher has edited are never overwritten.
        </p>
      </section>

      {/* promotion */}
      <section className="rounded-lg border border-line bg-card p-4 space-y-3">
        <div>
          <h2 className="text-sm font-medium">End-of-session promotion</h2>
          <p className="text-xs text-ink-soft">
            Move the class up. You will see exactly who is promoted, who repeats and
            who graduates <b>before</b> anything moves.
          </p>
        </div>

        <button onClick={runPreview} disabled={busy !== null || !armId}
                className="rounded-md border border-ink text-ink px-4 py-2 text-sm font-medium hover:bg-ink hover:text-white disabled:opacity-40">
          {busy === "preview" ? "Checking…" : "Preview promotion"}
        </button>

        {preview && (
          <div className="rounded-md border border-brass bg-brass/10 p-3 space-y-3">
            <p className="text-sm font-medium">
              {preview.graduating_class
                ? `${preview.from} is the final year — these students will graduate.`
                : `${preview.from} → ${preview.to}`}
            </p>

            {[
              { label: preview.graduating_class ? "Graduating" : "Promoted",
                rows: preview.graduating_class ? preview.graduated : preview.promoted },
              { label: "Repeating", rows: preview.repeated },
            ].map((group) => group.rows.length > 0 && (
              <div key={group.label}>
                <p className="text-xs font-medium text-ink-soft mb-1">
                  {group.label} ({group.rows.length})
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {group.rows.map((s) => (
                    <label key={s.student_id}
                           className="inline-flex items-center gap-1.5 rounded-full border border-line bg-white px-3 py-1 text-xs cursor-pointer">
                      <input type="checkbox"
                             checked={repeats.includes(s.student_id)}
                             onChange={() => { toggleRepeat(s.student_id); setPreview(null); }}
                             className="h-3 w-3" />
                      {s.name}
                    </label>
                  ))}
                </div>
              </div>
            ))}

            <p className="text-xs text-ink-soft">
              Tick a student to make them repeat instead. Then preview again.
            </p>

            <button onClick={commitPromotion} disabled={busy !== null}
                    className="rounded-md bg-ink text-white px-5 py-2.5 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
              {busy === "commit"
                ? "Working…"
                : preview.graduating_class ? "Graduate these students" : "Promote the class"}
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
