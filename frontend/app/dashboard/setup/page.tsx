"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, downloadFile } from "@/lib/api";
import { useToast } from "@/components/Toast";

type Term = {
  id: string; name: string; session: string; is_current: boolean;
  start_date: string | null; end_date: string | null;
  next_term_begins: string | null;
};
type Arm = { id: string; label: string; class_id: string; class_name: string };
type Subject = { id: string; name: string; code: string | null };
type Component = { id: string; name: string; max_score: number; sequence: number };
type SchoolSettings = {
  name: string; address: string | null; state: string | null;
  primary_color: string; principal_name: string | null;
  withhold_results_on_debt: boolean;
  online_payments_enabled: boolean;
  has_logo: boolean; has_signature: boolean; has_stamp: boolean;
  logo_url: string | null;
};

export default function SetupPage() {
  const [terms, setTerms] = useState<Term[]>([]);
  const [arms, setArms] = useState<Arm[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [components, setComponents] = useState<Component[]>([]);
  const [school, setSchool] = useState<SchoolSettings | null>(null);
  const [integrations, setIntegrations] = useState<{
    sms: { live: boolean; message: string };
    online_payments: { live: boolean; message: string };
  } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [testPhone, setTestPhone] = useState("");
  const toast = useToast();

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
      const [t, a, s, c, sc] = await Promise.all([
        api<Term[]>("/api/academics/terms"),
        api<Arm[]>("/api/academics/arms"),
        api<Subject[]>("/api/academics/subjects"),
        api<Component[]>("/api/assessment-components"),
        api<SchoolSettings>("/api/schools/me"),
      ]);
      api<typeof integrations>("/api/notifications/status")
        .then(setIntegrations).catch(() => {});
      setTerms(t); setArms(a); setSubjects(s); setSchool(sc);
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

  async function removeSubject(id: string, name: string) {
    if (!confirm(
      `Remove ${name}?\n\nIt leaves the pick lists, its teacher assignments end, and its timetable lessons are removed. Past results and printed report cards keep the subject — history never changes.`
    )) return;
    setBusy(`sub-${id}`); setNotice(null);
    try {
      const r = await api<{ note: string; assignments_closed: number; lessons_removed: number }>(
        `/api/academics/subjects/${id}`, { method: "DELETE" });
      toast.ok(`${name} removed. ${r.note}`);
      await load();
    } catch (e) {
      toast.err(e instanceof ApiError ? e.message : "Could not remove the subject.");
    } finally { setBusy(null); }
  }

  async function sendTestSms() {
    setBusy("sms");
    try {
      const r = await api<{ ok: boolean; status: string; provider: string; error: string | null; note: string; sent_to: string; endpoint: string | null }>(
        "/api/notifications/test-sms", {
          method: "POST", body: JSON.stringify({ phone: testPhone.trim() }),
        });
      if (r.provider === "mock") {
        toast.info("SMS is in preview mode — nothing was delivered. Set TERMII_API_KEY to go live.");
      } else if (r.ok) {
        toast.ok(`Message sent to ${r.sent_to}. If it doesn't arrive shortly, your sender ID may still be pending approval.`);
      } else {
        toast.err(`Termii rejected the message (via ${r.endpoint ?? "?"}): ${r.error ?? "unknown error"}`);
      }
    } catch (e) {
      toast.err(e instanceof ApiError ? e.message : "Could not send the test SMS.");
    } finally { setBusy(null); }
  }

  async function exportSchoolData() {
    setBusy("export");
    try {
      await downloadFile("/api/export/school.xlsx", "fiyox-school-export.xlsx");
      toast.ok("Your export is downloading — one Excel file with all your school's records.");
    } catch (e) {
      toast.err(e instanceof ApiError ? e.message : "Could not build the export.");
    } finally { setBusy(null); }
  }

  async function uploadAsset(asset: "logo" | "signature" | "stamp", file: File) {
    setBusy(asset); setNotice(null);
    try {
      if (file.size > 300_000) {
        throw new ApiError(413, `That image is ${Math.round(file.size / 1024)} KB — please use one under 300 KB.`);
      }
      const fd = new FormData();
      fd.append("file", file);
      await api(`/api/schools/me/branding/${asset}`, { method: "POST", body: fd });
      setNotice({ kind: "ok", text: `${asset[0].toUpperCase()}${asset.slice(1)} uploaded — it will appear on every report card.` });
      await load();
    } catch (e) {
      // show what actually went wrong, not a generic message
      const detail = e instanceof ApiError
        ? `${e.message} (HTTP ${e.status})`
        : e instanceof Error
          ? e.message
          : "Unknown error";
      setNotice({ kind: "err", text: `Could not upload the ${asset}: ${detail}` });
    } finally { setBusy(null); }
  }

  async function savePrincipal(name: string) {
    setBusy("principal"); setNotice(null);
    try {
      await api("/api/schools/me", {
        method: "PATCH", body: JSON.stringify({ principal_name: name }),
      });
      setNotice({ kind: "ok", text: "Principal's name saved." });
      await load();
    } catch { setNotice({ kind: "err", text: "Could not save the name." }); }
    finally { setBusy(null); }
  }

  async function saveTermDates(termId: string, field: string, value: string) {
    setBusy(`t-${termId}`); setNotice(null);
    try {
      await api(`/api/academics/terms/${termId}`, {
        method: "PATCH", body: JSON.stringify({ [field]: value }),
      });
      setNotice({
        kind: "ok",
        text: field === "next_term_begins"
          ? "Resumption date saved — it now prints on every report card."
          : "Term dates saved.",
      });
      await load();
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not save the date." });
    } finally { setBusy(null); }
  }

  async function toggleOnlinePayments(next: boolean) {
    setBusy("onlinepay"); setNotice(null);
    try {
      await api("/api/schools/me", {
        method: "PATCH", body: JSON.stringify({ online_payments_enabled: next }),
      });
      toast.ok(next
        ? "Online payments switched ON — parents now see a Pay online button."
        : "Online payments switched OFF — parents are asked to pay at the bursary.");
      await load();
    } catch (e) {
      toast.err(e instanceof ApiError ? e.message : "Could not change the setting.");
    } finally { setBusy(null); }
  }

  async function toggleWithhold(next: boolean) {
    setBusy("withhold"); setNotice(null);
    try {
      await api("/api/schools/me", {
        method: "PATCH",
        body: JSON.stringify({ withhold_results_on_debt: next }),
      });
      setNotice({
        kind: "ok",
        text: next
          ? "Results are now withheld from parents who owe fees for the term."
          : "Withholding is off — parents can see published results regardless of fees.",
      });
      await load();
    } catch (e) {
      setNotice({ kind: "err", text: e instanceof ApiError ? e.message : "Could not save the policy." });
    } finally { setBusy(null); }
  }

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

  async function closeArm(armId: string, label: string) {
    setBusy(`arm-${armId}`); setNotice(null);
    try {
      await api(`/api/academics/arms/${armId}`, { method: "DELETE" });
      setNotice({ kind: "ok", text: `${label} closed.` });
      await load();
    } catch (e) {
      setNotice({
        kind: "err",
        text: e instanceof ApiError
          ? e.message      // e.g. "3 student(s) are still in this arm. Move them first."
          : "Could not close the arm.",
      });
    } finally { setBusy(null); }
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

      {/* integrations */}
      {integrations && (
        <section className="rounded-lg border border-line bg-card p-4">
          <p className="text-sm font-medium mb-2">Integrations</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {[
              {
                label: "Online payments (Paystack)",
                live: Boolean(integrations.online_payments.live && school?.online_payments_enabled),
                message: !integrations.online_payments.live
                  ? integrations.online_payments.message
                  : school?.online_payments_enabled
                    ? "Parents can pay online with Paystack."
                    : "The payment gateway is configured, but online payment is switched OFF for this school — parents are asked to pay at the bursary.",
              },
              { label: "SMS to parents (Termii)", ...integrations.sms },
            ].map((i) => (
              <div key={i.label} className="rounded-md border border-line bg-paper p-3">
                <div className="flex items-center gap-2">
                  <span className={`inline-block h-2 w-2 rounded-full ${
                    i.live ? "bg-ledger" : "bg-ink-soft"}`} />
                  <span className="text-xs font-medium">{i.label}</span>
                  <span className={`text-xs ${i.live ? "text-ledger" : "text-ink-soft"}`}>
                    {i.live ? "live" : "off"}
                  </span>
                </div>
                <p className="text-xs text-ink-soft mt-1">{i.message}</p>
              </div>
            ))}
          </div>

          {/* the school decides whether parents may pay online */}
          <div className="mt-3 flex items-start gap-3 rounded-md border border-line bg-paper p-3">
            <input type="checkbox" id="onlinepay"
                   checked={school?.online_payments_enabled ?? false}
                   disabled={busy !== null}
                   onChange={(e) => toggleOnlinePayments(e.target.checked)}
                   className="mt-0.5 h-4 w-4" />
            <label htmlFor="onlinepay" className="text-xs">
              <span className="font-medium block text-sm">Allow parents to pay online</span>
              <span className="text-ink-soft">
                Off by default. Leave it off until the school is ready for online
                collections — parents then see no Pay online button at all.
              </span>
            </label>
          </div>

          {/* verify SMS actually works, before term-time */}
          <div className="mt-3 rounded-md border border-line bg-paper p-3">
            <p className="text-xs font-medium mb-1.5">Test SMS delivery</p>
            <p className="text-xs text-ink-soft mb-2">
              Send one real message to your own phone to confirm SMS is working.
              Nigerian format (0803…) is fine — it&apos;s converted automatically.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <input value={testPhone} onChange={(e) => setTestPhone(e.target.value)}
                     placeholder="08031234567" inputMode="tel"
                     className="rounded border border-line px-2 py-1.5 text-sm w-44" />
              <button onClick={sendTestSms} disabled={busy !== null || !testPhone.trim()}
                      className="rounded-md border border-ink text-ink px-3 py-1.5 text-sm font-medium hover:bg-ink hover:text-white disabled:opacity-40">
                {busy === "sms" ? "Sending…" : "Send test"}
              </button>
            </div>
          </div>
        </section>
      )}

      {/* the school's data belongs to the school */}
      <section className="rounded-lg border border-line bg-card p-4 space-y-2">
        <p className="text-sm font-medium">Your data</p>
        <p className="text-xs text-ink-soft">
          Download everything — students, guardians, staff, results, subject
          scores, invoices, payments and attendance — as one Excel workbook.
          Your school&apos;s records belong to your school, and you can take them
          with you at any time.
        </p>
        <button onClick={exportSchoolData} disabled={busy !== null}
                className="rounded-md border border-ink text-ink px-4 py-2 text-sm font-medium hover:bg-ink hover:text-white disabled:opacity-40">
          {busy === "export" ? "Preparing…" : "Download full export (.xlsx)"}
        </button>
      </section>

      {/* branding */}
      {school && (
        <section className="rounded-lg border border-line bg-card p-4 space-y-3">
          <div>
            <p className="text-sm font-medium">Report card branding</p>
            <p className="text-xs text-ink-soft">
              The crest, the principal&apos;s signature and the school stamp are
              printed on every report card. PNG or JPEG, under 300 KB.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {([
              { key: "logo" as const, label: "School crest / logo", has: school.has_logo },
              { key: "signature" as const, label: "Principal's signature", has: school.has_signature },
              { key: "stamp" as const, label: "School stamp", has: school.has_stamp },
            ]).map((a) => (
              <div key={a.key} className="rounded-md border border-line bg-paper p-3">
                <p className="text-xs font-medium mb-1">{a.label}</p>
                <p className={`text-xs mb-2 ${a.has ? "text-ledger" : "text-ink-soft"}`}>
                  {a.has ? "Uploaded ✓" : "Not set"}
                </p>
                <input
                  type="file"
                  accept="image/png,image/jpeg"
                  disabled={busy !== null}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) uploadAsset(a.key, f);
                    e.target.value = "";
                  }}
                  className="block w-full text-xs file:mr-2 file:rounded file:border-0 file:bg-ink file:px-2 file:py-1 file:text-white file:text-xs"
                />
                {busy === a.key && <p className="text-xs text-ink-soft mt-1">Uploading…</p>}
              </div>
            ))}
          </div>

          <div className="flex flex-wrap items-end gap-2">
            <label className="block">
              <span className="block text-xs text-ink-soft mb-1">Principal&apos;s name (printed under the signature)</span>
              <input
                defaultValue={school.principal_name ?? ""}
                placeholder="Rev. J. A. Danjuma"
                onBlur={(e) => {
                  const v = e.target.value.trim();
                  if (v && v !== (school.principal_name ?? "")) savePrincipal(v);
                }}
                className="w-64 rounded border border-line px-2 py-1.5 text-sm"
              />
            </label>
            <span className="text-xs text-ink-soft pb-2">Saves when you click away.</span>
          </div>
        </section>
      )}

      {/* policies */}
      {school && (
        <section className="rounded-lg border border-line bg-card p-4">
          <p className="text-sm font-medium mb-2">Policies</p>
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={school.withhold_results_on_debt}
              disabled={busy !== null}
              onChange={(e) => toggleWithhold(e.target.checked)}
              className="mt-0.5 h-4 w-4 accent-[color:var(--ink,#0B2239)]"
            />
            <span className="text-sm">
              Withhold results from fee debtors
              <span className="block text-xs text-ink-soft mt-0.5">
                When on, a parent or student with an outstanding balance for the term
                cannot view or download the report card — they see a withheld notice
                instead. Staff are never blocked, and the result unlocks the moment the
                bursar records payment.
              </span>
            </span>
          </label>
          {school.withhold_results_on_debt && (
            <p className="mt-2 text-xs text-brass-ink bg-brass/15 rounded px-2 py-1 inline-block">
              Currently withholding results from debtors.
            </p>
          )}
        </section>
      )}

      {/* current structure */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="rounded-lg border border-line bg-card p-4">
          <p className="text-sm font-medium mb-2">Terms</p>
          {terms.length === 0 ? (
            <p className="text-sm text-ink-soft">None yet.</p>
          ) : (
            <ul className="text-sm space-y-3">
              {terms.map((t) => (
                <li key={t.id} className="space-y-1.5">
                  <div>
                    {t.name} term · {t.session}{" "}
                    {t.is_current && (
                      <span className="rounded-full bg-ledger/10 text-ledger px-2 py-0.5 text-xs font-medium">
                        current
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap items-end gap-3">
                    {([
                      { key: "start_date", label: "Term starts", value: t.start_date },
                      { key: "end_date", label: "Term ends", value: t.end_date },
                      { key: "next_term_begins", label: "Next term begins", value: t.next_term_begins },
                    ]).map((f) => (
                      <label key={f.key} className="block">
                        <span className="block text-xs text-ink-soft mb-0.5">
                          {f.label}
                          {f.key === "next_term_begins" && (
                            <span className="text-brass-ink"> (on report card)</span>
                          )}
                        </span>
                        <input
                          type="date"
                          defaultValue={f.value ?? ""}
                          disabled={busy !== null}
                          onChange={(e) => {
                            if (e.target.value) saveTermDates(t.id, f.key, e.target.value);
                          }}
                          className="rounded border border-line px-2 py-1 text-sm bg-white"
                        />
                      </label>
                    ))}
                  </div>
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
            <>
              <div className="flex flex-wrap gap-1.5">
                {arms.map((a) => (
                  <span key={a.id}
                        className="inline-flex items-center gap-1.5 rounded-full border border-line bg-paper px-3 py-1 text-xs">
                    {a.label}
                    <button
                      onClick={() => {
                        if (confirm(`Close ${a.label}? This is refused if students are still in it.`))
                          closeArm(a.id, a.label);
                      }}
                      disabled={busy !== null}
                      aria-label={`Close ${a.label}`}
                      className="text-ink-soft hover:text-sanction disabled:opacity-40"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
              <p className="text-xs text-ink-soft">
                Closing an arm is refused while students are in it — move them to
                another arm first, so results and invoices are never orphaned.
              </p>
            </>
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
                      className="inline-flex items-center gap-1.5 rounded-full border border-line bg-paper px-3 py-1 text-xs">
                  {s.name}{s.code ? ` (${s.code})` : ""}
                  <button onClick={() => removeSubject(s.id, s.name)} disabled={busy !== null}
                          aria-label={`Remove ${s.name}`}
                          className="text-ink-soft hover:text-sanction disabled:opacity-40">
                    ×
                  </button>
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
