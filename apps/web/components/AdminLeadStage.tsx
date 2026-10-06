"use client";

import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { formatDate } from "@/lib/formatDate";
import { isClosed, needsReason, personTargets, stageLabel } from "@/lib/leadStages";
import { getPage } from "@/lib/telecallerCatalogue";

type Lead = { id: string; name: string; status: string };
type Message = { id: string; text: string; failed: boolean };
type HistoryRow = {
  id: string; from_stage: string; from_label: string; to_stage: string; to_label: string; event: string;
  actor: { id: string; full_name: string } | null; reason: string | null; created_at: string;
};

// tel-004 (spec §6, T25): an admin's stage move. Only the moves the API accepts are offered (lib/leadStages mirrors the rules); a
// closed outcome or a reopen needs a reason, checked here first so the admin isn't sent a 422. The API stays the authority.
export function LeadStageControl({ lead, onChanged, onMessage }: { lead: Lead; onChanged: (status: string) => void; onMessage: (m: Message) => void }) {
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
  const targets = personTargets(lead.status, true);
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
    const outcome = await sendJson(`/api/v1/admin/leads/${lead.id}`, "PATCH", text ? { status: target, reason: text } : { status: target });
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

// tel-004 AC5: the lead's stage changes, oldest first; automatic changes are by "System". Loaded when opened, not with the list.
export function LeadStageHistory({ lead }: { lead: Lead }) {
  const [rows, setRows] = useState<HistoryRow[] | null>(null);
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState(false);
  const label = `Stage history for ${lead.name}`;

  function toggle() {
    if (open) return setOpen(false);
    setOpen(true);
    setFailed(false);
    setRows(null);
    getPage<HistoryRow>(`/api/v1/admin/leads/${lead.id}/stage-history?limit=100`).then((page) => setRows(page.items), () => setFailed(true));
  }

  return (
    <div style={{ marginTop: 4 }}>
      <button type="button" className="btn secondary small" aria-label={label} aria-expanded={open} onClick={toggle}>History</button>
      {open && (failed ? (
        <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the history.</p>
      ) : rows === null ? (
        <p className="muted" style={{ fontSize: 13 }}>Loading…</p>
      ) : rows.length === 0 ? (
        <p className="muted" style={{ fontSize: 13 }}>No stage changes yet.</p>
      ) : (
        <ol aria-label={label} style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 13, minWidth: "9rem" }}>
          {rows.map((h) => (
            <li key={h.id}>
              <strong>{h.from_label} → {h.to_label}</strong>
              <div className="muted">{h.actor ? h.actor.full_name : "System"} · {formatDate(h.created_at, true)}</div>
              {h.reason && <div>{h.reason}</div>}
            </li>
          ))}
        </ol>
      ))}
    </div>
  );
}
