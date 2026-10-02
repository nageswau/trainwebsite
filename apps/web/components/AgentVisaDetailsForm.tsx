"use client";

import { FormEvent, ReactNode, useState } from "react";
import { Visa, VISA_DOCUMENT_TYPES } from "@/lib/agentApplications";

export const DETAIL_FIELDS = ["visa_application_date", "appointment_date", "interview_date", "checklist"] as const;
export type DetailField = (typeof DETAIL_FIELDS)[number];
type DateField = Exclude<DetailField, "checklist">;
export type VisaDetails = { checklist: string[] } & Record<DateField, string | null>;

type Props = {
  appId: string;
  visa: Visa | null; // null: starting a case
  checklistEditable: boolean;
  busy: boolean;
  errors: Partial<Record<DetailField, string>>;
  failure: ReactNode;
  onSubmit: (values: VisaDetails) => void;
  onCancel: () => void;
};

const DATES: { field: DateField; label: string }[] = [
  { field: "visa_application_date", label: "Visa application date (optional)" },
  { field: "appointment_date", label: "Appointment date (optional)" },
  { field: "interview_date", label: "Interview date (optional)" },
];

// AGN-012 (DEC-SCOPE-055): the dates and document checklist of a visa case, shared by Start and Edit. An emptied date is sent as null
// (it clears the stored one). The server checks the date order and the checklist; its field errors arrive in `errors`.
export default function AgentVisaDetailsForm({ appId, visa, checklistEditable, busy, errors, failure, onSubmit, onCancel }: Props) {
  const [checklist, setChecklist] = useState<string[]>(visa ? visa.checklist.map((c) => c.item) : []);
  const [dates, setDates] = useState<Record<DateField, string>>({
    visa_application_date: visa?.visa_application_date ?? "",
    appointment_date: visa?.appointment_date ?? "",
    interview_date: visa?.interview_date ?? "",
  });
  const id = (part: string) => `visa-${part}-${appId}`;
  const described = (field: DetailField) => (errors[field] ? { "aria-invalid": true as const, "aria-describedby": id(`${field}-error`) } : {});
  const error = (field: DetailField) =>
    errors[field] && (
      <p id={id(`${field}-error`)} className="form-error">
        {errors[field]}
      </p>
    );

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit({ checklist, visa_application_date: dates.visa_application_date || null, appointment_date: dates.appointment_date || null, interview_date: dates.interview_date || null });
  }
  return (
    <form className="form" aria-label={visa ? "Edit visa details" : "Start visa case"} aria-busy={busy} onSubmit={submit}>
      {DATES.map(({ field, label }) => (
        <div className="field" key={field}>
          <label htmlFor={id(field)}>{label}</label>
          <input
            id={id(field)}
            type="date"
            min="2000-01-01"
            max="2100-12-31"
            value={dates[field]}
            onChange={(event) => setDates((now) => ({ ...now, [field]: event.target.value }))}
            {...described(field)}
          />
          {error(field)}
        </div>
      ))}
      {checklistEditable && (
        <fieldset id={id("checklist")} tabIndex={-1} className="form-section" {...described("checklist")}>
          <legend>Documents the visa needs</legend>
          {VISA_DOCUMENT_TYPES.map((type) => (
            <label key={type} className="pf-check">
              <input
                type="checkbox"
                checked={checklist.includes(type)}
                onChange={(event) => setChecklist((now) => (event.target.checked ? [...now, type] : now.filter((t) => t !== type)))}
              />
              {type}
            </label>
          ))}
          {error("checklist")}
        </fieldset>
      )}
      {failure}
      <div className="actions">
        <button className="btn small" disabled={busy}>
          {busy ? "Saving…" : visa ? "Save visa details" : "Start visa case"}
        </button>
        <button type="button" className="btn ghost small" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
