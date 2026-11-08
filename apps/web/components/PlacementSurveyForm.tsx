"use client";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmTravel";
import { surveyUrl } from "@/lib/placements";

// pob-026 (DEC-SCOPE-435 S8/S12): one rating (1-5) and an optional comment through the signed link. The API decides every outcome:
// 404 unknown link, 410 used or expired, 429 too many attempts.
type Survey = { respondent: "client" | "candidate"; role: string; company: string };
type State = { kind: "loading" } | { kind: "form"; survey: Survey } | { kind: "done" } | { kind: "closed"; message: string } | { kind: "failed" };

const RATINGS: [number, string][] = [[1, "Very dissatisfied"], [2, "Dissatisfied"], [3, "Neutral"], [4, "Satisfied"], [5, "Very satisfied"]];
const COMMENT_MAX = 1000;
const GONE = "This feedback link has already been used or has expired."; // QA-01: the API's 410 does not say which
const INVALID = "This feedback link is not valid. Please use the link from your email.";
const BUSY = "Too many attempts from this network. Please try again later.";
const FAILED = "We couldn't reach the server. Check your connection and try again.";

const closedMessage = (status?: number) => (status === 410 ? GONE : status === 429 ? BUSY : status === 404 ? INVALID : null);

export default function PlacementSurveyForm({ token }: { token: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [rating, setRating] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const response = await fetch(surveyUrl(token), { cache: "no-store" });
      const data = await response.json().catch(() => null);
      if (response.ok && data && typeof data.role === "string") return setState({ kind: "form", survey: data as Survey });
      const message = closedMessage(response.status);
      setState(message ? { kind: "closed", message } : { kind: "failed" });
    } catch {
      setState({ kind: "failed" });
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (state.kind === "done" || state.kind === "closed") heading.current?.focus();
  }, [state.kind]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    if (rating === null) return setErrors({ rating: "Choose a rating from 1 to 5" });
    inFlight.current = true;
    setBusy(true);
    setErrors({});
    setFailure(null);
    const result = await sendJson(surveyUrl(token), "POST", { rating, comment: comment.trim() || null });
    inFlight.current = false;
    setBusy(false);
    if (result.ok) return setState({ kind: "done" });
    const placed = fieldErrors(result.detail);
    if (Object.keys(placed).length) return setErrors(placed);
    const message = closedMessage(result.status);
    if (message) return setState({ kind: "closed", message });
    setFailure(result.status ? result.message : FAILED);
  }

  if (state.kind === "loading") return <p role="status" className="muted">Loading your survey…</p>;
  if (state.kind === "failed") {
    return (
      <div role="alert" className="card vertical-card">
        <p className="form-error" style={{ margin: 0 }}>{FAILED}</p>
        <button type="button" className="btn secondary" onClick={() => void load()}>Try again</button>
      </div>
    );
  }
  if (state.kind === "done" || state.kind === "closed") {
    return (
      <div className="card vertical-card">
        <h1 ref={heading} tabIndex={-1} style={{ fontSize: 24, margin: 0 }}>{state.kind === "done" ? "Thank you for your feedback" : "Feedback link closed"}</h1>
        <p className="lead" style={{ margin: 0 }}>{state.kind === "done" ? "Your answer has been recorded. You can close this page." : state.message}</p>
      </div>
    );
  }
  const { survey } = state;
  const about = survey.respondent === "client" ? `the candidate we placed in the ${survey.role} role` : `your placement as ${survey.role}`;
  return (
    <form className="card vertical-card" noValidate onSubmit={submit} aria-labelledby="survey-title" style={{ display: "grid", gap: 16 }}>
      <div>
        <h1 id="survey-title" style={{ fontSize: 24, margin: 0 }}>How did it go?</h1>
        <p className="lead" style={{ margin: "4px 0 0", overflowWrap: "anywhere" }}>How satisfied are you with {about} at {survey.company}?</p>
      </div>
      <fieldset style={{ border: 0, padding: 0, margin: 0 }} aria-invalid={errors.rating ? true : undefined} aria-describedby={errors.rating ? "survey-rating-error" : undefined}>
        <legend style={{ fontWeight: 600, marginBottom: 8 }}>Your rating</legend>
        <div style={{ display: "grid", gap: 6 }}>
          {RATINGS.map(([value, label]) => (
            <label key={value} style={{ display: "flex", gap: 8, alignItems: "center", minHeight: 32, cursor: "pointer" }}>
              <input type="radio" name="rating" value={value} checked={rating === value} disabled={busy} onChange={() => setRating(value)} />
              <span><strong>{value}</strong> · {label}</span>
            </label>
          ))}
        </div>
        {errors.rating && <p id="survey-rating-error" className="form-error">{errors.rating}</p>}
      </fieldset>
      <div className="field">
        <label htmlFor="survey-comment">Comment (optional)</label>
        <textarea id="survey-comment" rows={4} maxLength={COMMENT_MAX} value={comment} disabled={busy} onChange={(e) => setComment(e.target.value)}
          aria-invalid={errors.comment ? true : undefined} aria-describedby={errors.comment ? "survey-comment-error" : "survey-comment-count"} />
        <p id="survey-comment-count" className="muted" style={{ margin: 0, fontSize: 13 }}>{comment.length} / {COMMENT_MAX}</p>
        {errors.comment && <p id="survey-comment-error" className="form-error">{errors.comment}</p>}
      </div>
      {failure && <p role="alert" className="form-error" style={{ margin: 0 }}>{failure}</p>}
      <div>
        <button type="submit" className="btn" disabled={busy}>{busy ? "Sending…" : "Send feedback"}</button>
      </div>
    </form>
  );
}
