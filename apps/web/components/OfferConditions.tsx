"use client";

import { FormEvent, useRef, useState } from "react";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import {
  ApplicationOffer,
  CONDITION_OWNER_LABELS,
  CONDITION_STATUS_LABELS,
  conditionEvidenceUrl,
  conditionProblem,
  conditionsUrl,
  conditionUrl,
  ConditionOwner,
  ConditionStatus,
  documentDownloadUrl,
  OfferCondition,
  OfferDocument,
} from "@/lib/applicationOffers";

type Props = {
  applicationId: string;
  offer: ApplicationOffer;
  agency: boolean;
  evidence: OfferDocument[];
  onSaved: (message: string) => void;
  onRecordUnconditional: () => void;
};

// ccrm-024 (DEC-SCOPE-261): the conditions an offer carries. Only the current offer's can change (C3); met needs evidence (C2), waived
// and failed a note (C5). Once every condition is met or waived the counselor is prompted -- nothing changes on its own (C4).
export default function OfferConditions({ applicationId, offer, agency, evidence, onSaved, onRecordUnconditional }: Props) {
  const [editing, setEditing] = useState<string | null>(null); // a condition id, "new", or null
  const [openError, setOpenError] = useState<string | null>(null);
  const items = offer.condition_items ?? [];
  const editable = offer.status === "active";
  const summary = offer.conditions_summary;
  if (items.length === 0 && !editable) return null;

  async function openEvidence(document: OfferDocument) {
    setOpenError(null);
    const outcome = await sendRequest(documentDownloadUrl(document.id), {});
    if (!outcome.ok) return setOpenError(outcome.message);
    window.open(String(outcome.data.url), "_blank", "noopener,noreferrer");
  }

  function saved(message: string) {
    setEditing(null);
    onSaved(message);
  }

  const form = (condition: OfferCondition | null) => (
    <ConditionForm applicationId={applicationId} offerId={offer.id} condition={condition} agency={agency} evidence={evidence} onSaved={saved} onCancel={() => setEditing(null)} />
  );

  return (
    <div style={{ marginTop: 8 }}>
      <strong id={`conditions-${offer.id}`} style={{ fontSize: 13 }}>
        Conditions
      </strong>
      {summary && summary.total > 0 && (
        <span className="muted">
          {" "}
          · {summary.satisfied} of {summary.total} conditions satisfied
        </span>
      )}
      {items.length > 0 && (
        <ul aria-labelledby={`conditions-${offer.id}`} style={{ listStyle: "none", padding: 0, margin: "4px 0 0", display: "grid", gap: 6 }}>
          {items.map((item) => (
            <li key={item.id} style={{ borderTop: "1px solid var(--border, #e5e7eb)", paddingTop: 6 }}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                <span className="badge">{item.status_label}</span>
                <span style={{ whiteSpace: "pre-line" }}>{item.description}</span>
              </div>
              <p className="muted" style={{ margin: "2px 0 0" }}>
                Owner: {item.owner_label}
                {item.due_date && ` · Due ${item.due_date}`}
              </p>
              {item.note && <p style={{ margin: "2px 0 0" }}>Note: {item.note}</p>}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
                {item.evidence && (
                  <button type="button" className="btn ghost small" onClick={() => openEvidence(item.evidence as OfferDocument)}>
                    Open evidence<span className="visually-hidden"> {item.evidence.name} (opens in a new tab)</span>
                  </button>
                )}
                {editable && editing === null && (
                  <button type="button" className="btn ghost small" onClick={() => setEditing(item.id)}>
                    Update condition<span className="visually-hidden"> {item.description}</span>
                  </button>
                )}
              </div>
              {editing === item.id && form(item)}
            </li>
          ))}
        </ul>
      )}
      {openError && <div className="form-error" role="status">{openError}</div>}
      {editable && summary?.all_satisfied && editing === null && (
        <div style={{ marginTop: 6 }}>
          <p style={{ margin: 0 }}>All conditions satisfied — the university may now issue an unconditional offer.</p>
          <button type="button" className="btn small" style={{ marginTop: 4 }} onClick={onRecordUnconditional}>
            Record unconditional offer
          </button>
        </div>
      )}
      {editable && editing === "new" && form(null)}
      {editable && editing === null && (
        <button type="button" className="btn ghost small" style={{ marginTop: 6 }} onClick={() => setEditing("new")}>
          Add condition
        </button>
      )}
    </div>
  );
}

type FormProps = {
  applicationId: string;
  offerId: string;
  condition: OfferCondition | null;
  agency: boolean;
  evidence: OfferDocument[];
  onSaved: (message: string) => void;
  onCancel: () => void;
};

