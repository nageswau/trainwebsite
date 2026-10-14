"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { Figures, ReviewSection } from "@/components/ManagementReview";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import { formatTarget } from "@/lib/managementPlans";
import { inrOrNone, missingProblems, NEXT_MONTH_PROMPTS, PROBLEM_PROMPTS, reviewApi, type MonthlyReview, type NarrativeKey, type ReviewNarrative } from "@/lib/managementReviews";
import { useHydrated } from "@/lib/useHydrated";

const MAX = 4000; // MR13, the API's limit per answer

// mgmt-032 (MR13): §9 Problems and §10 Next month. A draft's answers are edited here (only the changed ones are sent), its figures can
// be regenerated, and it is finalised after a confirmation; a final review shows the answers read-only. Every outcome is announced
// under the buttons (FormMessage); the page re-renders from the server afterwards.
export default function ManagementReviewEditor({ review }: { review: MonthlyReview }) {
  const router = useRouter();
  const ready = useHydrated();
  const draft = review.status === "draft";
  const [answers, setAnswers] = useState<ReviewNarrative>(review.narrative);
  const [saved, setSaved] = useState<ReviewNarrative>(review.narrative);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const sending = useRef(false);
  const next = review.snapshot.next_month;

  const changes = () => Object.fromEntries(Object.entries(answers).filter(([key, value]) => value.trim() !== saved[key as NarrativeKey].trim()));

  async function run(work: () => Promise<string | null>) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setMessage(null);
    try {
      const failure = await work();
      if (failure) setMessage({ text: failure, failed: true });
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }

  async function saveChanges(): Promise<string | null> {
    const body = changes();
    if (Object.keys(body).length === 0) return null;
    const result = await sendJson(reviewApi(review.month), "PATCH", body);
    if (!result.ok) return result.message;
    setSaved(answers);
    return null;
  }

  const save = () => run(async () => {
    if (Object.keys(changes()).length === 0) {
      setMessage({ text: "No changes to save.", failed: false });
      return null;
    }
    const failure = await saveChanges();
    if (failure) return failure;
    setMessage({ text: "Answers saved.", failed: false });
    router.refresh();
    return null;
  });

  const regenerate = () => run(async () => {
    const result = await sendRequest(`${reviewApi(review.month)}/generate`, { method: "POST" });
    if (!result.ok) return result.message;
    setMessage({ text: "Figures regenerated from today's data. Your answers are kept.", failed: false });
    router.refresh();
    return null;
  });

  function finalise() {
    const missing = missingProblems(answers);
    if (missing) {
      setMessage({ text: missing, failed: true });
      return;
    }
    if (!window.confirm(`Finalise the review for ${review.label}? Its figures and answers can no longer change, and every partner is emailed a link.`)) return;
    void run(async () => {
      const failure = await saveChanges();
      if (failure) return failure;
      const result = await sendRequest(`${reviewApi(review.month)}/finalise`, { method: "POST" });
      if (!result.ok) return result.message;
      setMessage({ text: "Review finalised. Partners have been sent a link.", failed: false });
      router.refresh();
      return null;
    });
  }

  const field = (key: NarrativeKey, label: string) =>
    draft ? (
      <div className="field" key={key}>
        <label htmlFor={`review-${key}`}>{label}</label>
        <textarea id={`review-${key}`} rows={4} maxLength={MAX} value={answers[key]} onChange={(e) => setAnswers({ ...answers, [key]: e.target.value })} />
      </div>
    ) : (
      <div key={key} style={{ marginBottom: 12 }}>
        <h4>{label}</h4>
        <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }} className={answers[key] ? undefined : "muted"}>{answers[key] || "Not answered"}</p>
      </div>
    );

  return (
    <form className="form" noValidate aria-label="Problems and next month" onSubmit={(e) => { e.preventDefault(); void save(); }}>
      <fieldset disabled={!ready || busy} className="form" style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
        <ReviewSection title="9. Problems">{PROBLEM_PROMPTS.map(([key, label]) => field(key, label))}</ReviewSection>
        <ReviewSection title="10. Next month">
          <h4>Targets for {next.label}</h4>
          {next.targets.length === 0 ? (
            <p className="muted">No KPI targets planned.</p>
          ) : (
            <Figures caption={`Targets for ${next.label}`} rows={next.targets.map((t): [string, string] => [`${t.vertical} · ${t.text} (${t.kpi})`, formatTarget(t.target, t.unit)])} />
          )}
          <Figures caption={`Marketing budget for ${next.label}`} rows={[[`Marketing budget for ${next.label}`, inrOrNone(next.budget)]]} />
          {NEXT_MONTH_PROMPTS.map(([key, label]) => field(key, label))}
        </ReviewSection>
        {draft && (
          <div className="actions">
            <button className="btn" type="submit">{busy ? "Working…" : "Save answers"}</button>
            <button className="btn secondary" type="button" onClick={() => void regenerate()}>Regenerate figures</button>
            <button className="btn secondary" type="button" onClick={finalise}>Finalise review</button>
          </div>
        )}
      </fieldset>
      {message && <FormMessage message={message} style={{ marginTop: 12 }} />}
    </form>
  );
}
