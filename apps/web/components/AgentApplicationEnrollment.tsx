"use client";

import Link from "next/link";
import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import { SIGN_IN_PATH } from "@/lib/activityFeedback";
import { sendJson } from "@/lib/apiErrors";
import {
  AgentApplicationDetail,
  APPLICATIONS_URL,
  canConfirmEnrollment,
  ENROLLMENT_CHECK_TEXT,
  SECTION_EXPIRED as EXPIRED,
  SECTION_SERVER_ERROR as SERVER_ERROR,
} from "@/lib/agentApplications";
import { fieldErrors } from "@/lib/agentStudents";
import { formatDateTimeIn, viewerTimeZone } from "@/lib/formatDate";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Props = {
  detail: AgentApplicationDetail;
  isMaster: boolean;
  onSaved: (d: AgentApplicationDetail, message: string) => void;
  onFailed: (message: string, status?: number) => void;
  onOpenChange?: (open: boolean) => void;
};

// Browser QA pass 2: the form words its own failures, keeping the entry (QA13-03 the AGN-006 QA6-02 wording, QA13-08 the "on our side"
// wording; both now in lib/agentApplications.ts, shared with the Visa section); a 409/404 goes to the detail, which reloads.
const FIELDS = ["enrollment_date", "university_student_id", "notes"] as const;
type Field = (typeof FIELDS)[number];
const FIELD_ID: Record<Field, string> = { enrollment_date: "date", university_student_id: "student", notes: "notes" };

// AGN-013 (DEC-SCOPE-054): Step 9. A Master confirms enrollment from an offer onwards, after an explicit confirmation (it estimates a
// commission and ends withdrawal); once enrolled, a Master corrects the date and student ID. Staff read. The server decides; the
// displayed status travels as `expected_status`, so a stale screen gets a 409 and the detail reloads.
export default function AgentApplicationEnrollment({ detail, isMaster, onSaved, onFailed, onOpenChange }: Props) {
  const enrolled = detail.status === "enrolled";
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(detail.enrollment_date ?? "");
  const [studentId, setStudentId] = useState(detail.university_student_id ?? "");
  const [notes, setNotes] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ text: string; expired?: boolean } | null>(null);
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const inFlight = useRef(false); // a same-tick second click sends nothing
  const focusAfter = useFocusAfterRender();
  const id = (part: string) => `enrollment-${part}-${detail.id}`;

  if (!enrolled && (!canConfirmEnrollment(detail.status) || detail.read_only_reason)) return null;

  function show(next: boolean) {
    setOpen(next);
    onOpenChange?.(next); // QA13-06: the detail hides its other status actions while this form is open
  }
  async function save() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    setErrors({});
    const body = { enrollment_date: date, university_student_id: studentId.trim() || null, expected_status: detail.status, ...(enrolled ? {} : { notes: notes.trim() || null }) };
    const outcome = await sendJson(`${APPLICATIONS_URL}/${detail.id}/enrollment`, "PUT", body); // never throws: failures come back as an outcome
    inFlight.current = false;
    setBusy(false);
    setConfirming(false);
    if (!outcome.ok) {
      if (outcome.status === 409 || outcome.status === 404) return onFailed(outcome.message, outcome.status);
      const onFields = outcome.status === 422 ? fieldErrors(outcome.detail, FIELDS) : null;
      if (onFields) {
        setErrors(onFields); // QA13-09: on the field, described by the message
        return focusAfter(id(FIELD_ID[FIELDS.find((f) => onFields[f])!]));
      }
      const status = outcome.status ?? 0;
      setFailure(status === 401 ? { text: EXPIRED, expired: true } : { text: status >= 500 ? SERVER_ERROR : outcome.message });
      return focusAfter(id("failure"));
    }
    const next = (outcome.data as { application?: AgentApplicationDetail }).application;
    if (!next) return onFailed("The change could not be confirmed. Reload to see the current status.");
    show(false);
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
  function start() {
    show(true);
    focusAfter(id("date")); // QA13-04: focus follows the form that opened
  }
  function cancel() {
    // QA13-05: Cancel discards the entry; reopening starts from what is stored.
    setDate(detail.enrollment_date ?? "");
    setStudentId(detail.university_student_id ?? "");
    setNotes("");
    setFailure(null);
    setErrors({});
    setConfirming(false);
    focusAfter(id("open"));
    show(false);
  }
  const invalid = (field: Field) =>
    errors[field] ? { "aria-invalid": true as const, "aria-describedby": id(`${FIELD_ID[field]}-error`) } : {};
  const fieldError = (field: Field) =>
    errors[field] && (
      <p id={id(`${FIELD_ID[field]}-error`)} className="form-error">
        {errors[field]}
      </p>
    );

  const canAct = isMaster && !detail.read_only_reason;
  return (
    <section aria-labelledby={id("heading")}>
      <h5 id={id("heading")}>Enrollment</h5>
      {enrolled && !open && (
        // QA13-01: the header badge is the final status and the fields above carry university, course and intake.
        // QA13-07: while editing, the inputs take the place of these values.
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
        <button id={id("open")} type="button" className="btn secondary small" onClick={start}>
          {!enrolled ? "Enroll student" : detail.enrollment_date ? "Edit enrollment details" : "Add enrollment details"}
        </button>
      )}
      {canAct && open && (
        <form className="form" aria-label="Enrollment" onSubmit={submit}>
          {!enrolled && (
            // What is being confirmed -- read-only here; changes go through Edit (DEC-SCOPE-054 E5).
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
            <input
              id={id("date")}
              type="date"
              required
              min="2000-01-01"
              max="2100-12-31"
              value={date}
              onChange={(event) => setDate(event.target.value)}
              {...invalid("enrollment_date")}
            />
            {fieldError("enrollment_date")}
          </div>
          <div className="field">
            <label htmlFor={id("student")}>University student ID (optional)</label>
            <input id={id("student")} maxLength={60} autoComplete="off" value={studentId} onChange={(event) => setStudentId(event.target.value)} {...invalid("university_student_id")} />
            {fieldError("university_student_id")}
          </div>
          {!enrolled && (
            <div className="field">
              <label htmlFor={id("notes")}>Note (optional)</label>
              <textarea id={id("notes")} maxLength={2000} value={notes} onChange={(event) => setNotes(event.target.value)} {...invalid("notes")} />
              {fieldError("notes")}
            </div>
          )}
          {failure && (
            <p id={id("failure")} tabIndex={-1} className="form-error" role="alert">
              {failure.text}
              {failure.expired && (
                <>
                  {" "}
                  <Link href={SIGN_IN_PATH} target="_blank" rel="noopener">
                    Sign in again
                  </Link>
                </>
              )}
            </p>
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
