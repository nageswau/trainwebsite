"use client";

import Link from "next/link";
import { FormEvent, useEffect, useId, useRef, useState } from "react";

import LocalDateTime from "@/components/LocalDateTime";
import { type ActivityFeedback, type FeedbackActivity, participationText, SCORE_LABELS, SESSION_EXPIRED, SIGN_IN_PATH, type UnsentText } from "@/lib/activityFeedback";
import { detailMessage, isRequestBody, NOT_COMPLETED } from "@/lib/apiErrors";

type Props = { activity: FeedbackActivity; onSubmitted: (feedback: ActivityFeedback) => void; onDuplicate: (unsent: UnsentText) => void; onCancel: () => void };
const DISCARD_PROMPT = "Discard your unsent feedback?";
type FieldName = "rating" | "satisfaction" | "trainer_name" | "feedback" | "suggestions";
type FormError = { text: string; expired?: boolean; fields?: FieldName[] };

const TEXT_MAX = 5000;
const FIELD_LABELS: Record<FieldName, string> = { rating: "Overall rating", satisfaction: "School satisfaction", trainer_name: "Trainer / Counsellor", feedback: "Feedback", suggestions: "Suggestions" };

/** A FastAPI 422 list, worded per field ("Suggestions: Must not ...") so the user knows which box to fix (QA-018-01). */
function fieldError(detail: unknown): FormError | null {
  if (!Array.isArray(detail)) return null;
  const fields: FieldName[] = [];
  const parts = detail.map((item: { loc?: unknown[] }) => {
    const field = item?.loc?.[1] as FieldName | undefined;
    const text = detailMessage([item]);
    if (field && field in FIELD_LABELS) {
      fields.push(field);
      return `${FIELD_LABELS[field]}: ${text}`;
    }
    return text;
  });
  return { text: parts.join("; "), fields };
}

const countText = (n: number) => `${n} / ${TEXT_MAX} characters${n >= TEXT_MAX ? " — limit reached" : ""}`;

// ENH-018: the coordinator's feedback on one completed activity (spec §7.2). Native radios in a fieldset give arrow-key
// navigation and a spoken group name; `required` on the radios and the feedback textarea gives native validation. On a
// refusal the entry is kept, the alert takes focus and names the field, which is marked invalid (QA-018-01); a 409 goes to the
// parent with the unsent text, which it shows next to the stored feedback (QA-018-03). The long fields show how much of their
// limit is used (QA-018-02). Once anything is entered, leaving the page asks first and Cancel confirms (QA-018-08); nothing is
// stored in the browser. (Next.js in-app links cannot be intercepted, so a sidebar click is not covered.)
function ScoreField({ name, legend }: { name: string; legend: string }) {
  return (
    <fieldset className="score-field">
      <legend>{legend}</legend>
      <div className="score-options">
        {SCORE_LABELS.map((label, i) => (
          <label key={label}>
            <input type="radio" name={name} value={i + 1} required />
            {`${i + 1} – ${label}`}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export default function ActivityFeedbackForm({ activity, onSubmitted, onDuplicate, onCancel }: Props) {
  const id = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<FormError | null>(null);
  const [lengths, setLengths] = useState({ feedback: 0, suggestions: 0 });
  const [dirty, setDirty] = useState(false);
  const invalid = (field: FieldName) => (error?.fields?.includes(field) ? true : undefined);

  useEffect(() => headingRef.current?.focus(), []);
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function cancel() {
    if (dirty && !window.confirm(DISCARD_PROMPT)) return;
    onCancel();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const text = (key: string) => String(form.get(key) ?? "").trim() || null;
    if (!text("feedback")) return setError({ text: `${FIELD_LABELS.feedback}: Must not be blank`, fields: ["feedback"] });
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/v1/school/activities/${activity.activity_id}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating: Number(form.get("rating")), satisfaction: Number(form.get("satisfaction")), trainer_name: text("trainer_name"), feedback: String(form.get("feedback") ?? ""), suggestions: text("suggestions") }),
      });
      const data = await response.json().catch(() => null);
      if (response.status === 409) return onDuplicate({ trainer_name: text("trainer_name"), feedback: String(form.get("feedback") ?? ""), suggestions: text("suggestions") });
      if (response.status === 401) return setError({ text: `${SESSION_EXPIRED} Your entry is kept; sign in again in a new tab, then submit.`, expired: true });
      const detail = (data as { detail?: unknown } | null)?.detail;
      const invalidFields = response.status === 422 ? fieldError(detail) : null;
      if (invalidFields) return setError(invalidFields);
      if (!response.ok || !isRequestBody(data)) return setError({ text: detailMessage(detail, "Could not save the feedback.") });
      onSubmitted(data as ActivityFeedback);
    } catch {
      setError({ text: NOT_COMPLETED });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="action-card">
      <form className="form" onSubmit={submit} onChange={() => setDirty(true)} aria-labelledby={`${id}-heading`}>
        <div>
          <h3 id={`${id}-heading`} ref={headingRef} tabIndex={-1}>{`Feedback: ${activity.title}`}</h3>
          <p className="muted" style={{ margin: 0 }}>
            <LocalDateTime value={activity.scheduled_at} withTime /> · {participationText(activity.participation)}
          </p>
        </div>
        <ScoreField name="rating" legend="Overall rating" />
        <ScoreField name="satisfaction" legend="School satisfaction" />
        <div className="field">
          <label htmlFor={`${id}-trainer`}>Trainer / Counsellor (optional)</label>
          <input id={`${id}-trainer`} name="trainer_name" maxLength={200} autoComplete="off" aria-describedby={`${id}-trainer-hint`} aria-invalid={invalid("trainer_name")} />
          <p id={`${id}-trainer-hint`} className="field-hint">Up to 200 characters.</p>
        </div>
        <div className="field">
          <label htmlFor={`${id}-feedback`}>Feedback</label>
          <textarea
            id={`${id}-feedback`}
            name="feedback"
            required
            maxLength={TEXT_MAX}
            aria-describedby={`${id}-privacy ${id}-feedback-count`}
            aria-invalid={invalid("feedback")}
            onChange={(e) => setLengths((l) => ({ ...l, feedback: e.target.value.length }))}
          />
          <p id={`${id}-privacy`} className="field-hint">Describe the session. Please don&apos;t include students&apos; personal details.</p>
          <p id={`${id}-feedback-count`} className="field-hint">{countText(lengths.feedback)}</p>
        </div>
        <div className="field">
          <label htmlFor={`${id}-suggestions`}>Suggestions (optional)</label>
          <textarea
            id={`${id}-suggestions`}
            name="suggestions"
            maxLength={TEXT_MAX}
            aria-describedby={`${id}-suggestions-count`}
            aria-invalid={invalid("suggestions")}
            onChange={(e) => setLengths((l) => ({ ...l, suggestions: e.target.value.length }))}
          />
          <p id={`${id}-suggestions-count`} className="field-hint">{countText(lengths.suggestions)}</p>
        </div>
        {error && (
          <div ref={errorRef} tabIndex={-1} className="form-error" role="alert">
            {error.text}
            {error.expired && <> <Link href={SIGN_IN_PATH} target="_blank" rel="noopener">Sign in again</Link></>}
          </div>
        )}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <button className="btn" disabled={busy}>{busy ? "Saving…" : "Submit feedback"}</button>
          <button type="button" className="btn secondary" onClick={cancel} disabled={busy}>Cancel</button>
        </div>
      </form>
    </div>
  );
}
