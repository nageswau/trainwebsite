"use client";

import { type ChangeEvent, type FormEvent, useEffect, useRef, useState } from "react";

import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { sendJson } from "@/lib/apiErrors";
import {
  changedFields, listError, LIST_ITEM_MAX, LIST_MAX_ITEMS, NOTES_MAX, REMARKS_MAX, RESULT_LIST_FIELDS, toDraft,
  type PsychometricResult, type ResultDraft, type ResultKey,
} from "@/lib/psychometric";

// ENH-027 -- record/edit one assessment's structured result (spec §5.3). Patterns reused from ActivityFeedbackForm (ENH-018):
// heading focus on open, beforeunload while dirty, counters, field-level aria-invalid. Lists are comma-separated like the
// ENH-025/026 forms. Only changed fields are sent, so two team members editing different fields never overwrite each other
// (spec §4.3). The API is the authority; the client checks are for usability only.

type Props = { record: PsychometricResult & { id: string; assessment_type: string }; studentName: string; onDone: (saved: boolean) => void };

const id = (key: ResultKey) => `psy-result-${key.replaceAll("_", "-")}`;
const LIST_HINT_ID = "psy-result-lists-hint";
const LEAVE_PROMPT = "Leave without saving your results?";

const DATE_KEYS: ResultKey[] = ["test_date", "parent_discussion_on", "follow_up_on"];
// Visual order, so focus lands on the first rejected field the user would meet.
const FORM_ORDER: ResultKey[] = ["test_date", ...RESULT_LIST_FIELDS.map((f) => f.key), "parent_discussion_on", "follow_up_on"];

// QA27-03/-04: this editor's own wording for a server failure and an ended session. Everything typed stays in the form,
// so say so; for 401, signing in again in a new tab restores the cookie for this tab too, and Save then works here.
// Every other status keeps the server's own message (e.g. the partnership-tier 403).
function failureText(status: number | undefined, serverMessage: string): string {
  if (status === 401) return "Your session has ended. Sign in again in a new tab, then press Save here — your entry is kept.";
  if (status !== undefined && status >= 500) return "Something went wrong on our side. Your entry is kept — try again in a moment.";
  return serverMessage;
}

