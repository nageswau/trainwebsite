"use client";
import { type FormEvent, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson } from "@/lib/apiErrors";
import { isRequirementBody, type Requirement, REQUIREMENTS_URL } from "@/lib/recruiterRequirements";

// hrc-007 (DEC-SCOPE-380 A6/A8): sending a requirement for approval, and an approver's decision. The server decides who may do either
// (`approval.can_submit` / `can_decide`, the `jobs.approve` grant, never one's own job); these forms only send and show its answer.
type Done = (requirement: Requirement, notice: string) => void;

export function SubmitForApproval({ requirement, onDone }: { requirement: Requirement; onDone: Done }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const id = `requirement-${requirement.id}-submit`;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(`${REQUIREMENTS_URL}/${requirement.id}/submit`, "POST", note.trim() ? { note: note.trim() } : {});
    setBusy(false);
    if (outcome.ok && isRequirementBody(outcome.data)) {
      setNote("");
      onDone(outcome.data.requirement, "Sent for approval. It opens once an approver approves it.");
    } else setFailure(outcome.ok ? "Unable to send this requirement for approval." : outcome.message);
  }

  return (
    <section className="action-card wide" aria-labelledby={id}>
      <h3 id={id}>Approval</h3>
      <p style={{ margin: 0 }}>This requirement needs approval before it opens to candidates.</p>
      <form className="form" onSubmit={submit} aria-busy={busy}>
        <div className="field">
          <label htmlFor={`${id}-note`}>Note for the approver (optional)</label>
          <input id={`${id}-note`} type="text" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
        </div>
        <div className="actions">
          <button type="submit" className="btn small" disabled={busy}>
            {busy ? "Sending…" : "Submit for approval"}
          </button>
        </div>
      </form>
      {failure && (
        <p className="form-error" role="alert">
          {failure}
        </p>
      )}
    </section>
  );
}

/** Approve (optional note) or reject (a reason is required). `onDone` gets the requirement the API returns. */
export function ApprovalDecision({ requirementId, title, onDone }: { requirementId: string; title: string; onDone: Done }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const id = `approval-${requirementId}`;

  async function decide(action: "approve" | "reject") {
    if (busy) return;
    const value = text.trim();
    if (action === "reject" && !value) {
      setFailure("Give a reason to reject this requirement.");
      document.getElementById(`${id}-text`)?.focus();
      return;
    }
    setBusy(action);
    setFailure(null);
    const body = action === "reject" ? { reason: value } : value ? { note: value } : {};
    const outcome = await sendJson(`${REQUIREMENTS_URL}/${encodeURIComponent(requirementId)}/${action}`, "POST", body);
    setBusy(null);
    if (outcome.ok && isRequirementBody(outcome.data)) {
      setText("");
      onDone(outcome.data.requirement, action === "approve" ? `${title} approved. It is now open.` : `${title} rejected and returned to draft.`);
    } else setFailure(outcome.ok ? "Unable to record the decision." : outcome.message);
  }

  return (
    <div className="form" aria-busy={busy !== null}>
      <div className="field">
        <label htmlFor={`${id}-text`}>Note, or the reason when rejecting</label>
        <textarea id={`${id}-text`} rows={2} value={text} maxLength={500} aria-invalid={failure ? true : undefined}
          aria-describedby={failure ? `${id}-error` : undefined} onChange={(e) => setText(e.target.value)} />
      </div>
      <div className="actions">
        <button type="button" className="btn small" disabled={busy !== null} onClick={() => void decide("approve")}>
          {busy === "approve" ? "Approving…" : "Approve"}
        </button>
        <button type="button" className="btn secondary small" disabled={busy !== null} onClick={() => void decide("reject")}>
          {busy === "reject" ? "Rejecting…" : "Reject"}
        </button>
      </div>
      {failure && (
        <p id={`${id}-error`} className="form-error" role="alert">
          {failure}
        </p>
      )}
    </div>
  );
}

/** Who sent it and when -- shown while the requirement is pending. */
export function SubmittedLine({ by, at }: { by: { full_name: string } | null; at: string | null }) {
  if (!at) return null;
  return (
    <p style={{ margin: 0 }} className="muted">
      Sent for approval{by ? ` by ${by.full_name}` : ""} on <LocalTime value={at} time />.
    </p>
  );
}
