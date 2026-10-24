"use client";

import { FormEvent, useState } from "react";

import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { detailMessage, sendJson } from "@/lib/apiErrors";
import { isVisaDecided, nextVisaStatuses, visaStatusLabel } from "@/lib/visaStatus";

export type VisaDocument = { id: string; document_type: string; original_filename: string | null };
export type VisaCaseView = {
  id: string;
  visa_status: string;
  readiness_review_date: string | null;
  visa_category: string | null;
  appointment_date: string | null;
  appointment_place: string | null;
  submission_date: string | null;
  tracking_reference: string | null;
  interview_date: string | null;
  expected_decision_date: string | null;
  decision_date: string | null;
  outcome_document_id: string | null;
  refusal_reason?: string | null;
  next_steps: string | null;
  documents?: VisaDocument[];
};

const DATES = [
  ["readiness_review_date", "Readiness review date"],
  ["appointment_date", "Appointment date"],
  ["submission_date", "Submission date"],
  ["interview_date", "Interview date"],
  ["expected_decision_date", "Expected decision date"],
] as const;
const TEXTS = [
  ["visa_category", "Visa category", 80],
  ["appointment_place", "Appointment place", 200],
  ["tracking_reference", "Visa application reference", 120],
] as const;
type Field = (typeof DATES)[number][0] | (typeof TEXTS)[number][0] | "decision_date" | "outcome_document_id" | "refusal_reason" | "next_steps";
const FIELDS: Field[] = [...DATES.map(([f]) => f), ...TEXTS.map(([f]) => f), "decision_date", "outcome_document_id", "refusal_reason", "next_steps"];

/** A 422 list's message for one body field, if the server put one there. */
function fieldMessage(detail: unknown, field: string): string | null {
  if (!Array.isArray(detail)) return null;
  const hit = detail.find((d: { loc?: unknown[] }) => Array.isArray(d?.loc) && d.loc[d.loc.length - 1] === field);
  return hit ? detailMessage([hit]) : null;
}

