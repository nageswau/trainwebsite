"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import PsychometricResultsForm from "@/components/PsychometricResultsForm";
import { sendJson } from "@/lib/apiErrors";
import { hasResults, type PsychometricResult } from "@/lib/psychometric";

type Student = { id: string; full_name: string; school_name: string };
type Record_ = { id: string; school_student_id: string; assessment_type: string; report_url: string | null; status: string; created_at: string } & PsychometricResult;

// SCH-005: Psychometric Team assigns an assessment, then uploads a report against it --
// visible to readers immediately, no Draft/Published gate for this content.
export default function SchoolPsychometricRecordsPanel({ records, students }: { records: Record_[]; students: Student[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  // ENH-022: which form the message belongs to, so it renders beside that form.
  const [message, setMessage] = useState<(FormMessageState & { form: "assign" | "attach" }) | null>(null);
  // ENH-027: one action card at a time -- the attach card or the results editor.
  const [open, setOpen] = useState<{ kind: "attach" | "results"; id: string } | null>(null);
  const uploadingId = open?.kind === "attach" ? open.id : null;
  const resultsRecord = open?.kind === "results" ? records.find((r) => r.id === open.id) ?? null : null;
  const triggers = useRef<Record<string, HTMLButtonElement | null>>({});
  const [returnFocusTo, setReturnFocusTo] = useState<string | null>(null);

  useEffect(() => {
    if (!returnFocusTo) return;
    triggers.current[returnFocusTo]?.focus();
    setReturnFocusTo(null);
  }, [returnFocusTo]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setBusy(true);
    setMessage(null);
    const form = new FormData(formElement);
    const result = await sendJson("/api/v1/school/psychometric-team/records", "POST", { school_student_id: form.get("school_student_id"), assessment_type: form.get("assessment_type") });
    setBusy(false);
    if (!result.ok) {
      setMessage({ text: result.message, failed: true, form: "assign" });
      return;
    }
    setMessage({ text: "Assessment assigned.", failed: false, form: "assign" });
    formElement.reset();
    router.refresh();
  }

  async function attachReport(event: FormEvent<HTMLFormElement>, recordId: string) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    const result = await sendJson(`/api/v1/school/psychometric-team/records/${recordId}`, "PATCH", { report_url: form.get("report_url") });
    setBusy(false);
    if (!result.ok) {
      setMessage({ text: result.message, failed: true, form: "attach" });
      return;
    }
    // The attach card closes on success, so this confirmation shows under the assign form instead.
    setMessage({ text: "Report attached.", failed: false, form: "assign" });
    setOpen(null);
    router.refresh();
  }

  // QA-022-01: an attach message belongs to the card that produced it -- opening (for any record) or cancelling starts clean.
  function clearAttachMessage() {
    setMessage((current) => (current?.form === "attach" ? null : current));
  }

  // QA27-01: opening a card starts a new action, so an earlier success confirmation ("Results saved.", "Report attached.")
  // no longer describes what is on screen. A failed assign message stays: it still belongs to the assign form.
  function clearForNewAction() {
    setMessage((current) => (current && (current.form === "attach" || !current.failed) ? null : current));
  }

  function startAttach(recordId: string) {
    clearForNewAction();
    setOpen({ kind: "attach", id: recordId });
  }

  function stopAttach() {
    clearAttachMessage();
    setOpen(null);
  }

  function startResults(recordId: string) {
    clearForNewAction();
    setOpen({ kind: "results", id: recordId });
  }

  // ENH-027: closing the editor (saved or cancelled) returns focus to the row button that opened it.
  function finishResults(saved: boolean) {
    const recordId = open?.id ?? null;
    setOpen(null);
    if (saved) {
      setMessage({ text: "Results saved.", failed: false, form: "assign" });
      router.refresh();
    }
    setReturnFocusTo(recordId);
  }

  function studentName(id: string) {
    return students.find((s) => s.id === id)?.full_name || "Unknown student";
  }

  return (
    <div className="portal-content">
      <div className="card">
        <h2>Assessments</h2>
        {records.length === 0 ? (
          <p className="muted">No assessments assigned yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Student</th><th>Assessment</th><th>Status</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {records.map((r) => (
                  <tr key={r.id}>
                    <td>{studentName(r.school_student_id)}</td>
                    <td>{r.assessment_type}</td>
                    <td>{r.status}</td>
                    <td>
                      <div className="actions">
                        {r.status === "assigned" ? (
                          <button className="btn ghost small" onClick={() => startAttach(r.id)}>Attach report</button>
                        ) : (
                          <span className="muted" style={{ fontSize: 13 }}>Report attached</span>
                        )}
                        <button
                          ref={(el) => { triggers.current[r.id] = el; }}
                          className="btn ghost small"
                          aria-label={`${hasResults(r) ? "Edit" : "Record"} results for ${studentName(r.school_student_id)} — ${r.assessment_type}`}
                          onClick={() => startResults(r.id)}
                        >
                          {hasResults(r) ? "Edit results" : "Record results"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {uploadingId && (
        <div className="action-card">
          <h3>Attach report</h3>
          <form className="form" onSubmit={(e) => attachReport(e, uploadingId)}>
            <div className="field">
              <label htmlFor="report-url">Report URL</label>
              <input id="report-url" name="report_url" required placeholder="/local-files/uploads/report.pdf" />
            </div>
            <div className="field" style={{ flexDirection: "row", gap: 12 }}>
              <button className="btn" disabled={busy}>{busy ? "Saving…" : "Attach"}</button>
              <button type="button" className="btn secondary" onClick={stopAttach}>Cancel</button>
            </div>
          </form>
          {message?.form === "attach" && <FormMessage message={message} />}
        </div>
      )}

      {resultsRecord && (
        <PsychometricResultsForm key={resultsRecord.id} record={resultsRecord} studentName={studentName(resultsRecord.school_student_id)} onDone={finishResults} />
      )}

      <div className="action-card">
        <h3>Assign an assessment</h3>
        {students.length === 0 ? (
          <p className="muted">No students in your portfolio yet. Contact your Overseas Admin.</p>
        ) : (
          <form className="form" onSubmit={submit}>
            <div className="field">
              <label htmlFor="psych-student">Student</label>
              <select id="psych-student" name="school_student_id" required defaultValue="">
                <option value="" disabled>Select student</option>
                {students.map((s) => (
                  <option key={s.id} value={s.id}>{s.full_name} — {s.school_name}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="psych-type">Assessment type</label>
              <input id="psych-type" name="assessment_type" required placeholder="e.g. Aptitude Test" />
            </div>
            <button className="btn" disabled={busy}>{busy ? "Saving…" : "Assign assessment"}</button>
          </form>
        )}
        {message?.form === "assign" && <FormMessage message={message} />}
      </div>
    </div>
  );
}
