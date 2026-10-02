"use client";

import Link from "next/link";
import { FormEvent, useRef, useState } from "react";
import { sendJson } from "@/lib/apiErrors";
import { AgentApplicationDetail, OFFER_TYPE_LABELS, offerUrl, OfferType, todayIso } from "@/lib/agentApplications";
import { statusLabel } from "@/lib/agentDocuments";

type Props = {
  detail: AgentApplicationDetail;
  onSaved: (d: AgentApplicationDetail, message: string) => void;
  onFailed: (message: string, status?: number) => void;
  onCancel: () => void;
};

// AGN-010 (DEC-SCOPE-054): record or replace the offer -- the whole offer is sent (PUT). Conditions are asked for only for a
// conditional offer; the deadline is the application's offer deadline (O2), so it starts from that value. The offer letter is picked
// from this application's uploaded offer letters (O3). The date limits are the inputs' own min/max; the server checks every rule.
export default function AgentApplicationOfferForm({ detail, onSaved, onFailed, onCancel }: Props) {
  const current = detail.offer;
  const id = detail.id;
  const [type, setType] = useState<OfferType | "">(current?.type ?? "");
  const [date, setDate] = useState(current?.date ?? "");
  const [deadline, setDeadline] = useState(detail.offer_deadline ?? "");
  const [conditions, setConditions] = useState(current?.conditions ?? "");
  const [documentId, setDocumentId] = useState(current?.document?.id ?? "");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // a same-tick second submit sends nothing (QA8-06)
  const letters = detail.offer_letters ?? [];
  // A linked letter beyond the listed ones stays selectable, so an edit never silently unlinks it.
  const options = current?.document && !letters.some((l) => l.id === current.document?.id) ? [current.document, ...letters] : letters;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    let outcome: Awaited<ReturnType<typeof sendJson>>;
    try {
      outcome = await sendJson(offerUrl(id), "PUT", {
        offer_type: type,
        offer_date: date,
        offer_deadline: deadline || null,
        conditions: type === "conditional" ? conditions.trim() || null : null,
        offer_document_id: documentId || null,
        expected_status: detail.status,
      });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
    if (!outcome.ok) return onFailed(outcome.message, outcome.status);
    const next = (outcome.data as { application?: AgentApplicationDetail }).application;
    if (!next) return onFailed("The change could not be confirmed. Reload to see the application.");
    onSaved(next, "Offer saved.");
  }

  return (
    <form className="form" onSubmit={submit} aria-label={current ? "Edit offer" : "Record offer"}>
      <fieldset className="field">
        <legend>Offer type</legend>
        {(Object.keys(OFFER_TYPE_LABELS) as OfferType[]).map((value) => (
          <label key={value}>
            <input id={`offer-type-${id}-${value}`} type="radio" name={`offer-type-${id}`} value={value} required checked={type === value} onChange={() => setType(value)} /> {OFFER_TYPE_LABELS[value]}
          </label>
        ))}
      </fieldset>
      <div className="field">
        <label htmlFor={`offer-date-${id}`}>Offer date</label>
        <input id={`offer-date-${id}`} type="date" required max={todayIso()} value={date} onChange={(e) => setDate(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor={`offer-deadline-${id}`}>Offer deadline (optional)</label>
        <input id={`offer-deadline-${id}`} type="date" min={date || undefined} value={deadline} onChange={(e) => setDeadline(e.target.value)} />
      </div>
      {type === "conditional" && (
        <div className="field">
          <label htmlFor={`offer-conditions-${id}`}>Conditions (required for a conditional offer)</label>
          <textarea
            id={`offer-conditions-${id}`}
            required
            maxLength={2000}
            rows={4}
            aria-describedby={`offer-conditions-hint-${id}`}
            value={conditions}
            onChange={(e) => setConditions(e.target.value)}
          />
          <small id={`offer-conditions-hint-${id}`} className="muted">
            One condition per line, for example: IELTS 6.5 overall.
          </small>
        </div>
      )}
      {options.length ? (
        <div className="field">
          <label htmlFor={`offer-letter-${id}`}>Offer letter (optional)</label>
          <select id={`offer-letter-${id}`} value={documentId} onChange={(e) => setDocumentId(e.target.value)}>
            <option value="">Not attached</option>
            {options.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name} ({statusLabel(l.verification_status)})
              </option>
            ))}
          </select>
        </div>
      ) : (
        <p className="muted">
          No offer letter is uploaded for this application yet. Upload it in <Link href="/overseas/agent/documents">Documents</Link> with the type
          &ldquo;Offer letter&rdquo; and this application selected, then attach it here.
        </p>
      )}
      <div className="actions">
        <button className="btn small" disabled={busy}>
          {busy ? "Saving…" : "Save offer"}
        </button>
        <button type="button" className="btn ghost small" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
