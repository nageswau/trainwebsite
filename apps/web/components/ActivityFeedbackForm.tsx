"use client";

import { FormEvent, useEffect, useId, useRef, useState } from "react";

import LocalDateTime from "@/components/LocalDateTime";
import { type ActivityFeedback, type FeedbackActivity, participationText, SCORE_LABELS } from "@/lib/activityFeedback";
import { detailMessage, isRequestBody, NOT_COMPLETED } from "@/lib/apiErrors";

type Props = { activity: FeedbackActivity; onSubmitted: (feedback: ActivityFeedback) => void; onDuplicate: () => void; onCancel: () => void };

// ENH-018: the coordinator's feedback on one completed activity (spec §7.2). Native radios in a fieldset give arrow-key
// navigation and a spoken group name; `required` on the radios and the feedback textarea gives native validation. On a
// refusal the entry is kept and the alert takes focus; a 409 goes to the parent, which shows the feedback already stored.
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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => headingRef.current?.focus(), []);
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const text = (key: string) => String(form.get(key) ?? "").trim() || null;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/v1/school/activities/${activity.activity_id}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating: Number(form.get("rating")), satisfaction: Number(form.get("satisfaction")), trainer_name: text("trainer_name"), feedback: String(form.get("feedback") ?? ""), suggestions: text("suggestions") }),
      });
      const data = await response.json().catch(() => null);
      if (response.status === 409) return onDuplicate();
      if (!response.ok || !isRequestBody(data)) return setError(detailMessage((data as { detail?: unknown } | null)?.detail, "Could not save the feedback."));
      onSubmitted(data as ActivityFeedback);
    } catch {
      setError(NOT_COMPLETED);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="action-card">
      <form className="form" onSubmit={submit} aria-labelledby={`${id}-heading`}>
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
          <input id={`${id}-trainer`} name="trainer_name" maxLength={200} autoComplete="off" />
        </div>
        <div className="field">
          <label htmlFor={`${id}-feedback`}>Feedback</label>
          <textarea id={`${id}-feedback`} name="feedback" required maxLength={5000} aria-describedby={`${id}-privacy`} />
          <p id={`${id}-privacy`} className="muted" style={{ margin: 0, fontSize: 13 }}>Describe the session. Please don&apos;t include students&apos; personal details.</p>
        </div>
        <div className="field">
          <label htmlFor={`${id}-suggestions`}>Suggestions (optional)</label>
          <textarea id={`${id}-suggestions`} name="suggestions" maxLength={5000} />
        </div>
        {error && <div ref={errorRef} tabIndex={-1} className="form-error" role="alert">{error}</div>}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <button className="btn" disabled={busy}>{busy ? "Saving…" : "Submit feedback"}</button>
          <button type="button" className="btn secondary" onClick={onCancel} disabled={busy}>Cancel</button>
        </div>
      </form>
    </div>
  );
}