export default function PsychometricResultsForm({ record, studentName, onDone }: Props) {
  const [initial] = useState<ResultDraft>(() => toDraft(record));
  const [draft, setDraft] = useState<ResultDraft>(initial);
  const [busy, setBusy] = useState(false);
  // `signIn`: the failure was an ended session, so the message gets a sign-in link (QA27-04).
  const [message, setMessage] = useState<(FormMessageState & { signIn?: boolean }) | null>(null);
  const [errors, setErrors] = useState<Partial<Record<ResultKey, string>>>({});
  const headingRef = useRef<HTMLHeadingElement>(null);
  const fieldRefs = useRef<Partial<Record<ResultKey, HTMLInputElement | null>>>({});
  const dirty = Object.keys(changedFields(initial, draft)).length > 0;

  useEffect(() => headingRef.current?.focus(), []);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    // QA27-02: beforeunload only covers reload/close. An in-app link (sidebar, 360° links) navigates client-side, so ask
    // first; capture phase runs before Next's Link handler, and "no" stops the click before it reaches the router.
    const guardLinks = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const link = (event.target as Element | null)?.closest?.("a[href]") as HTMLAnchorElement | null;
      if (!link || link.target === "_blank" || link.hasAttribute("download") || link.origin !== window.location.origin) return;
      if (!window.confirm(LEAVE_PROMPT)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", warn);
    document.addEventListener("click", guardLinks, true);
    return () => {
      window.removeEventListener("beforeunload", warn);
      document.removeEventListener("click", guardLinks, true);
    };
  }, [dirty]);

  const bind = (key: ResultKey) => ({
    id: id(key),
    name: key,
    value: draft[key],
    disabled: busy,
    onChange: (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setDraft((d) => ({ ...d, [key]: e.target.value })),
  });

  // aria-invalid + the error id for a field the last submit rejected; `describedBy` is the field's usual description.
  const invalid = (key: ResultKey, describedBy?: string) => ({
    ref: (el: HTMLInputElement | null) => { fieldRefs.current[key] = el; },
    "aria-invalid": errors[key] ? true : undefined,
    "aria-describedby": [describedBy, errors[key] ? `${id(key)}-error` : undefined].filter(Boolean).join(" ") || undefined,
  });
  const errorText = (key: ResultKey) => (errors[key] ? <p id={`${id(key)}-error`} className="form-error">{errors[key]}</p> : null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found: Partial<Record<ResultKey, string>> = {};
    for (const { key } of RESULT_LIST_FIELDS) {
      const error = listError(draft[key]);
      if (error) found[key] = error;
    }
    // A partly typed date input reports "" -- sending that would silently clear a stored date (final review).
    for (const key of DATE_KEYS) {
      if (fieldRefs.current[key]?.validity.badInput) found[key] = "Enter a complete date, or clear the field.";
    }
    setErrors(found);
    const first = FORM_ORDER.find((key) => found[key]);
    if (first) {
      setMessage(null); // QA27-01: an earlier "No changes to save." must not sit beside the new field error
      fieldRefs.current[first]?.focus();
      return;
    }
    const payload = changedFields(initial, draft);
    if (Object.keys(payload).length === 0) {
      setMessage({ text: "No changes to save.", failed: false });
      return;
    }
    setBusy(true);
    setMessage(null);
    const result = await sendJson(`/api/v1/school/psychometric-team/records/${record.id}`, "PATCH", payload);
    setBusy(false);
    if (!result.ok) {
      setMessage({ text: failureText(result.status, result.message), failed: true, signIn: result.status === 401 });
      return;
    }
    onDone(true);
  }

  return (
    <div className="action-card">
      <h3 ref={headingRef} tabIndex={-1}>Results — {studentName} · {record.assessment_type}</h3>
      <form className="form" onSubmit={submit} aria-busy={busy} noValidate>
        <fieldset className="question">
          <legend>Assessment</legend>
          <div className="field">
            <label htmlFor={id("test_date")}>Test date</label>
            <input type="date" {...bind("test_date")} {...invalid("test_date")} />
            {errorText("test_date")}
          </div>
        </fieldset>

        <fieldset className="question">
          <legend>Findings</legend>
          <p id={LIST_HINT_ID} className="muted">Separate items with commas (use / or ; inside an item) — up to {LIST_MAX_ITEMS} items of {LIST_ITEM_MAX} characters each.</p>
          {RESULT_LIST_FIELDS.map(({ key, label }) => (
            <div className="field" key={key}>
              <label htmlFor={id(key)}>{label}</label>
              <input {...bind(key)} {...invalid(key, LIST_HINT_ID)} />
              {errorText(key)}
            </div>
          ))}
        </fieldset>

        <fieldset className="question">
          <legend>Counselling &amp; follow-up</legend>
          <div className="field">
            <label htmlFor={id("counsellor_remarks")}>Counsellor remarks</label>
            <textarea {...bind("counsellor_remarks")} maxLength={REMARKS_MAX} aria-describedby={`${id("counsellor_remarks")}-count`} />
            <small id={`${id("counsellor_remarks")}-count`} className="muted">{draft.counsellor_remarks.length} / {REMARKS_MAX}</small>
          </div>
          <div className="form-grid">
            <div className="field">
              <label htmlFor={id("parent_discussion_on")}>Parent discussion date</label>
              <input type="date" {...bind("parent_discussion_on")} {...invalid("parent_discussion_on")} />
              {errorText("parent_discussion_on")}
            </div>
            <div className="field">
              <label htmlFor={id("follow_up_on")}>Follow-up date</label>
              <input type="date" {...bind("follow_up_on")} {...invalid("follow_up_on")} />
              {errorText("follow_up_on")}
            </div>
          </div>
          <div className="field">
            <label htmlFor={id("parent_discussion_notes")}>Parent discussion notes</label>
            <textarea {...bind("parent_discussion_notes")} maxLength={NOTES_MAX} aria-describedby={`${id("parent_discussion_notes")}-count`} />
            <small id={`${id("parent_discussion_notes")}-count`} className="muted">{draft.parent_discussion_notes.length} / {NOTES_MAX}</small>
          </div>
        </fieldset>

        <div className="actions">
          <button className="btn" disabled={busy}>{busy ? "Saving…" : "Save results"}</button>
          <button type="button" className="btn secondary" disabled={busy} onClick={() => onDone(false)}>Cancel</button>
        </div>
      </form>
      {message && <FormMessage message={message} />}
      {message?.signIn ? (
        <a href="/overseas/login" target="_blank" rel="noopener noreferrer">Sign in again (opens a new tab)</a>
      ) : null}
    </div>
  );
}