// ccrm-026 (DEC-SCOPE-252): the counselor records a visa case's Appendix A lifecycle -- details, the next status, and the decision
// with its date, evidence and (refused only) the restricted reason. The shown status travels as `expected_visa_status`, so a stale
// screen gets a 409. A decided case is read-only here: the Overseas Admin corrects it (VC1).
export default function CounselorVisaCaseForm({ visa, onSaved }: { visa: VisaCaseView; onSaved: () => void }) {
  const initial = () => Object.fromEntries(FIELDS.map((f) => [f, (visa[f] as string | null) ?? ""])) as Record<Field, string>;
  const [values, setValues] = useState<Record<Field, string>>(initial);
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const [errors, setErrors] = useState<Partial<Record<string, string>>>({});
  const decided = isVisaDecided(visa.visa_status);
  const finalStatus = target || visa.visa_status;
  const decisionShown = isVisaDecided(finalStatus);
  const id = (name: string) => `visa-${visa.id}-${name}`;

  if (decided) {
    return (
      <>
        <p className="muted" style={{ fontSize: 13 }}>The visa decision is recorded, so this case can no longer be changed. Ask the Overseas Admin to correct it.</p>
        {message && <FormMessage message={message} style={{ marginTop: 8, fontSize: 13 }} />}
      </>
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    setErrors({});
    const body: Record<string, unknown> = { expected_visa_status: visa.visa_status };
    for (const field of FIELDS) {
      const value = values[field].trim();
      if (value !== ((visa[field] as string | null) ?? "")) body[field] = value === "" ? null : value;
    }
    if (target) body.visa_status = target;
    const result = await sendJson(`/api/v1/workflows/overseas/visa/${visa.id}/lifecycle`, "PATCH", body);
    setBusy(false);
    if (!result.ok) {
      const perField = Object.fromEntries([...FIELDS, "visa_status"].map((f) => [f, fieldMessage(result.detail, f)]).filter(([, m]) => m));
      setErrors(perField);
      setMessage({ text: result.message, failed: true });
      return;
    }
    setTarget("");
    setMessage({ text: target ? `Visa status set to ${visaStatusLabel(target)}.` : "Visa details saved.", failed: false });
    onSaved();
  }

  const set = (field: Field) => (event: { target: { value: string } }) => setValues((current) => ({ ...current, [field]: event.target.value }));
  const invalid = (field: string) => (errors[field] ? { "aria-invalid": true, "aria-describedby": id(`${field}-error`) } : {});
  const error = (field: string) => errors[field] && <span id={id(`${field}-error`)} className="form-error">{errors[field]}</span>;

  return (
    <form className="form" aria-label="Visa case" onSubmit={submit} style={{ marginTop: 10 }}>
      <div className="field">
        <label htmlFor={id("visa_status")}>Next status</label>
        <select id={id("visa_status")} value={target} onChange={(event) => setTarget(event.target.value)} {...invalid("visa_status")}>
          <option value="">Keep {visaStatusLabel(visa.visa_status)}</option>
          {nextVisaStatuses(visa.visa_status).map((status) => (
            <option key={status} value={status}>
              {visaStatusLabel(status)}
            </option>
          ))}
        </select>
      </div>
      {TEXTS.map(([field, text, max]) => (
        <div className="field" key={field}>
          <label htmlFor={id(field)}>{text}</label>
          <input id={id(field)} value={values[field]} maxLength={max} onChange={set(field)} {...invalid(field)} />
          {error(field)}
        </div>
      ))}
      {DATES.map(([field, text]) => (
        <div className="field" key={field}>
          <label htmlFor={id(field)}>{text}</label>
          <input id={id(field)} type="date" value={values[field]} onChange={set(field)} {...invalid(field)} />
          {error(field)}
        </div>
      ))}
      {decisionShown && (
        <fieldset className="form-section">
          <legend>Decision: {visaStatusLabel(finalStatus)}</legend>
          <div className="field">
            <label htmlFor={id("decision_date")}>Decision date</label>
            <input id={id("decision_date")} type="date" value={values.decision_date} onChange={set("decision_date")} {...invalid("decision_date")} />
            {error("decision_date")}
          </div>
          <div className="field">
            <label htmlFor={id("outcome_document_id")}>Outcome evidence</label>
            <select id={id("outcome_document_id")} value={values.outcome_document_id} onChange={set("outcome_document_id")} {...invalid("outcome_document_id")}>
              <option value="">No document</option>
              {(visa.documents ?? []).map((doc) => (
                <option key={doc.id} value={doc.id}>
                  {doc.document_type}
                  {doc.original_filename ? ` (${doc.original_filename})` : ""}
                </option>
              ))}
            </select>
            {error("outcome_document_id")}
          </div>
          {finalStatus === "refused" && (
            <div className="field">
              <label htmlFor={id("refusal_reason")}>Refusal reason (counselor and admin only)</label>
              <textarea id={id("refusal_reason")} value={values.refusal_reason} maxLength={2000} onChange={set("refusal_reason")} {...invalid("refusal_reason")} />
              {error("refusal_reason")}
            </div>
          )}
          <p className="muted" style={{ fontSize: 13 }}>Once saved, the decision is final. Only the Overseas Admin can correct it.</p>
        </fieldset>
      )}
      <div className="field">
        <label htmlFor={id("next_steps")}>Next steps</label>
        <textarea id={id("next_steps")} value={values.next_steps} maxLength={2000} onChange={set("next_steps")} {...invalid("next_steps")} />
        {error("next_steps")}
      </div>
      <button className="btn small" disabled={busy}>
        {busy ? "Saving…" : decisionShown ? "Record decision" : "Save visa case"}
      </button>
      {message && <FormMessage message={message} style={{ marginTop: 8, fontSize: 13 }} />}
    </form>
  );
}
