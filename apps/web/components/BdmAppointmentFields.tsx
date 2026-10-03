"use client";
import { useEffect, useState } from "react";

import type { BdmType } from "@/lib/bdm";
import { appointmentTypes, DURATIONS, formatMinutes, nowIstInput, TYPE_LABEL } from "@/lib/bdmAppointments";
import type { OrgContact } from "@/lib/bdmOrganizations";

// bdm-006 (R-F6): the booking fields in four fieldsets. Presentational: the form owns the state and the submit.
export type FieldValues = { contactId: string; when: string; duration: number; type: string; location: string; purpose: string; remarks: string; leads: string; revenue: string };

export default function BdmAppointmentFields({
  values,
  set,
  bdmType,
  contacts,
  contactsLoading,
  showWhen,
  contactRequired = true,
}: {
  values: FieldValues;
  set: <K extends keyof FieldValues>(key: K, value: FieldValues[K]) => void;
  bdmType: BdmType;
  contacts: OrgContact[] | null;
  contactsLoading: boolean;
  showWhen: boolean;
  contactRequired?: boolean;
}) {
  // `min` is read after mount: a server-rendered value can differ from the browser's across a minute boundary (hydration warning).
  const [min, setMin] = useState<string | undefined>(undefined);
  useEffect(() => setMin(nowIstInput()), []);
  return (
    <>
      <fieldset className="form-section">
        <legend>Who</legend>
        <div className="field">
          <label htmlFor="appt-contact">Contact person{contactRequired ? " (required)" : ""}</label>
          <select id="appt-contact" required={contactRequired} aria-required={contactRequired} value={values.contactId} disabled={contactsLoading || !contacts} onChange={(e) => set("contactId", e.target.value)}>
            {contactsLoading ? <option value="">Loading contacts…</option> : <option value="">Choose a contact</option>}
            {(contacts ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
                {c.designation ? ` — ${c.designation}` : ""}
              </option>
            ))}
          </select>
        </div>
      </fieldset>
      <fieldset className="form-section">
        <legend>When</legend>
        {showWhen && (
          <>
            <div className="field">
              <label htmlFor="appt-when">Date and time (IST) (required)</label>
              <input id="appt-when" type="datetime-local" required aria-required="true" min={min} value={values.when} onChange={(e) => set("when", e.target.value)} />
            </div>
          </>
        )}
        <div className="field">
          <label htmlFor="appt-duration">Duration</label>
          <select id="appt-duration" value={values.duration} onChange={(e) => set("duration", Number(e.target.value))}>
            {(DURATIONS.includes(values.duration) ? DURATIONS : [...DURATIONS, values.duration].sort((a, b) => a - b)).map((d) => (
              <option key={d} value={d}>
                {formatMinutes(d)}
              </option>
            ))}
          </select>
        </div>
      </fieldset>
      <fieldset className="form-section">
        <legend>Details</legend>
        <div className="field">
          <label htmlFor="appt-type">Type (required)</label>
          <select id="appt-type" required aria-required="true" value={values.type} onChange={(e) => set("type", e.target.value)}>
            <option value="">Choose a type</option>
            {appointmentTypes(bdmType).map((t) => (
              <option key={t} value={t}>
                {TYPE_LABEL[t]}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="appt-location">Location</label>
          <input id="appt-location" maxLength={255} value={values.location} onChange={(e) => set("location", e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="appt-purpose">Purpose</label>
          <textarea id="appt-purpose" maxLength={1000} rows={2} value={values.purpose} onChange={(e) => set("purpose", e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="appt-remarks">Remarks</label>
          <textarea id="appt-remarks" maxLength={2000} rows={2} value={values.remarks} onChange={(e) => set("remarks", e.target.value)} />
        </div>
      </fieldset>
      <fieldset className="form-section">
        <legend>Estimates</legend>
        <div className="field">
          <label htmlFor="appt-leads">Expected leads</label>
          <input id="appt-leads" type="number" inputMode="numeric" min={0} step={1} value={values.leads} onChange={(e) => set("leads", e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="appt-revenue">Expected revenue (INR)</label>
          <input id="appt-revenue" type="number" inputMode="decimal" min={0} step={0.01} value={values.revenue} onChange={(e) => set("revenue", e.target.value)} />
        </div>
      </fieldset>
    </>
  );
}
