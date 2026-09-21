"use client";

import { KeyboardEvent, useEffect, useRef, useState } from "react";

import { formatDate } from "@/lib/formatDate";
import { detailMessage, isRequestBody } from "@/lib/apiErrors";
import { type AdminTransferRequest, STATUS_CLASS, STATUS_LABEL } from "@/lib/transfers";

// ENH-005 -- one request in the admin's queue (spec §7.1). Approve and reject are irreversible from here, so each is two-step and
// inline (ENH-004's pattern, no dialog library): the consequences are stated, focus moves into the confirm, Escape or Cancel puts it
// back on the button that opened it.
type Mode = "idle" | "approve" | "reject";
export type Decision = { request: AdminTransferRequest; message: string };
export type Failure = { text: string; expired?: boolean; refetch?: boolean };

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

// Approval clears the student's pending parent invite (it belongs to the losing school), so a parent who has not accepted yet would end up with
// an account at the losing school and no linked child. Said in words before the admin decides, and again beside the irreversible button.
const inviteWarning = (r: AdminTransferRequest) =>
  `A parent has been invited but has not accepted yet. Approving clears that invite, so they will not be linked to ${r.student_name}. Consider asking them to accept it first.`;

function describeOutcome(request: AdminTransferRequest) {
  const o = request.outcome;
  return o ? `${plural(o.parents_moved, "parent")} moved, ${o.parents_kept} kept, ${plural(o.results_withdrawn, "result")} withdrawn` : "";
}

