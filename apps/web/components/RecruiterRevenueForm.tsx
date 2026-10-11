"use client";
import { type FormEvent, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmPipeline";
import { revenueConflict } from "@/lib/recruiterRevenue";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

export type RevenueField = {
  name: string; label: string; kind: "text" | "date" | "amount" | "textarea" | "select"; required?: boolean; max?: number; hint?: string;
  options?: { key: string; label: string }[];
};

// rec-031 (spec §4): the one small form behind the fee override, Add invoice, Record payment and Cancel invoice. It sends every field
// (blank = null) plus `extra`; the server owns the rules, so a 422 lands on its field (aria-invalid, focused) and a coded 409 shows its
// message. `noValidate`: the server's words, not the browser's bubble, explain a bad amount or date. A double click sends once.
export default function RecruiterRevenueForm({ id, label, submitLabel, url, method, fields, initial = {}, extra = {}, onDone, onCancel }: {
  id: string; label: string; submitLabel: string; url: string; method: "POST" | "PUT"; fields: RevenueField[]; initial?: Record<string, string>;
  extra?: Record<string, unknown>; onDone: (data: Record<string, unknown>) => void; onCancel: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(fields.map((f) => [f.name, initial[f.name] ?? ""])));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const focus = useFocusAfterRender();
  const fid = (part: string) => `${id}-${part}`;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    setErrors({});
    try {
      const body = { ...extra, ...Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v.trim() === "" ? null : v.trim()])) };
      const outcome = await sendJson(url, method, body);
      if (outcome.ok) return onDone(outcome.data);
      const found = fieldErrors(outcome.detail);
      const known = Object.keys(found).filter((k) => k in values);
      if (known.length) {
        setErrors(found);
        return focus(fid(known[0]));
      }
      setFailure(revenueConflict(outcome.detail) ?? outcome.message);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <form className="form-grid" onSubmit={submit} aria-label={label} noValidate>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {fields.map((f) => {
        const describedBy = [errors[f.name] ? fid(`${f.name}-error`) : null, f.hint ? fid(`${f.name}-hint`) : null].filter(Boolean).join(" ") || undefined;
        const common = {
          id: fid(f.name), value: values[f.name], required: f.required, "aria-invalid": errors[f.name] ? true : undefined, "aria-describedby": describedBy,
          onChange: (e: { target: { value: string } }) => setValues((v) => ({ ...v, [f.name]: e.target.value })),
        };
        return (
          <div className="field" key={f.name}>
            <label htmlFor={fid(f.name)}>{f.label}{f.required ? "" : " (optional)"}</label>
            {f.kind === "select" ? (
              <select {...common}>
                <option value="">{f.required ? "Choose…" : "None"}</option>
                {f.options?.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
              </select>
            ) : f.kind === "textarea" ? (
              <textarea {...common} maxLength={f.max} rows={2} />
            ) : (
              <input {...common} type={f.kind === "date" ? "date" : "text"} inputMode={f.kind === "amount" ? "decimal" : undefined} maxLength={f.max} autoComplete="off" />
            )}
            {f.hint && <p id={fid(`${f.name}-hint`)} className="muted">{f.hint}</p>}
            {errors[f.name] && <p id={fid(`${f.name}-error`)} className="form-error">{errors[f.name]}</p>}
          </div>
        );
      })}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : submitLabel}</button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Back</button>
      </div>
    </form>
  );
}
