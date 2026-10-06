"use client";
import { type FormEvent, useRef, useState } from "react";

import BdmConfirm from "@/components/BdmConfirm";
import { sendJson } from "@/lib/apiErrors";
import { FIELD_LABEL, isMouBody, type Mou, mouConflict, type MouFields, type MouStatus, orgMouUrl, SETTABLE_MOU_STATUSES } from "@/lib/bdmMous";
import { fieldErrors } from "@/lib/bdmPipeline";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const DATES = ["proposal_sent_on", "signed_on", "valid_from", "valid_until"] as const;
const EXPIRED_HINT = "Expired. Start a renewal to change the status, or correct the valid-until date.";

const fieldsOf = (m: Mou | null): MouFields => ({
  proposal_sent_on: m?.proposal_sent_on ?? "", signed_on: m?.signed_on ?? "", valid_from: m?.valid_from ?? "", valid_until: m?.valid_until ?? "",
  reference: m?.reference ?? "", notes: m?.notes ?? "",
});

// bdm-005 (spec §8): start (mou = null) or edit the current MoU. Required markers follow the chosen status (Signed / Active need the
// signed date, Active the window) -- fast feedback only; the server enforces every rule and its 422 lands on the field. An edit sends
// only what changed, plus `from_status` with a status change. A Signed that moves the pipeline (D28) is confirmed first. A 409 with a
// code (changed meanwhile, expired, Lost) goes to the card, which reloads.
export default function BdmMouForm({ orgId, mou, onSaved, onCancel, onConflict }: {
  orgId: string; mou: Mou | null; onSaved: (m: Mou) => void; onCancel: () => void; onConflict: (text: string) => void;
}) {
  const expired = mou?.status === "expired";
  const [status, setStatus] = useState<MouStatus>(mou?.status ?? "prospect");
  const [fields, setFields] = useState<MouFields>(fieldsOf(mou));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // a double click sends nothing twice
  const focus = useFocusAfterRender();
  const id = (part: string) => `mou-${orgId}-${part}`;
  const needsSigned = status === "signed" || status === "active";
  const needsWindow = status === "active";
  const required = (f: keyof MouFields) => (f === "signed_on" && needsSigned) || ((f === "valid_from" || f === "valid_until") && needsWindow);
  const set = (f: keyof MouFields, value: string) => setFields((current) => ({ ...current, [f]: value }));

  function body(): Record<string, unknown> {
    if (!mou) return { status, ...Object.fromEntries(Object.entries(fields).filter(([, v]) => v.trim() !== "")) };
    const before = fieldsOf(mou);
    const changed = Object.entries(fields).filter(([f, v]) => v !== before[f as keyof MouFields]);
    const statusChange = !expired && status !== mou.status ? { status, from_status: mou.status } : {};
    return { ...statusChange, ...Object.fromEntries(changed.map(([f, v]) => [f, v.trim() === "" ? null : v])) };
  }

  async function send() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    setErrors({});
    try {
      const outcome = await sendJson(orgMouUrl(orgId), mou ? "PATCH" : "POST", body());
      if (outcome.ok && isMouBody(outcome.data)) return onSaved(outcome.data.mou);
      if (outcome.ok) return setFailure("Unable to save the MoU.");
      const conflict = mouConflict(outcome.detail);
      if (conflict !== null) return onConflict(conflict);
      const found = fieldErrors(outcome.detail);
      if (Object.keys(found).length) {
        setErrors(found);
        return focus(id(Object.keys(found)[0]));
      }
      setFailure(outcome.message);
    } finally {
      inFlight.current = false;
      setBusy(false);
      setConfirming(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const signing = status === "signed" && mou?.status !== "signed" && mou?.pipeline_on_sign;
    if (signing) return setConfirming(true);
    void send();
  }
  const describedBy = (f: string) => (errors[f] ? id(`${f}-error`) : undefined);
  const error = (f: string) => (errors[f] ? <p id={id(`${f}-error`)} className="form-error">{errors[f]}</p> : null);

  return (
    <form className="form-grid" onSubmit={submit} aria-label={mou ? "Edit MoU" : "Start MoU"}>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      <div className="field">
        <label htmlFor={id("status")}>{FIELD_LABEL.status}</label>
        <select id={id("status")} value={status} onChange={(e) => setStatus(e.target.value as MouStatus)} disabled={expired} aria-describedby={expired ? id("status-hint") : describedBy("status")}>
          {expired && <option value="expired">Expired</option>}
          {SETTABLE_MOU_STATUSES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
        {expired && <p id={id("status-hint")} className="muted">{EXPIRED_HINT}</p>}
        {error("status")}
      </div>
      {DATES.map((f) => (
        <div className="field" key={f}>
          <label htmlFor={id(f)}>{FIELD_LABEL[f]}{required(f) ? " (required)" : ""}</label>
          <input id={id(f)} type="date" value={fields[f]} onChange={(e) => set(f, e.target.value)} required={required(f)} aria-describedby={describedBy(f)} />
          {error(f)}
        </div>
      ))}
      <div className="field">
        <label htmlFor={id("reference")}>{FIELD_LABEL.reference}</label>
        <input id={id("reference")} value={fields.reference} onChange={(e) => set("reference", e.target.value)} maxLength={100} aria-describedby={describedBy("reference")} />
        {error("reference")}
      </div>
      <div className="field">
        <label htmlFor={id("notes")}>{FIELD_LABEL.notes}</label>
        <textarea id={id("notes")} value={fields.notes} onChange={(e) => set("notes", e.target.value)} maxLength={2000} rows={3} aria-describedby={describedBy("notes")} />
        {error("notes")}
      </div>
      {confirming && mou?.pipeline_on_sign ? (
        <BdmConfirm label="Confirm signing" confirmText="Yes, save" cancelText="Not yet" busyText="Saving…" busy={busy} onConfirm={() => void send()} onCancel={() => setConfirming(false)}>
          This also moves the pipeline to {mou.pipeline_on_sign.label}.
        </BdmConfirm>
      ) : (
        <div className="actions">
          <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : mou ? "Save MoU" : "Start MoU"}</button>
          <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
        </div>
      )}
    </form>
  );
}
