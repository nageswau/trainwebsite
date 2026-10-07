"use client";
import { type FormEvent, useState } from "react";

import BdmConfirm from "@/components/BdmConfirm";
import { sendJson } from "@/lib/apiErrors";
import { COMMENT_MAX, commentUrl, type DailyReport, isDailyReport, NOTE_MAX, reportUrl, submitUrl } from "@/lib/bdmDailyReports";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-015 (spec §6): one day's report -- the counts (computed by the API; an untracked count says so, never 0), then the BDM's note
// and Submit (after a confirm: submitting freezes the counts and locks the day's activities), or for a manager the comment form on a
// submitted report. The API decides every rule; a refusal is shown as its own sentence and a 409 re-reads the report.
export default function BdmDailyReport({ initial, mode }: { initial: DailyReport; mode: "bdm" | "manager" }) {
  const [report, setReport] = useState(initial);
  const [note, setNote] = useState("");
  const [comment, setComment] = useState(initial.manager_comment?.text ?? "");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const day = report.report_date;

  async function reread() {
    try {
      const response = await fetch(reportUrl(day));
      const data = response.ok ? await response.json() : null;
      if (isDailyReport(data)) setReport(data);
    } catch {
      // the refusal is already on screen; the page can be reloaded
    }
  }

  async function submit() {
    setBusy(true);
    setError(null);
    const outcome = await sendJson(submitUrl(day), "POST", { note: note.trim() ? note : null });
    setBusy(false);
    setConfirming(false);
    if (outcome.ok && isDailyReport(outcome.data)) {
      setReport(outcome.data);
      setNotice("Report submitted. This day's activities are now locked.");
      focus("daily-report-status");
      return;
    }
    setError(outcome.ok ? "Something went wrong." : outcome.message);
    if (!outcome.ok && outcome.status === 409) await reread();
    focus("daily-report-error");
  }

  async function saveComment(e: FormEvent) {
    e.preventDefault();
    setNotice(null);
    if (!comment.trim()) { // QA15-01: `required` lets spaces through; refuse here instead of a 422 round trip
      setError("Write a comment first.");
      focus("daily-report-error");
      return;
    }
    setBusy(true);
    setError(null);
    const outcome = await sendJson(commentUrl(report.bdm.id, day), "PUT", { comment });
    setBusy(false);
    if (outcome.ok && isDailyReport(outcome.data)) {
      setReport(outcome.data);
      setNotice("Comment saved.");
      focus("daily-report-status");
      return;
    }
    setError(outcome.ok ? "Something went wrong." : outcome.message);
    focus("daily-report-error");
  }

  const submitted = report.status === "submitted";
  return (
    <>
      <p className="muted">
        {submitted
          ? `Submitted ${formatSchoolDateTime(report.submitted_at, true)}. These counts were saved when the report was submitted.`
          : mode === "manager"
            ? "Not submitted yet. These counts are a live preview."
            : report.can_submit
              ? "A live preview of the day's counts. Add a note and submit at the end of the day."
              : `Reports can be submitted up to ${report.submit_window_days} days back. These counts are a live preview.`}
      </p>
      <dl className="kpi-grid" aria-label="Day counts">
        {report.counts.map((c) => (
          <div className="kpi-tile" key={c.key}>
            <dt>{c.label}</dt>
            <dd className="kpi-value">{c.tracked ? c.count : "Not tracked"}</dd>
            <dd className="kpi-note muted">{c.definition}</dd>
          </div>
        ))}
      </dl>
      <div id="daily-report-status" tabIndex={-1} role="status" aria-live="polite" className={notice ? "form-message" : undefined}>{notice}</div>
      {error && <p id="daily-report-error" tabIndex={-1} className="form-error" role="alert">{error}</p>}

      {submitted && (
        <section className="action-card wide" aria-label="Submitted report">
          <h3>End-of-day note</h3>
          <p style={{ whiteSpace: "pre-wrap" }}>{report.note ?? "No note."}</p>
          {report.manager_comment && (
            <>
              <h3>Manager&apos;s comment</h3>
              <p style={{ whiteSpace: "pre-wrap" }}>{report.manager_comment.text}</p>
              <p className="muted">{report.manager_comment.by.full_name}, {formatSchoolDateTime(report.manager_comment.at, true)}</p>
            </>
          )}
        </section>
      )}

      {mode === "bdm" && !submitted && report.can_submit && (
        <section className="action-card wide" aria-label="Submit the report">
          <div className="field">
            <label htmlFor="daily-report-note">End-of-day note (optional)</label>
            <textarea id="daily-report-note" value={note} maxLength={NOTE_MAX} rows={4} onChange={(e) => setNote(e.target.value)}
              aria-describedby="daily-report-note-hint daily-report-note-count" />
            <p id="daily-report-note-hint" className="field-hint">Your reporting manager reads this note. On a day off, say so here.</p>
            <p id="daily-report-note-count" className="muted">{note.length} / {NOTE_MAX}</p>
          </div>
          {confirming ? (
            <BdmConfirm label="Confirm submitting the report" confirmText="Yes, submit" busyText="Submitting…" busy={busy} onConfirm={() => void submit()}
              onCancel={() => { setConfirming(false); focus("daily-report-submit"); }}>
              Submitting saves these counts and locks this day&apos;s activities. You can&apos;t undo it.
            </BdmConfirm>
          ) : (
            <div className="actions">
              <button id="daily-report-submit" type="button" className="btn" onClick={() => { setConfirming(true); setNotice(null); }}>Submit report</button>
            </div>
          )}
        </section>
      )}

      {mode === "manager" && submitted && (
        <form className="action-card wide" aria-label="Comment on the report" onSubmit={(e) => void saveComment(e)}>
          <div className="field">
            <label htmlFor="daily-report-comment">Your comment</label>
            <textarea id="daily-report-comment" value={comment} maxLength={COMMENT_MAX} rows={3} required onChange={(e) => setComment(e.target.value)}
              aria-describedby="daily-report-comment-count" />
            <p id="daily-report-comment-count" className="muted">{comment.length} / {COMMENT_MAX}</p>
          </div>
          <div className="actions">
            <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save comment"}</button>
          </div>
        </form>
      )}
    </>
  );
}
