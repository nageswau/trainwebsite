"use client";

import Link from "next/link";
import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import { SESSION_EXPIRED, SIGN_IN_PATH } from "@/lib/activityFeedback";
import { sendJson } from "@/lib/apiErrors";
import { AgentApplicationDetail, depositUrl } from "@/lib/agentApplications";
import { fieldErrors } from "@/lib/agentStudents";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Props = {
  detail: AgentApplicationDetail;
  onSaved: (d: AgentApplicationDetail, message: string) => void;
  onFailed: (message: string, status?: number) => void;
  onCancel: () => void;
};

const EXPIRED = `${SESSION_EXPIRED} Your entry is kept; sign in again in a new tab, then save.`;
const SERVER_ERROR = "Something went wrong on our side. Please try again; your entry is kept.";
const FIELDS = ["required", "amount", "due_date"] as const;
type Field = (typeof FIELDS)[number];
const FIELD_ID: Record<Field, string> = { required: "required-yes", amount: "amount", due_date: "due" }; // the control a 422 focuses

// AGN-011 (DEC-SCOPE-057 §4.2): record or change the deposit while it is unpaid -- required yes/no, the amount in rupees (D1) and an
// optional due date; the whole deposit is sent (PUT). A 422 lands on its field with the entry kept; a 409/404 goes to the detail,
// which reloads to the real state. Escape cancels.
export default function AgentApplicationDepositForm({ detail, onSaved, onFailed, onCancel }: Props) {
  const current = detail.deposit;
  const id = (part: string) => `deposit-${part}-${detail.id}`;
  const [required, setRequired] = useState<boolean | null>(current ? current.required : null);
  const [amount, setAmount] = useState(current?.amount ?? "");
  const [dueDate, setDueDate] = useState(current?.due_date ?? "");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ text: string; expired?: boolean } | null>(null);
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const inFlight = useRef(false); // a same-tick second submit sends nothing
  const focusAfter = useFocusAfterRender();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current || required === null) return;
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    setErrors({});
    const body = required ? { required, amount: amount.trim(), due_date: dueDate || null } : { required };
    const outcome = await sendJson(depositUrl(detail.id), "PUT", body); // never throws
    inFlight.current = false;
    setBusy(false);
    if (!outcome.ok) {
      if (outcome.status === 409 || outcome.status === 404) return onFailed(outcome.message, outcome.status);
      const onFields = outcome.status === 422 ? fieldErrors(outcome.detail, FIELDS) : null;
      if (onFields) {
        setErrors(onFields);
        return focusAfter(id(FIELD_ID[FIELDS.find((f) => onFields[f])!]));
      }
      const status = outcome.status ?? 0;
      setFailure(status === 401 ? { text: EXPIRED, expired: true } : { text: status >= 500 ? SERVER_ERROR : outcome.message });
      return focusAfter(id("failure"));
    }
    const next = (outcome.data as { application?: AgentApplicationDetail }).application;
    if (!next) return onFailed("The change could not be confirmed. Reload to see the application.");
    onSaved(next, "Deposit saved.");
  }

  const invalid = (field: Field) => (errors[field] ? { "aria-invalid": true as const, "aria-describedby": id(`${field}-error`) } : {});
  const fieldError = (field: Field) =>
    errors[field] && (
      <p id={id(`${field}-error`)} className="form-error">
        {errors[field]}
      </p>
    );

  return (
    <form
      className="form"
      aria-label={current ? "Edit deposit" : "Record deposit"}
      onSubmit={submit}
      onKeyDown={(event: KeyboardEvent) => event.key === "Escape" && onCancel()}
    >
      <fieldset className="field">
        <legend>Deposit required?</legend>
        <label>
          <input id={id("required-yes")} type="radio" name={id("required")} required checked={required === true} onChange={() => setRequired(true)} {...invalid("required")} /> Yes
        </label>
        <label>
          <input id={id("required-no")} type="radio" name={id("required")} required checked={required === false} onChange={() => setRequired(false)} /> No
        </label>
        {fieldError("required")}
      </fieldset>
      {required && (
        <>
          <div className="field">
            <label htmlFor={id("amount")}>Amount in ₹ (INR)</label>
            <input
              id={id("amount")}
              inputMode="decimal"
              required
              autoComplete="off"
              pattern="[0-9]+(\.[0-9]{1,2})?"
              title="A rupee amount with up to 2 decimals, for example 50000 or 50000.50"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              {...invalid("amount")}
            />
            {fieldError("amount")}
          </div>
          <div className="field">
            <label htmlFor={id("due")}>Due date (optional)</label>
            <input id={id("due")} type="date" min="2000-01-01" max="2100-12-31" value={dueDate} onChange={(event) => setDueDate(event.target.value)} {...invalid("due_date")} />
            {fieldError("due_date")}
          </div>
        </>
      )}
      {failure && (
        <p id={id("failure")} tabIndex={-1} className="form-error" role="alert">
          {failure.text}
          {failure.expired && (
            <>
              {" "}
              <Link href={SIGN_IN_PATH} target="_blank" rel="noopener">
                Sign in again
              </Link>
            </>
          )}
        </p>
      )}
      <div className="actions">
        <button className="btn small" disabled={busy || required === null}>
          {busy ? "Saving…" : "Save deposit"}
        </button>
        <button type="button" className="btn ghost small" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
