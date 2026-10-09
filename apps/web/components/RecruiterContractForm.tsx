"use client";
import { type FormEvent, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmPipeline";
import {
  companyContractsUrl, type Contract, contractConflict, type ContractFields, contractOverlap, type ContractStatus, FEE_BASES, FIELD_LABEL, isContractBody,
  SETTABLE_CONTRACT_STATUSES,
} from "@/lib/recruiterContracts";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const EXPIRED_HINT = "Expired. Start a renewal to change the status, or correct the end date.";
const SIGNED_HINT = "Signed and Active need the contract document on file. Upload it first.";
const TERMS = ["payment_terms", "replacement_policy"] as const;

const fieldsOf = (c: Contract | null): ContractFields => ({
  agreement_type: c?.agreement_type ?? "", start_date: c?.start_date ?? "", end_date: c?.end_date ?? "", fee_basis: c?.fee_basis ?? "",
  fee_value: c?.fee_value ?? "", payment_terms: c?.payment_terms ?? "", replacement_policy: c?.replacement_policy ?? "",
});

// rec-030 (spec §4): start (contract = null, a first contract or a renewal) or edit the current contract. Required markers follow the
// chosen status (Active needs both dates) -- fast feedback only; the server enforces every rule and its 422 lands on the field. An edit
// sends only what changed, plus `from_status` with a status change and the version it showed. A 409 with a code goes to the section,
// which reloads; an overlap (CT8) stays on the form.
export default function RecruiterContractForm({ companyId, contract, onSaved, onCancel, onConflict }: {
  companyId: string; contract: Contract | null; onSaved: (c: Contract) => void; onCancel: () => void; onConflict: (text: string) => void;
}) {
  const expired = contract?.status === "expired";
  const [status, setStatus] = useState<ContractStatus>(contract?.status ?? "discussion");
  const [fields, setFields] = useState<ContractFields>(fieldsOf(contract));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // a double click sends nothing twice
  const focus = useFocusAfterRender();
  const id = (part: string) => `contract-${companyId}-${part}`;
  const needsWindow = status === "active";
  const set = (f: keyof ContractFields, value: string) => setFields((current) => ({ ...current, [f]: value }));
  const noDocument = !contract?.contract_document;

  function body(): Record<string, unknown> {
    if (!contract) return { status, ...Object.fromEntries(Object.entries(fields).filter(([, v]) => v.trim() !== "")) };
    const before = fieldsOf(contract);
    const changed = Object.entries(fields).filter(([f, v]) => v !== before[f as keyof ContractFields]);
    const statusChange = !expired && status !== contract.status ? { status, from_status: contract.status } : {};
    return { ...statusChange, ...Object.fromEntries(changed.map(([f, v]) => [f, v.trim() === "" ? null : v])), expected_updated_at: contract.updated_at };
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    setErrors({});
    try {
      const outcome = await sendJson(companyContractsUrl(companyId), contract ? "PATCH" : "POST", body());
      if (outcome.ok && isContractBody(outcome.data)) return onSaved(outcome.data.contract);
      if (outcome.ok) return setFailure("Unable to save the contract.");
      const conflict = contractConflict(outcome.detail);
      if (conflict !== null) return onConflict(conflict);
      const found = fieldErrors(outcome.detail);
      if (Object.keys(found).length) {
        setErrors(found);
        return focus(id(Object.keys(found)[0]));
      }
      setFailure(contractOverlap(outcome.detail) ?? outcome.message);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  const describedBy = (f: string, hint?: string) => [errors[f] ? id(`${f}-error`) : null, hint ?? null].filter(Boolean).join(" ") || undefined;
  const error = (f: string) => (errors[f] ? <p id={id(`${f}-error`)} className="form-error">{errors[f]}</p> : null);
  const text = (f: "agreement_type", max: number) => (
    <div className="field">
      <label htmlFor={id(f)}>{FIELD_LABEL[f]}</label>
      <input id={id(f)} value={fields[f]} onChange={(e) => set(f, e.target.value)} maxLength={max} aria-describedby={describedBy(f)} />
      {error(f)}
    </div>
  );

  return (
    <form className="form-grid" onSubmit={submit} aria-label={contract ? "Edit contract" : "Start contract"}>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      <div className="field">
        <label htmlFor={id("status")}>{FIELD_LABEL.status}</label>
        <select id={id("status")} value={status} onChange={(e) => setStatus(e.target.value as ContractStatus)} disabled={expired}
          aria-describedby={describedBy("status", expired ? id("status-hint") : noDocument ? id("signed-hint") : undefined)}>
          {expired && <option value="expired">Expired</option>}
          {SETTABLE_CONTRACT_STATUSES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
        {expired ? <p id={id("status-hint")} className="muted">{EXPIRED_HINT}</p> : noDocument && <p id={id("signed-hint")} className="muted">{SIGNED_HINT}</p>}
        {error("status")}
      </div>
      {text("agreement_type", 100)}
      {(["start_date", "end_date"] as const).map((f) => (
        <div className="field" key={f}>
          <label htmlFor={id(f)}>{FIELD_LABEL[f]}{needsWindow ? " (required)" : ""}</label>
          <input id={id(f)} type="date" value={fields[f]} onChange={(e) => set(f, e.target.value)} required={needsWindow} aria-describedby={describedBy(f)} />
          {error(f)}
        </div>
      ))}
      <div className="field">
        <label htmlFor={id("fee_basis")}>{FIELD_LABEL.fee_basis}</label>
        <select id={id("fee_basis")} value={fields.fee_basis} onChange={(e) => set("fee_basis", e.target.value)} aria-describedby={describedBy("fee_basis")}>
          <option value="">Not agreed yet</option>
          {FEE_BASES.map((b) => <option key={b.key} value={b.key}>{b.label}</option>)}
        </select>
        {error("fee_basis")}
      </div>
      <div className="field">
        <label htmlFor={id("fee_value")}>{FIELD_LABEL.fee_value}{fields.fee_basis === "percent_of_ctc" ? " (%)" : fields.fee_basis === "fixed" ? " (₹)" : ""}</label>
        <input id={id("fee_value")} inputMode="decimal" value={fields.fee_value} onChange={(e) => set("fee_value", e.target.value)} aria-describedby={describedBy("fee_value")} />
        {error("fee_value")}
      </div>
      {TERMS.map((f) => (
        <div className="field" key={f}>
          <label htmlFor={id(f)}>{FIELD_LABEL[f]}</label>
          <textarea id={id(f)} value={fields[f]} onChange={(e) => set(f, e.target.value)} maxLength={2000} rows={3} aria-describedby={describedBy(f)} />
          {error(f)}
        </div>
      ))}
      <div className="actions">
        <button id={id("save")} type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : contract ? "Save contract" : "Start contract"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}
