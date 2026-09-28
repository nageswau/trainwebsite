"use client";

import { FormEvent, useRef, useState } from "react";

import { CERT_STATUS_LABEL, type CertificationFields } from "@/components/CertificationDetails";
import { detailMessage, isRequestBody, NOT_COMPLETED } from "@/lib/apiErrors";
import { refocus } from "@/lib/focus";

type CertErrors = { status?: string; number?: string; issued?: string };

// ENH-012 -- one form for all 10 self-entry sections (same shape: title/organization/dates/description),
// mirroring SchoolTransferRequestForm.tsx exactly: per-field useState, busy/inFlight guard, raw fetch(),
// no optimistic UI (waits for the confirmed response, matching this codebase's deliberately conservative
// pattern -- spec §3.8). Used both for create (no entryId) and edit (entryId + initial values) by
// PortfolioPanel.tsx (Task 9).

export default function PortfolioEntryForm({ studentId, section, entryId, initial, onDone, onCancel }: {
  studentId: string; section: string; entryId?: string;
  initial?: { title: string; description: string | null; organization: string | null; date_from: string | null; date_to: string | null } & CertificationFields;
  onDone: () => void; onCancel: () => void;
}) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [organization, setOrganization] = useState(initial?.organization ?? "");
  const [dateFrom, setDateFrom] = useState(initial?.date_from ?? "");
  const [dateTo, setDateTo] = useState(initial?.date_to ?? "");
  // ENH-024 (spec §6): the Skill India tag is chosen only when adding a certification; an edit shows it as text (D8).
  const [skillIndia, setSkillIndia] = useState(initial?.certification_type === "skill_india");
  const [certStatus, setCertStatus] = useState(initial?.certification_status ?? "");
  const [certNumber, setCertNumber] = useState(initial?.certificate_number ?? "");
  const [issuedOn, setIssuedOn] = useState(initial?.issued_on ?? "");
  const [busy, setBusy] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [certErrors, setCertErrors] = useState<CertErrors>({});
  const [alert, setAlert] = useState<string | null>(null);
  const inFlight = useRef(false);
  const offerSkillIndia = !entryId && section === "certification";

  // ENH-024 D6, mirrored for a fast answer; the server stays authoritative.
  function checkCertification(): CertErrors {
    if (!skillIndia) return {};
    const errors: CertErrors = {};
    if (!certStatus) errors.status = "Choose a status.";
    if (certStatus === "certified" && !certNumber.trim()) errors.number = "Enter the certificate number.";
    if (certStatus === "certified" && !issuedOn) errors.issued = "Enter the issue date.";
    return errors;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || inFlight.current) return;
    setAlert(null);
    const titleError = title.trim() ? null : "Enter a title.";
    const errors = checkCertification();
    setFieldError(titleError);
    setCertErrors(errors);
    const firstInvalid = titleError ? "pf-title" : errors.status ? "pf-cert-status" : errors.number ? "pf-cert-number" : errors.issued ? "pf-cert-issued" : null;
    if (firstInvalid) {
      refocus(firstInvalid);
      return;
    }
    inFlight.current = true;
    setBusy(true);
    const certification = skillIndia
      ? { ...(entryId ? {} : { certification_type: "skill_india" }), certification_status: certStatus, certificate_number: certNumber.trim() || null, issued_on: issuedOn || null }
      : {};
    const body = {
      ...(entryId ? {} : { section }),
      title: title.trim(),
      description: description.trim() || null,
      organization: organization.trim() || null,
      date_from: dateFrom || null,
      date_to: dateTo || null,
      ...certification,
    };
    const url = entryId ? `/api/v1/school/students/${studentId}/portfolio/entries/${entryId}` : `/api/v1/school/students/${studentId}/portfolio/entries`;
    let response: Response;
    try {
      response = await fetch(url, { method: entryId ? "PATCH" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    } catch {
      inFlight.current = false;
      setBusy(false);
      setAlert(NOT_COMPLETED);
      refocus("pf-save-btn");
      return;
    }
    const data = await response.json().catch(() => null);
    inFlight.current = false;
    setBusy(false);
    if (!response.ok) {
      setAlert(detailMessage(data?.detail));
      refocus("pf-save-btn");
      return;
    }
    if (!isRequestBody(data)) {
      setAlert("The save could not be confirmed. Please check the list before retrying.");
      refocus("pf-save-btn");
      return;
    }
    onDone();
  }

  return (
    <form className="form" onSubmit={submit} noValidate>
      <div className="field">
        <label htmlFor="pf-title">Title</label>
        <input id="pf-title" className="search" value={title} disabled={busy} aria-invalid={fieldError ? true : undefined} aria-describedby={fieldError ? "pf-title-error" : undefined} onChange={(e) => setTitle(e.target.value)} />
        {fieldError && <span id="pf-title-error" className="form-error">{fieldError}</span>}
      </div>
      {offerSkillIndia && (
        <div className="field">
          <label htmlFor="pf-skill-india">
            <input id="pf-skill-india" type="checkbox" checked={skillIndia} disabled={busy} onChange={(e) => setSkillIndia(e.target.checked)} /> Skill India certification
          </label>
        </div>
      )}
      {entryId && skillIndia && <p className="muted">Skill India certification</p>}
      <div className="field">
        <label htmlFor="pf-organization">{skillIndia ? "Issuing body (optional)" : "Organization (optional)"}</label>
        <input id="pf-organization" className="search" value={organization} disabled={busy} onChange={(e) => setOrganization(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="pf-date-from">Start date (optional)</label>
        <input id="pf-date-from" type="date" className="search" value={dateFrom} disabled={busy} onChange={(e) => setDateFrom(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="pf-date-to">End date (optional)</label>
        <input id="pf-date-to" type="date" className="search" value={dateTo} disabled={busy} onChange={(e) => setDateTo(e.target.value)} />
      </div>
      {skillIndia && (
        <fieldset className="field">
          <legend>Skill India details</legend>
          <div className="field">
            <label htmlFor="pf-cert-status">Status</label>
            <select id="pf-cert-status" className="search" value={certStatus} disabled={busy} aria-invalid={certErrors.status ? true : undefined} aria-describedby={certErrors.status ? "pf-cert-status-error" : undefined} onChange={(e) => setCertStatus(e.target.value)}>
              <option value="">Choose status</option>
              {Object.entries(CERT_STATUS_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            {certErrors.status && <span id="pf-cert-status-error" className="form-error">{certErrors.status}</span>}
          </div>
          <div className="field">
            <label htmlFor="pf-cert-number">Certificate number</label>
            <input id="pf-cert-number" className="search" maxLength={100} value={certNumber} disabled={busy} aria-invalid={certErrors.number ? true : undefined} aria-describedby={certErrors.number ? "pf-cert-number-hint pf-cert-number-error" : "pf-cert-number-hint"} onChange={(e) => setCertNumber(e.target.value)} />
            <span id="pf-cert-number-hint" className="muted">Required once certified.</span>
            {certErrors.number && <span id="pf-cert-number-error" className="form-error">{certErrors.number}</span>}
          </div>
          <div className="field">
            <label htmlFor="pf-cert-issued">Issue date</label>
            <input id="pf-cert-issued" type="date" className="search" value={issuedOn} disabled={busy} aria-invalid={certErrors.issued ? true : undefined} aria-describedby={certErrors.issued ? "pf-cert-issued-hint pf-cert-issued-error" : "pf-cert-issued-hint"} onChange={(e) => setIssuedOn(e.target.value)} />
            <span id="pf-cert-issued-hint" className="muted">Required once certified.</span>
            {certErrors.issued && <span id="pf-cert-issued-error" className="form-error">{certErrors.issued}</span>}
          </div>
        </fieldset>
      )}
      <div className="field">
        <label htmlFor="pf-description">Description (optional)</label>
        <textarea id="pf-description" className="search" rows={3} maxLength={2000} value={description} disabled={busy} onChange={(e) => setDescription(e.target.value)} />
      </div>
      <button id="pf-save-btn" type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
      <button type="button" className="btn secondary" disabled={busy} onClick={onCancel}>Cancel</button>
      {alert && <div role="alert" className="form-error">{alert}</div>}
    </form>
  );
}
