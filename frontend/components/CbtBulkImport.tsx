"use client";

import { useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";

type Opt = { id: string; text: string };
type Item = {
  text: string; type: string; options: Opt[]; correct: unknown;
  difficulty: string; topic: string; marks: number; issues: string[];
  include: boolean;
};

const DIFFS = ["easy", "medium", "hard"] as const;

// a live re-check so the badge updates as the teacher fixes a question
function liveIssues(it: Item): string[] {
  const p: string[] = [];
  if (!it.text.trim()) p.push("Missing question text");
  if (it.type === "single" || it.type === "multiple") {
    if (it.options.filter((o) => o.text.trim()).length < 2) p.push("Needs at least two options");
    const ok = it.type === "single"
      ? typeof it.correct === "string" && it.correct
      : Array.isArray(it.correct) && it.correct.length > 0;
    if (!ok) p.push("Choose the correct answer");
  }
  if (it.type === "boolean" && typeof it.correct !== "boolean") p.push("Choose True or False");
  if (it.type === "short" && (!Array.isArray(it.correct) || (it.correct as string[]).join("").trim() === ""))
    p.push("Add an accepted answer");
  return p;
}

export default function CbtBulkImport({ subjectId, onImported, onClose }:
  { subjectId: string; onImported: () => void; onClose: () => void }) {
  const { ok, err } = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<Item[] | null>(null);
  const [busy, setBusy] = useState(false);

  const field = "w-full rounded-md border border-line bg-white px-3 py-2 text-sm";

  async function upload() {
    const f = fileRef.current?.files?.[0];
    if (!f) return err("Choose a Word (.docx) or PDF file first");
    const form = new FormData();
    form.append("file", f);
    setBusy(true);
    try {
      const r = await api<{ questions: Omit<Item, "include">[] }>(
        "/api/cbt/bank/parse", { method: "POST", body: form });
      setItems(r.questions.map((q) => ({ ...q, include: q.issues.length === 0 })));
    } catch (e) { err(e instanceof ApiError ? e.message : "Could not read that file"); }
    finally { setBusy(false); }
  }

  function patch(i: number, f: Partial<Item>) {
    setItems((prev) => prev ? prev.map((it, j) => j === i ? { ...it, ...f } : it) : prev);
  }

  async function doImport() {
    if (!items) return;
    const chosen = items.filter((it) => it.include).map((it) => ({
      text: it.text.trim(), type: it.type,
      options: (it.type === "single" || it.type === "multiple")
        ? it.options.filter((o) => o.text.trim()) : [],
      correct: it.correct, difficulty: it.difficulty, topic: it.topic, marks: it.marks,
    }));
    if (!chosen.length) return err("Tick at least one question to import");
    setBusy(true);
    try {
      const r = await api<{ created: number; skipped: number }>("/api/cbt/bank/import", {
        method: "POST",
        body: JSON.stringify({ subject_id: subjectId, questions: chosen }) });
      ok(`Imported ${r.created}${r.skipped ? `, skipped ${r.skipped}` : ""}`);
      setItems(null);
      if (fileRef.current) fileRef.current.value = "";
      onImported();
      onClose();
    } catch (e) { err(e instanceof ApiError ? e.message : "Import failed"); }
    finally { setBusy(false); }
  }

  const includable = items?.filter((it) => it.include).length ?? 0;

  return (
    <div className="bg-card border border-ink rounded-xl p-5 space-y-4 card">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">Import from a document</p>
        <button onClick={onClose} className="text-xs text-ink-soft hover:text-ink underline underline-offset-2">Close</button>
      </div>

      <p className="text-xs text-ink-soft">
        Upload a Word (.docx) or PDF with numbered questions, A) B) C) options and
        an “Answer:” line. You can review and fix everything before saving.
      </p>

      <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
        <input ref={fileRef} type="file" accept=".docx,.pdf"
               className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-ink file:text-white file:px-3 file:py-1.5 file:text-sm" />
        <button onClick={upload} disabled={busy}
                className="rounded-md border border-ink text-ink px-4 py-2 text-sm font-medium hover:bg-ink hover:text-white disabled:opacity-50">
          {busy && !items ? "Reading…" : "Upload & preview"}
        </button>
      </div>

      {items && (
        <div className="space-y-3 pt-1">
          <p className="text-sm">
            Found <b>{items.length}</b> question{items.length === 1 ? "" : "s"}.
            Review, fix any flagged, then import.
          </p>

          {items.map((it, i) => {
            const probs = liveIssues(it);
            return (
              <div key={i} className={`rounded-lg border p-3 space-y-2 ${probs.length ? "border-sanction/40 bg-sanction/5" : "border-line"}`}>
                <div className="flex items-start gap-2">
                  <input type="checkbox" className="mt-1" checked={it.include}
                         onChange={(e) => patch(i, { include: e.target.checked })} />
                  <div className="flex-1 min-w-0 space-y-2">
                    <textarea className={`${field} min-h-[48px]`} value={it.text}
                              onChange={(e) => patch(i, { text: e.target.value })} />
                    <div className="flex flex-wrap gap-2">
                      <select className="rounded-md border border-line bg-white px-2 py-1 text-xs capitalize"
                              value={it.difficulty} onChange={(e) => patch(i, { difficulty: e.target.value })}>
                        {DIFFS.map((d) => <option key={d} value={d}>{d}</option>)}
                      </select>
                      <span className="text-xs text-ink-soft self-center">{it.type}</span>
                    </div>

                    {(it.type === "single" || it.type === "multiple") && it.options.map((o, oi) => (
                      <div key={o.id} className="flex items-center gap-2">
                        <input type={it.type === "single" ? "radio" : "checkbox"} name={`c${i}`}
                               checked={it.type === "single" ? it.correct === o.id
                                 : Array.isArray(it.correct) && (it.correct as string[]).includes(o.id)}
                               onChange={() => it.type === "single"
                                 ? patch(i, { correct: o.id })
                                 : patch(i, { correct: Array.isArray(it.correct) && (it.correct as string[]).includes(o.id)
                                     ? (it.correct as string[]).filter((x) => x !== o.id)
                                     : [...((it.correct as string[]) || []), o.id] })} />
                        <input className={field} value={o.text}
                               onChange={(e) => patch(i, { options: it.options.map((x, j) => j === oi ? { ...x, text: e.target.value } : x) })} />
                      </div>
                    ))}

                    {it.type === "boolean" && (
                      <div className="flex gap-4 text-sm">
                        {[["True", true], ["False", false]].map(([l, v]) => (
                          <label key={l as string} className="flex items-center gap-1.5">
                            <input type="radio" name={`b${i}`} checked={it.correct === v}
                                   onChange={() => patch(i, { correct: v })} />
                            {l as string}
                          </label>
                        ))}
                      </div>
                    )}

                    {it.type === "short" && (
                      <input className={field} placeholder="Accepted answers, comma-separated"
                             value={Array.isArray(it.correct) ? (it.correct as string[]).join(", ") : ""}
                             onChange={(e) => patch(i, { correct: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} />
                    )}

                    {probs.length > 0 && (
                      <p className="text-xs text-sanction">⚠ {probs.join(" · ")}</p>
                    )}
                  </div>
                </div>
              </div>
            );
          })}

          <div className="flex items-center justify-between pt-1">
            <p className="text-xs text-ink-soft">{includable} selected</p>
            <button onClick={doImport} disabled={busy || includable === 0}
                    className="rounded-md bg-ink text-white px-5 py-2 text-sm font-medium hover:bg-ink-soft disabled:opacity-50">
              {busy ? "Importing…" : `Import ${includable}`}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