function ConditionForm({ applicationId, offerId, condition, agency, evidence, onSaved, onCancel }: FormProps) {
  const key = `${offerId}-${condition?.id ?? "new"}`;
  const [description, setDescription] = useState(condition?.description ?? "");
  const [owner, setOwner] = useState<ConditionOwner>(condition?.owner ?? "student");
  const [due, setDue] = useState(condition?.due_date ?? "");
  const [status, setStatus] = useState<ConditionStatus>(condition?.status ?? "open");
  const [evidenceId, setEvidenceId] = useState(condition?.evidence?.id ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState(condition?.note ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // a same-tick second submit sends nothing
  const owners = (Object.keys(CONDITION_OWNER_LABELS) as ConditionOwner[]).filter((value) => value !== "agent" || agency || condition?.owner === "agent");
  const choices = condition?.evidence && !evidence.some((d) => d.id === condition.evidence?.id) ? [condition.evidence, ...evidence] : evidence;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    const problem = condition ? conditionProblem(status, Boolean(evidenceId || file), note) : null;
    if (problem) return setError(problem);
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const base = { description: description.trim(), owner, due_date: due || null };
      if (!condition) {
        const outcome = await sendJson(conditionsUrl(applicationId, offerId), "POST", base);
        return outcome.ok ? onSaved("Condition added.") : setError(outcome.message);
      }
      let documentId = evidenceId;
      if (file) {
        const upload = new FormData();
        upload.set("file", file);
        const uploaded = await sendRequest(conditionEvidenceUrl(applicationId), { method: "POST", body: upload });
        if (!uploaded.ok) return setError(uploaded.message);
        documentId = String((uploaded.data.document as OfferDocument).id);
      }
      const outcome = await sendJson(conditionUrl(applicationId, offerId, condition.id), "PATCH", { ...base, status, evidence_document_id: documentId || null, note: note.trim() || null });
      if (!outcome.ok) return setError(outcome.message);
      onSaved(outcome.data.changed === false ? "Nothing changed." : "Condition updated.");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <form className="form" onSubmit={submit} aria-label={condition ? "Update condition" : "Add condition"} style={{ marginTop: 6 }}>
      <div className="field">
        <label htmlFor={`condition-text-${key}`}>Condition</label>
        <textarea id={`condition-text-${key}`} rows={2} maxLength={1000} required value={description} onChange={(e) => setDescription(e.target.value)} />
      </div>
      <div className="form-grid">
        <div className="field">
          <label htmlFor={`condition-owner-${key}`}>Owner</label>
          <select id={`condition-owner-${key}`} value={owner} onChange={(e) => setOwner(e.target.value as ConditionOwner)}>
            {owners.map((value) => (
              <option key={value} value={value}>
                {CONDITION_OWNER_LABELS[value]}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor={`condition-due-${key}`}>Due date (optional)</label>
          <input id={`condition-due-${key}`} type="date" value={due} onChange={(e) => setDue(e.target.value)} />
        </div>
        {condition && (
          <div className="field">
            <label htmlFor={`condition-status-${key}`}>Status</label>
            <select id={`condition-status-${key}`} value={status} onChange={(e) => setStatus(e.target.value as ConditionStatus)}>
              {(Object.keys(CONDITION_STATUS_LABELS) as ConditionStatus[]).map((value) => (
                <option key={value} value={value}>
                  {CONDITION_STATUS_LABELS[value]}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
      {condition && (
        <>
          {choices.length > 0 && (
            <div className="field">
              <label htmlFor={`condition-evidence-${key}`}>Evidence</label>
              <select id={`condition-evidence-${key}`} value={evidenceId} disabled={file !== null} onChange={(e) => setEvidenceId(e.target.value)}>
                <option value="">None</option>
                {choices.map((document) => (
                  <option key={document.id} value={document.id}>
                    {document.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="field">
            <label htmlFor={`condition-file-${key}`}>{choices.length ? "Or upload evidence (PDF or image)" : "Upload evidence (PDF or image)"}</label>
            <input id={`condition-file-${key}`} type="file" accept="application/pdf,image/png,image/jpeg,image/webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </div>
          <div className="field">
            <label htmlFor={`condition-note-${key}`}>Note {status === "waived" || status === "failed" ? "(required)" : "(optional)"}</label>
            <textarea id={`condition-note-${key}`} rows={2} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
        </>
      )}
      {error && (
        <div className="form-error" role="status" aria-live="polite">
          {error}
        </div>
      )}
      <div className="actions" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button className="btn small" disabled={busy}>
          {busy ? "Saving…" : "Save condition"}
        </button>
        <button type="button" className="btn ghost small" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
