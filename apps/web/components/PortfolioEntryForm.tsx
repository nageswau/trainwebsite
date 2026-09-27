"use client";

import { FormEvent, useRef, useState } from "react";

import InternshipFields from "@/components/InternshipFields";
import { detailMessage, isRequestBody, NOT_COMPLETED } from "@/lib/apiErrors";
import { refocus } from "@/lib/focus";
import { filledInternship, internshipChanges, type InternshipValues, pickInternship } from "@/lib/internship";

// ENH-012 -- one form for all 10 self-entry sections (same shape: title/organization/dates/description),
// mirroring SchoolTransferRequestForm.tsx exactly: per-field useState, busy/inFlight guard, raw fetch(),
// no optimistic UI (waits for the confirmed response, matching this codebase's deliberately conservative
// pattern -- spec §3.8). Used both for create (no entryId) and edit (entryId + initial values) by
// PortfolioPanel.tsx (Task 9).

export default function PortfolioEntryForm({ studentId, section, entryId, initial, onDone, onCancel }: {
  studentId: string; section: string; entryId?: string;
  initial?: { title: string; description: string | null; organization: string | null; date_from: string | null; date_to: string | null } & InternshipValues;
  onDone: () => void; onCancel: () => void;
}) {
  // ENH-021: an internship's title is its Role and its organization its Company (required); its tracking fields ride along.
  const internship = section === "internship";
  const [tracking, setTracking] = useState<InternshipValues>(() => pickInternship(initial));
  const [companyError, setCompanyError] = useState<string | null>(null);
  const [title, setTitle] = useState(initial?.title ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [organization, setOrganization] = useState(initial?.organization ?? "");
  const [dateFrom, setDateFrom] = useState(initial?.date_from ?? "");
  const [dateTo, setDateTo] = useState(initial?.date_to ?? "");
  const [busy, setBusy] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [alert, setAlert] = useState<string | null>(null);
  const inFlight = useRef(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || inFlight.current) return;
    setAlert(null);
    if (!title.trim()) {
      setFieldError(internship ? "Enter the role." : "Enter a title.");
      return;
    }
    setFieldError(null);
    if (internship && !organization.trim()) {
      setCompanyError("Enter the company.");
      return;
    }
    setCompanyError(null);
    inFlight.current = true;
    setBusy(true);
    const body = {
      ...(entryId ? {} : { section }),
      title: title.trim(),
      description: description.trim() || null,
      organization: organization.trim() || null,
      date_from: dateFrom || null,
      date_to: dateTo || null,
      // ENH-021 I6: only changed tracking fields on edit, so a basic edit never needs the Platinum-only gate.
      ...(internship ? (entryId ? internshipChanges(pickInternship(initial), tracking) : filledInternship(tracking)) : {}),
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
        <label htmlFor="pf-title">{internship ? "Role" : "Title"}</label>
        <input id="pf-title" className="search" value={title} disabled={busy} aria-invalid={fieldError ? true : undefined} aria-describedby={fieldError ? "pf-title-error" : undefined} onChange={(e) => setTitle(e.target.value)} />
        {fieldError && <span id="pf-title-error" className="form-error">{fieldError}</span>}
      </div>
      <div className="field">
        <label htmlFor="pf-organization">{internship ? "Company" : "Organization (optional)"}</label>
        <input id="pf-organization" className="search" value={organization} disabled={busy} aria-invalid={companyError ? true : undefined} aria-describedby={companyError ? "pf-organization-error" : undefined} onChange={(e) => setOrganization(e.target.value)} />
        {companyError && <span id="pf-organization-error" className="form-error">{companyError}</span>}
      </div>
      <div className="field">
        <label htmlFor="pf-date-from">Start date (optional)</label>
        <input id="pf-date-from" type="date" className="search" value={dateFrom} disabled={busy} onChange={(e) => setDateFrom(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="pf-date-to">End date (optional)</label>
        <input id="pf-date-to" type="date" className="search" value={dateTo} disabled={busy} onChange={(e) => setDateTo(e.target.value)} />
      </div>
      {internship && <InternshipFields values={tracking} onChange={setTracking} disabled={busy} />}
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
