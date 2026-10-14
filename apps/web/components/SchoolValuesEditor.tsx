"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmTravel";
import { SCHOOLS_API, type SchoolValues } from "@/lib/managementSchools";
import { useHydrated } from "@/lib/useHydrated";

type Field = "contract_value" | "renewal_value";
const FIELDS: [Field, string][] = [["contract_value", "Contract value (₹)"], ["renewal_value", "Renewal value (₹)"]];
const AMOUNT = /^\d+(\.\d{1,2})?$/;
const plain = (value: string) => value.replace(/[,\s₹]/g, "");

/** What the browser can check before sending; the API checks everything again. Empty clears the value. */
function validate(values: Record<Field, string>): Partial<Record<Field, string>> {
  const errors: Partial<Record<Field, string>> = {};
  for (const [key] of FIELDS) {
    const amount = plain(values[key]);
    if (amount && !AMOUNT.test(amount)) errors[key] = /^\d+\.\d{3,}$/.test(amount) ? "Use at most 2 decimal places" : "Enter an amount of 0 or more";
  }
  return errors;
}

// mgmt-022 (SD13): the finance tier's contract / renewal value of one school, opened from its row. Saving refreshes the dashboard so the
// row and the totals show the stored values; a failed save keeps what was typed.
export default function SchoolValuesEditor({ school }: { school: SchoolValues & { name: string } }) {
  const router = useRouter();
  const ready = useHydrated();
  const [values, setValues] = useState<Record<Field, string>>({ contract_value: school.contract_value ?? "", renewal_value: school.renewal_value ?? "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const id = (key: string) => `school-${school.id}-${key}`;

  async function save() {
    const found = validate(values);
    setErrors(found);
    setMessage("");
    if (Object.keys(found).length) {
      document.getElementById(id(Object.keys(found)[0]))?.focus();
      return;
    }
    setBusy(true);
    const body = Object.fromEntries(FIELDS.map(([key]) => [key, plain(values[key]) || null]));
    const saved = await sendJson(`${SCHOOLS_API}/${school.id}`, "PATCH", body);
    setBusy(false);
    if (!saved.ok) {
      const placed = fieldErrors(saved.detail);
      setErrors(placed);
      setMessage(Object.keys(placed).length ? "Check the highlighted fields." : saved.message);
      return;
    }
    setMessage("Saved.");
    router.refresh();
  }

  return (
    <details className="school-values">
      <summary aria-label={`Edit values for ${school.name}`}>Edit values</summary>
      <form className="form" noValidate aria-label={`Contract and renewal value for ${school.name}`} onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <fieldset disabled={!ready || busy} className="form" style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
          {FIELDS.map(([key, label]) => (
            <div className="field" key={key}>
              <label htmlFor={id(key)}>{label}</label>
              <input id={id(key)} type="text" inputMode="decimal" autoComplete="off" value={values[key]} placeholder="Not entered"
                aria-invalid={errors[key] ? true : undefined} aria-describedby={errors[key] ? id(`${key}-error`) : undefined}
                onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))} />
              {errors[key] && <p className="form-error" id={id(`${key}-error`)}>{errors[key]}</p>}
            </div>
          ))}
          <span className="muted" style={{ fontSize: 13 }}>Leave a value empty to clear it.</span>
          {message && <p className={message === "Saved." ? "muted" : "form-error"} role={message === "Saved." ? "status" : "alert"}>{message}</p>}
          <button className="btn" type="submit">{busy ? "Saving…" : "Save"}</button>
        </fieldset>
      </form>
    </details>
  );
}
