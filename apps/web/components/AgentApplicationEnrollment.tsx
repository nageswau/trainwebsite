"use client";

import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import { sendJson } from "@/lib/apiErrors";
import { AgentApplicationDetail, APPLICATIONS_URL, canConfirmEnrollment, ENROLLMENT_CHECK_TEXT } from "@/lib/agentApplications";
import { formatDateTimeIn, viewerTimeZone } from "@/lib/formatDate";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Props = {
  detail: AgentApplicationDetail;
  isMaster: boolean;
  onSaved: (d: AgentApplicationDetail, message: string) => void;
  onFailed: (message: string, status?: number) => void;
};

// AGN-013 (DEC-SCOPE-052): Step 9. A Master confirms enrollment from an offer onwards, after an explicit confirmation (it estimates a
// commission and ends withdrawal); once enrolled, a Master corrects the date and student ID. Staff read. The server decides; the
// displayed status travels as `expected_status`, so a stale screen gets a 409 and the detail reloads.
export default function AgentApplicationEnrollment({ detail, isMaster, onSaved, onFailed }: Props) {
  const enrolled = detail.status === "enrolled";
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(detail.enrollment_date ?? "");
  const [studentId, setStudentId] = useState(detail.university_student_id ?? "");
  const [notes, setNotes] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // a same-tick second click sends nothing
  const focusAfter = useFocusAfterRender();
  const id = (part: string) => `enrollment-${part}-${detail.id}`;

  if (!enrolled && (!canConfirmEnrollment(detail.status) || detail.read_only_reason)) return null;

  async function save() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    let outcome: Awaited<ReturnType<typeof sendJson>>;
    try {
      const body = { enrollment_date: date, university_student_id: studentId.trim() || null, expected_status: detail.status, ...(enrolled ? {} : { notes: notes.trim() || null }) };
      outcome = await sendJson(`${APPLICATIONS_URL}/${detail.id}/enrollment`, "PUT", body);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
    setConfirming(false);
    if (!outcome.ok) return onFailed(outcome.message, outcome.status);
    const next = (outcome.data as { application?: AgentApplicationDetail }).application;
    if (!next) return onFailed("The change could not be confirmed. Reload to see the current status.");
    setOpen(false);
    onSaved(next, enrolled ? "Enrollment details saved." : "Enrollment confirmed.");
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (enrolled) save();
    else setConfirming(true);
  }
  function back() {
    focusAfter(id("submit"));
    setConfirming(false);
  }
  function cancel() {
    focusAfter(id("open"));
    setOpen(false);
  }

  const canAct = isMaster && !detail.read_only_reason;
  return (
    <section aria-labelledby={id("heading")}>
      <h5 id={id("heading")}>Enrollment</h5>
      {enrolled && (
        // QA13-01: the header badge is the final status and the fields above carry university, course and intake.
        <dl className="card-stack">
          <dt>Enrollment date</dt>
          <dd>{detail.enrollment_date ?? "Not recorded"}</dd>
          <dt>University student ID</dt>
          <dd>{detail.university_student_id ?? "Not recorded"}</dd>
          <dt>Confirmed by the agency</dt>
          <dd>{detail.enrollment_confirmed_at ? formatDateTimeIn(detail.enrollment_confirmed_at, viewerTimeZone(), true) : "—"}</dd>
        </dl>
      )}
      {detail.enrollment_check && <p className="form-warning">{ENROLLMENT_CHECK_TEXT[detail.enrollment_check]}</p>}
      {!enrolled && !isMaster && <p className="muted">An agency Master confirms enrollment.</p>}
      {canAct && !open && (
        <button id={id("open")} type="button" className="btn secondary small" onClick={() => setOpen(true)}>
          {!enrolled ? "Enroll student" : detail.enrollment_date ? "Edit enrollment details" : "Add enrollment details"}
        </button>
      )}
      {canAct && open && (
        <form className="form" aria-label="Enrollment" onSubmit={submit}>
          {!enrolled && (
            // What is being confirmed -- read-only here; changes go through Edit (DEC-SCOPE-052 E5).
            <dl className="card-stack">
              <dt>University</dt>
              <dd>{detail.university}</dd>
              <dt>Course</dt>
              <dd>{detail.course ?? "Undecided"}</dd>
              <dt>Intake</dt>
              <dd>{detail.intake}</dd>
            </dl>
          )}
          <div className="field">
            <label htmlFor={id("date")}>Enrollment date (required)</label>
            <input id={id("date")} type="date" required min="2000-01-01" max="2100-12-31" value={date} onChange={(event) => setDate(event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor={id("student")}>University student ID (optional)</label>
            <input id={id("student")} maxLength={60} autoComplete="off" value={studentId} onChange={(event) => setStudentId(event.target.value)} />
          </div>
          {!enrolled && (
            <div className="field">
              <label htmlFor={id("notes")}>Note (optional)</label>
              <textarea id={id("notes")} maxLength={2000} value={notes} onChange={(event) => setNotes(event.target.value)} />
            </div>
          )}
          {confirming ? (
            <div role="group" aria-label="Confirm enrollment" onKeyDown={(event: KeyboardEvent) => event.key === "Escape" && back()}>
              <p>Confirm enrollment? A commission will be estimated and the application can no longer be withdrawn.</p>
              <div className="actions">
                <button type="button" className="btn small" disabled={busy} onClick={save} autoFocus>
                  {busy ? "Saving…" : "Yes, confirm enrollment"}
                </button>
                <button type="button" className="btn ghost small" onClick={back}>
                  Go back
                </button>
              </div>
            </div>
          ) : (
            <div className="actions">
              <button id={id("submit")} className="btn small" disabled={busy || !date}>
                {busy ? "Saving…" : enrolled ? "Save enrollment details" : "Confirm enrollment"}
              </button>
              <button type="button" className="btn ghost small" onClick={cancel}>
                Cancel
              </button>
            </div>
          )}
        </form>
      )}
    </section>
  );
}
