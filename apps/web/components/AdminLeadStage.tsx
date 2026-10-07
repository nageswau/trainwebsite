"use client";

import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import LeadTimeline from "@/components/LeadTimeline";
import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import { isClosed, needsReason, personTargets, stageLabel } from "@/lib/leadStages";

type Lead = { id: string; name: string; status: string };
type Message = { id: string; text: string; failed: boolean };

const adminMove = (id: string, target: string, reason: string) =>
  sendJson(`/api/v1/admin/leads/${id}`, "PATCH", reason ? { status: target, reason } : { status: target });

// tel-004 (spec §6, T25): an admin's stage move. Only the moves the API accepts are offered (lib/leadStages mirrors the rules); a
// closed outcome or a reopen needs a reason, checked here first so the admin isn't sent a 422. The API stays the authority.
// tel-008: the lead detail reuses it with the telecaller route (`move`); a telecaller can't reopen a closed lead (`canReopen`).
export function LeadStageControl({ lead, onChanged, onMessage, move = adminMove, canReopen = true }: {
  lead: Lead; onChanged: (status: string) => void; onMessage: (m: Message) => void;
  move?: (id: string, target: string, reason: string) => Promise<SendOutcome>; canReopen?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const reasonId = useId();
  const opener = useRef<HTMLButtonElement>(null);
  const refocus = useRef(false);
  // Browser QA-01: closing the form (Save or Cancel) unmounts it, so put keyboard focus back on the button that opened it.
  useEffect(() => {
    if (!open && refocus.current) {
      refocus.current = false;
      opener.current?.focus();
    }
  }, [open]);
  const targets = personTargets(lead.status, canReopen);
  if (targets.length === 0) return null;

  function close() {
    refocus.current = true;
    setOpen(false);
    setTarget("");
    setReason("");
    setError("");
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!target) return setError("Choose a stage.");
    const text = reason.trim();
    if (needsReason(lead.status, target) && !text) return setError("Add a reason for this stage.");
    setError("");
    setBusy(true);
    const outcome = await move(lead.id, target, text);
    setBusy(false);
    if (!outcome.ok) return onMessage({ id: lead.id, text: outcome.message, failed: true });
    close();
    onChanged(target);
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
// "System". Loaded when opened, not with the list.
export function LeadStageHistory({ lead }: { lead: Lead }) {
  const [open, setOpen] = useState(false);
  const label = `History for ${lead.name}`;

  return (
    <div style={{ marginTop: 4, minWidth: "min(18rem, 70vw)" }}>
      <button type="button" className="btn secondary small" aria-label={label} aria-expanded={open} onClick={() => setOpen((o) => !o)}>History</button>
      {open && <LeadTimeline url={`/api/v1/admin/leads/${encodeURIComponent(lead.id)}/timeline`} version={0} label={label} />}
    </div>
  );
}
