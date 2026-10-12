"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { sendJson, sendRequest } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmTravel";
import { KIND_LABEL, LEDGER_API, LEDGER_HOME, type LedgerEntry, type LedgerKind, type LedgerOptions } from "@/lib/managementLedger";
import { useHydrated } from "@/lib/useHydrated";

type Values = { kind: LedgerKind; entry_date: string; category_id: string; amount: string; vertical: string; description: string; channel: string; program_id: string; batch_id: string };
type Field = keyof Values;

const AMOUNT = /^\d+(\.\d{1,2})?$/;
const RECEIPT_TYPES = ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png";

function initial(entry: LedgerEntry | undefined, today: string): Values {
  if (!entry) return { kind: "expense", entry_date: today, category_id: "", amount: "", vertical: "", description: "", channel: "", program_id: "", batch_id: "" };
  return {
    kind: entry.kind, entry_date: entry.entry_date, category_id: entry.category.id, amount: entry.amount, vertical: entry.vertical, description: entry.description,
    channel: entry.channel ?? "", program_id: entry.program?.id ?? "", batch_id: entry.batch?.id ?? "",
  };
}

const plainAmount = (value: string) => value.replace(/[,\s₹]/g, "");

/** What the browser can check before sending; the API checks everything again. */
function validate(values: Values): Partial<Record<Field, string>> {
  const errors: Partial<Record<Field, string>> = {};
  if (!values.entry_date) errors.entry_date = "Choose a date";
  if (!values.category_id) errors.category_id = "Choose a category";
  const amount = plainAmount(values.amount);
  if (!AMOUNT.test(amount) || Number(amount) <= 0) errors.amount = /^\d+\.\d{3,}$/.test(amount) ? "Use at most 2 decimal places" : "Enter an amount more than 0";
  if (!values.vertical) errors.vertical = "Choose a vertical";
  const description = values.description.trim();
  if (description.length < 2 || description.length > 500) errors.description = "Describe the entry (2-500 characters)";
  return errors;
}