export default function AdminTransferRow({ request, onDecided, onFailure }: { request: AdminTransferRequest; onDecided: (d: Decision) => void; onFailure: (f: Failure) => void }) {
  const [mode, setMode] = useState<Mode>("idle");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const opener = useRef<Mode>("idle");
  const buttons = useRef<Record<string, HTMLButtonElement | null>>({});
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const restoreFocus = useRef(false);
  const inFlight = useRef(false); // `busy` is state: two clicks in one task both see false (found by the browser QA)
  const r = request;
  const preview = r.preview;

  // Focus follows the confirm in and back out: into the confirm when it opens (the note field for a rejection, which is typed first),
  // and back onto the button that opened it when it closes without a decision.
  useEffect(() => {
    if (mode === "approve") buttons.current.confirmApprove?.focus();
    else if (mode === "reject") noteRef.current?.focus();
    else if (restoreFocus.current) {
      restoreFocus.current = false;
      buttons.current[opener.current]?.focus();
    }
  }, [mode]);

  function open(next: Mode) {
    opener.current = next;
    setMode(next);
  }
  function close() {
    restoreFocus.current = true;
    setMode("idle");
  }
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape" && !busy) close();
  }

  async function decide(kind: "approve" | "reject") {
    if (busy || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    let response: Response;
    try {
      response = await fetch(`/api/v1/overseas-admin/school-transfer-requests/${r.id}/${kind}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(kind === "reject" && note.trim() ? { note: note.trim() } : {}),
      });
    } catch {
      inFlight.current = false;
      setBusy(false);
      return onFailure({ text: "The decision did not complete. Check your connection and refresh the queue before trying again." });
    }
    const data = await response.json().catch(() => null);
    inFlight.current = false;
    setBusy(false);
    if (response.status === 401) return onFailure({ text: "Your session has expired. ", expired: true });
    if (!response.ok) return onFailure({ text: detailMessage(data?.detail), refetch: response.status === 409 });
    // A 2xx that is not the decided request (a proxy page, an empty body) does not show the decision was recorded, and describeOutcome would
    // fail on it. Re-read the queue rather than guess (browser QA N2).
    if (!isRequestBody(data)) return onFailure({ text: "The decision could not be confirmed. The queue is being reloaded; check it before deciding again.", refetch: true });
    const updated = data as AdminTransferRequest;
    onDecided({ request: updated, message: kind === "approve" ? `Moved ${r.student_name} to ${r.to_school.name}. ${describeOutcome(updated)}.` : `Request rejected for ${r.student_name}.` });
  }

  return (
    <li>
      <div className="who">
        <strong>{r.student_name}</strong>
        <span>{r.student_code}</span>
        <span>From {r.from_school.name} → To {r.to_school.name}</span>
        <span>Requested by {r.requester.name} ({r.direction === "outgoing" ? "the losing" : "the gaining"} school) · {formatDate(r.created_at)}</span>
        {r.reason && <span>Reason: {r.reason}</span>}
        {r.decision_note && <span>Note: {r.decision_note}</span>}
        {r.status === "pending" && preview && (
          <span>If approved: up to {plural(preview.linked_parents, "linked parent account")} may move, and {plural(preview.in_flight_results, "unpublished result")} will be withdrawn.</span>
        )}
        {r.status === "pending" && preview && !preview.to_school_has_portfolio_staff && (
          <span className="form-warning">{r.to_school.name} has no assigned staff portfolio, so the student will be invisible to the Academic Team, Career Counselor and Psychometric Team until one is assigned.</span>
        )}
        {r.status === "pending" && preview?.pending_parent_invite && <span className="form-warning">{inviteWarning(r)}</span>}
        {r.outcome && <span>{describeOutcome(r)}</span>}
      </div>
      <div className="meta">
        <span className={STATUS_CLASS[r.status]}>{STATUS_LABEL[r.status]}</span>
        {r.status === "pending" && mode === "idle" && (
          <>
            <button ref={(el) => { buttons.current.approve = el; }} type="button" className="btn small" aria-label={`Approve transfer of ${r.student_name} to ${r.to_school.name}`} onClick={() => open("approve")}>Approve</button>
            <button ref={(el) => { buttons.current.reject = el; }} type="button" className="btn small secondary" aria-label={`Reject transfer of ${r.student_name} to ${r.to_school.name}`} onClick={() => open("reject")}>Reject</button>
          </>
        )}
      </div>
      {mode === "approve" && (
        <div style={{ flexBasis: "100%", display: "grid", gap: 8 }} onKeyDown={onKeyDown}>
          <p id={`approve-text-${r.id}`}>Moves {r.student_name} to {r.to_school.name}.</p>
          <p>Up to {plural(preview?.linked_parents ?? 0, "linked parent account")} {preview?.linked_parents === 1 ? "moves" : "move"} to {r.to_school.name} if they have no other child at {r.from_school.name}. Each parent keeps access to their child.</p>
          <p>{plural(preview?.in_flight_results ?? 0, "unpublished result")} {preview?.in_flight_results === 1 ? "is" : "are"} withdrawn. The teacher assignment is cleared. This cannot be undone here.</p>
          {preview?.pending_parent_invite && <p className="form-warning">{inviteWarning(r)}</p>}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button ref={(el) => { buttons.current.confirmApprove = el; }} type="button" className="btn" disabled={busy} aria-describedby={`approve-text-${r.id}`} onClick={() => void decide("approve")}>{busy ? "Approving…" : "Confirm approval"}</button>
            <button type="button" className="btn ghost" disabled={busy} onClick={close}>Cancel</button>
          </div>
        </div>
      )}
      {mode === "reject" && (
        <div style={{ flexBasis: "100%", display: "grid", gap: 8 }} onKeyDown={onKeyDown}>
          <div className="field">
            <label htmlFor={`reject-note-${r.id}`}>Note for the requesting coordinator (optional)</label>
            <textarea ref={noteRef} id={`reject-note-${r.id}`} className="search" rows={2} maxLength={500} value={note} disabled={busy} aria-describedby={`reject-hint-${r.id}`} onChange={(e) => setNote(e.target.value)} />
            <span id={`reject-hint-${r.id}`} className="muted">Visible to the requesting coordinator. Do not include student details.</span>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="button" className="btn" disabled={busy} onClick={() => void decide("reject")}>{busy ? "Rejecting…" : "Confirm rejection"}</button>
            <button type="button" className="btn ghost" disabled={busy} onClick={close}>Cancel</button>
          </div>
        </div>
      )}
    </li>
  );
}
