"use client";

import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import LeadNotes from "@/components/LeadNotes";
import LeadTimeline from "@/components/LeadTimeline";
import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import {
  LOST_REASONS_URL, isClosed, isLoss, needsReason, personTargets, stageLabel, type Closure, type LeadClosureFields, type LostReason,
} from "@/lib/leadStages";
import { getPage } from "@/lib/telecallerCatalogue";

type Lead = { id: string; name: string; status: string };
type Message = { id: string; text: string; failed: boolean };

/** ccrm-006 D8: the active lost reasons, read once the form needs them; a failure offers Retry. */
function useLostReasons(wanted: boolean) {
  const [items, setItems] = useState<LostReason[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!wanted || items) return;
    const controller = new AbortController();
    setFailed(false);
    getPage<LostReason>(`${LOST_REASONS_URL}?active=true&limit=100`, controller.signal)
      .then((page) => setItems(page.items))
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [wanted, items, attempt]);
  return { items, failed, retry: () => setAttempt((n) => n + 1) };
}

const adminMove = (id: string, target: string, reason: string, closure: Closure = {}) =>
  sendJson(`/api/v1/admin/leads/${id}`, "PATCH", { status: target, ...(reason ? { reason } : {}), ...closure });

// tel-004 (spec §6, T25): an admin's stage move. Only the moves the API accepts are offered (lib/leadStages mirrors the rules); a
// closed outcome or a reopen needs a reason, checked here first so the admin isn't sent a 422. The API stays the authority.
// tel-008: the lead detail reuses it with the telecaller route (`move`); a telecaller can't reopen a closed lead (`canReopen`).
// ccrm-006 (D3-D5): Duplicate asks for the surviving lead's Lead ID; Lost / Not Interested for a reason from the list and "lost to".
// `onChanged` gets the lead's new closure, so the caller can show it without a re-read.
export function LeadStageControl({ lead, onChanged, onMessage, move = adminMove, canReopen = true, targets: offered }: {
  lead: Lead; onChanged: (status: string, closure: Required<LeadClosureFields>) => void; onMessage: (m: Message) => void;
  move?: (id: string, target: string, reason: string, closure: Closure) => Promise<SendOutcome>; canReopen?: boolean;
  targets?: string[]; // ccrm-003: the counselor's CC8 list (lib/leadStages counselorTargets) instead of the telecaller / admin moves
}) {
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState("");
  const [duplicateOf, setDuplicateOf] = useState("");
  const [lostReasonId, setLostReasonId] = useState("");
  const [lostTo, setLostTo] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const reasonId = useId();
  const loss = isLoss(target);
  const reasons = useLostReasons(open && loss);
  const opener = useRef<HTMLButtonElement>(null);
  const refocus = useRef(false);
  // Browser QA-01: closing the form (Save or Cancel) unmounts it, so put keyboard focus back on the button that opened it.
  useEffect(() => {
    if (!open && refocus.current) {
      refocus.current = false;
      opener.current?.focus();
    }
  }, [open]);
  const targets = offered ?? personTargets(lead.status, canReopen);
  if (targets.length === 0) return null;

  function close() {
    refocus.current = true;
    setOpen(false);
    setTarget("");
    setReason("");
    setDuplicateOf("");
    setLostReasonId("");
    setLostTo("");
    setError("");
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!target) return setError("Choose a stage.");
    const text = reason.trim();
    if (needsReason(lead.status, target) && !text) return setError("Add a reason for this stage.");
    const code = duplicateOf.trim().toUpperCase();
    if (target === "duplicate" && !code) return setError("Enter the Lead ID of the lead this one duplicates.");
    if (loss && !lostReasonId) return setError("Choose why the lead was lost.");
    const closure: Closure = target === "duplicate" ? { duplicate_of: code }
      : loss ? { lost_reason_id: lostReasonId, ...(lostTo.trim() ? { lost_to: lostTo.trim() } : {}) } : {};
    setError("");
    setBusy(true);
    const outcome = await move(lead.id, target, text, closure);
    setBusy(false);
    if (!outcome.ok) return onMessage({ id: lead.id, text: outcome.message, failed: true });
    const picked = reasons.items?.find((r) => r.id === lostReasonId);
    close();
    onChanged(target, {
      duplicate_of: code && target === "duplicate" ? { id: "", lead_code: code } : null,
      lost_reason: loss && picked ? { id: picked.id, name: picked.name } : null,
      lost_to: loss ? closure.lost_to ?? null : null,
    });
    onMessage({ id: lead.id, text: "Stage updated.", failed: false });
  }

  if (!open) {
    return (
      <button ref={opener} type="button" className="btn secondary small" aria-label={`Change stage for ${lead.name}`} onClick={() => setOpen(true)}>
        Change stage
      </button>
    );
  }
  const reopening = isClosed(lead.status);
  const required = !!target && needsReason(lead.status, target);
  return (
    <form onSubmit={save} noValidate style={{ display: "grid", gap: 6, minWidth: "9rem" }}>
      <select aria-label={`New stage for ${lead.name}`} value={target} disabled={busy} autoFocus
        onChange={(e) => { setTarget(e.target.value); setError(""); }}>
        <option value="">Choose a stage</option>
        {targets.map((stage) => <option key={stage} value={stage}>{reopening ? `Reopen to ${stageLabel(stage)}` : stageLabel(stage)}</option>)}
      </select>
      {target === "duplicate" && (
        <>
          <label htmlFor={`${reasonId}-dup`} style={{ fontSize: 13 }}>Duplicate of Lead ID (required)</label>
          <input id={`${reasonId}-dup`} value={duplicateOf} disabled={busy} maxLength={20} placeholder="LD-000123" autoComplete="off"
            onChange={(e) => setDuplicateOf(e.target.value)} />
        </>
      )}
      {loss && (reasons.failed ? (
        <div>
          <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>Unable to load the lost reasons.</p>
          <button type="button" className="btn secondary small" onClick={reasons.retry}>Retry</button>
        </div>
      ) : reasons.items === null ? (
        <p className="muted" role="status" style={{ margin: 0, fontSize: 13 }}>Loading lost reasons…</p>
      ) : (
        <>
          <label htmlFor={`${reasonId}-lost`} style={{ fontSize: 13 }}>Lost reason (required)</label>
          <select id={`${reasonId}-lost`} value={lostReasonId} disabled={busy} onChange={(e) => setLostReasonId(e.target.value)}>
            <option value="">Choose a reason</option>
            {reasons.items.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
          <label htmlFor={`${reasonId}-to`} style={{ fontSize: 13 }}>Lost to (optional)</label>
          <input id={`${reasonId}-to`} value={lostTo} disabled={busy} maxLength={160} placeholder="Competitor or chosen destination"
            onChange={(e) => setLostTo(e.target.value)} />
        </>
      ))}
      <label htmlFor={reasonId} style={{ fontSize: 13 }}>{required ? "Reason (required)" : "Reason (optional)"}</label>
      <textarea id={reasonId} rows={2} maxLength={500} value={reason} disabled={busy} onChange={(e) => setReason(e.target.value)} />
      {error && <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>{error}</p>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={close}>Cancel</button>
      </div>
    </form>
  );
}

// tel-004 AC5, tel-015 TM1: the lead's merged timeline (stage changes and every other event), newest first; automatic changes are by
// "System". Loaded when opened, not with the list. ccrm-002 (N5): the lead's notes above it -- the admin writes there.
export function LeadStageHistory({ lead }: { lead: Lead }) {
  const [open, setOpen] = useState(false);
  const [version, setVersion] = useState(0);
  const label = `History for ${lead.name}`;
  const url = `/api/v1/admin/leads/${encodeURIComponent(lead.id)}`;

  return (
    <div style={{ marginTop: 4, minWidth: "min(18rem, 70vw)" }}>
      <button type="button" className="btn secondary small" aria-label={label} aria-expanded={open} onClick={() => setOpen((o) => !o)}>History</button>
      {open && (
        <div style={{ display: "grid", gap: 12, marginTop: 8 }}>
          <LeadNotes url={`${url}/notes`} onAdded={() => setVersion((n) => n + 1)} />
          <LeadTimeline url={`${url}/timeline`} version={version} label={label} />
        </div>
      )}
    </div>
  );
}