// mgmt-004 (ML4-ML8, ML13): a new entry or a change to a draft or rejected one. "Save and submit" saves, then sends it for a partner's
// approval; a chosen receipt is uploaded after the save. If that second step fails the saved entry still opens, with a notice saying
// which step to retry there, so nothing typed is lost twice.
export default function LedgerEntryForm({ options, today, entry }: { options: LedgerOptions; today: string; entry?: LedgerEntry }) {
  const router = useRouter();
  const ready = useHydrated();
  const [values, setValues] = useState<Values>(() => initial(entry, today));
  const [receipt, setReceipt] = useState<File | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (key: Field, value: string) => setValues((v) => ({ ...v, [key]: value }));

  const categories = options.categories.filter((c) => c.kind === values.kind).map((c) => ({ value: c.id, label: c.nature ? `${c.name} (${c.nature})` : c.name }));
  if (entry && entry.kind === values.kind && !categories.some((c) => c.value === entry.category.id)) categories.push({ value: entry.category.id, label: `${entry.category.name} (inactive)` });
  const programs = options.programs.map((p) => ({ value: p.id, label: p.name }));
  if (entry?.program && !programs.some((p) => p.value === entry.program!.id)) programs.push({ value: entry.program.id, label: entry.program.name });
  const batches = (options.programs.find((p) => p.id === values.program_id)?.batches ?? []).map((b) => ({ value: b.id, label: b.name }));
  if (entry?.batch && values.batch_id === entry.batch.id && !batches.some((b) => b.value === entry.batch!.id)) batches.push({ value: entry.batch.id, label: entry.batch.name });

  const fieldProps = (key: Field) => ({ id: `ledger-${key}`, "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `ledger-${key}-error` : undefined });
  const error = (key: Field) => errors[key] && <p className="form-error" id={`ledger-${key}-error`}>{errors[key]}</p>;
  const select = (key: Field, label: string, choices: { value: string; label: string }[], empty: string) => (
    <div className="field">
      <label htmlFor={`ledger-${key}`}>{label}</label>
      <select value={values[key]} onChange={(e) => (key === "program_id" ? setValues((v) => ({ ...v, program_id: e.target.value, batch_id: "" })) : set(key, e.target.value))} {...fieldProps(key)}>
        <option value="">{empty}</option>
        {choices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
      </select>
      {error(key)}
    </div>
  );

  async function save(submit: boolean) {
    const found = validate(values);
    setErrors(found);
    if (Object.keys(found).length) {
      setMessage("Check the highlighted fields.");
      document.getElementById(`ledger-${Object.keys(found)[0]}`)?.focus();
      return;
    }
    setBusy(true);
    setMessage("");
    const body = {
      ...(entry ? {} : { kind: values.kind }), entry_date: values.entry_date, category_id: values.category_id, amount: plainAmount(values.amount),
      vertical: values.vertical, description: values.description.trim(), channel: values.kind === "expense" && values.channel ? values.channel : null,
      program_id: values.program_id || null, batch_id: values.batch_id || null,
    };
    const saved = entry ? await sendJson(`${LEDGER_API}/${entry.id}`, "PATCH", body) : await sendJson(LEDGER_API, "POST", body);
    if (!saved.ok) {
      const placed = fieldErrors(saved.detail);
      setErrors(placed);
      setMessage(Object.keys(placed).length ? "Check the highlighted fields." : saved.message);
      setBusy(false);
      return;
    }
    const id = entry?.id ?? String(saved.data.id);
    let notice = "";
    if (receipt) {
      const form = new FormData();
      form.append("file", receipt);
      if (!(await sendRequest(`${LEDGER_API}/${id}/receipt`, { method: "PUT", body: form })).ok) notice = "receipt";
    }
    if (!notice && submit && !(await sendJson(`${LEDGER_API}/${id}/submit`, "POST", {})).ok) notice = "submit";
    router.push(`${LEDGER_HOME}/${id}${notice ? `?notice=${notice}` : ""}`);
    router.refresh(); // the entry page may be cached from before this change
  }

  return (
    <form className="form action-card" noValidate aria-label={entry ? "Edit ledger entry" : "New ledger entry"} onSubmit={(e) => { e.preventDefault(); void save(false); }}>
      <fieldset disabled={!ready || busy} className="form" style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
        {!entry && (
          <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
            <legend style={{ fontWeight: 800, fontSize: 13, marginBottom: 7 }}>Kind</legend>
            <div className="actions">
              {(Object.keys(KIND_LABEL) as LedgerKind[]).map((kind) => (
                <label key={kind} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input type="radio" name="kind" value={kind} checked={values.kind === kind} style={{ width: "auto" }}
                    onChange={() => setValues((v) => ({ ...v, kind, category_id: "", channel: "" }))} />
                  {KIND_LABEL[kind]}
                </label>
              ))}
            </div>
          </fieldset>
        )}
        <div className="form-grid">
          <div className="field">
            <label htmlFor="ledger-entry_date">Date</label>
            <input type="date" max={today} value={values.entry_date} onChange={(e) => set("entry_date", e.target.value)} {...fieldProps("entry_date")} />
            {error("entry_date")}
          </div>
          {select("category_id", "Category", categories, "Choose…")}
          <div className="field">
            <label htmlFor="ledger-amount">Amount (₹)</label>
            <input type="text" inputMode="decimal" autoComplete="off" value={values.amount} onChange={(e) => set("amount", e.target.value)} {...fieldProps("amount")} />
            {error("amount")}
          </div>
          {select("vertical", "Vertical", options.verticals, "Choose…")}
        </div>
        <div className="field">
          <label htmlFor="ledger-description">Description</label>
          <textarea rows={3} maxLength={500} value={values.description} onChange={(e) => set("description", e.target.value)} {...fieldProps("description")} />
          {error("description")}
        </div>
        <div className="form-grid">
          {values.kind === "expense" && select("channel", "Marketing channel (optional)", options.channels, "None")}
          {select("program_id", "Course (optional)", programs, "None")}
          {values.program_id && select("batch_id", "Batch (optional)", batches, "None")}
        </div>
        <div className="field">
          <label htmlFor="ledger-receipt">Receipt (optional)</label>
          <input id="ledger-receipt" type="file" accept={RECEIPT_TYPES} onChange={(e) => setReceipt(e.target.files?.[0] ?? null)} />
          <span className="muted" style={{ fontSize: 13 }}>PDF, JPEG or PNG.{entry?.receipt ? " A new file replaces the current receipt." : ""}</span>
        </div>
        {message && <p className="form-error" role="alert">{message}</p>}
        <div className="actions">
          <button className="btn" type="submit">{busy ? "Saving…" : entry ? "Save changes" : "Save draft"}</button>
          <button className="btn secondary" type="button" onClick={() => void save(true)}>Save and submit</button>
          <a className="btn ghost" href={entry ? `${LEDGER_HOME}/${entry.id}` : LEDGER_HOME}>Cancel</a>
        </div>
      </fieldset>
    </form>
  );
}
