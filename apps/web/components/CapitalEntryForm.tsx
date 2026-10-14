"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { formatInr } from "@/lib/managementLedger";
import {
  CAPITAL_API,
  CAPITAL_KIND_LABEL,
  EMPTY_ENTRY_FORM,
  entryBody,
  entryProblem,
  overdraw,
  type CapitalAccount,
  type CapitalPerson,
  type EntryForm,
} from "@/lib/partnerCapital";

// mgmt-015 (CP2-CP4, CP11): record one capital entry. Closed until asked for. A withdrawal over the partner's balance needs a second
// click (the API accepts it). One request at a time, so a double click never records twice; a refusal keeps the entry and shows the
// API's reason. Entries are never edited: a mistake is corrected with an opposing entry that says so in its note.
const SAVE_FAILED = "The entry could not be saved. Try again.";

export default function CapitalEntryForm({ partners, accounts, today }: { partners: CapitalPerson[]; accounts: CapitalAccount[]; today: string }) {
  const router = useRouter();
  const sending = useRef(false);
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<EntryForm>(EMPTY_ENTRY_FORM);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [problem, setProblem] = useState<{ field?: keyof EntryForm; message: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const id = (field: string) => `capital-entry-${field}`;
  const set = (field: keyof EntryForm) => (e: { target: { value: string } }) => {
    setValues((v) => ({ ...v, [field]: e.target.value }));
    setConfirming(false);
  };
  const invalid = (field: keyof EntryForm) => (problem?.field === field ? { "aria-invalid": true as const, "aria-describedby": id("error") } : {});

  const toggle = (next: boolean) => {
    setOpen(next);
    setValues(EMPTY_ENTRY_FORM);
    setProblem(null);
    setConfirming(false);
    if (next) setNotice(null);
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (sending.current) return;
    const wrong = entryProblem(values, today);
    if (wrong) {
      setProblem(wrong);
      return document.getElementById(id(wrong.field))?.focus();
    }
    const over = overdraw(values, accounts);
    if (over && !confirming) {
      setConfirming(true);
      return setProblem({ message: `This withdrawal is more than ${over.name}'s capital balance of ${formatInr(over.balance)}. Record it anyway?` });
    }
    sending.current = true;
    setBusy(true);
    setProblem(null);
    const outcome = await sendJson(`${CAPITAL_API}/entries`, "POST", entryBody(values));
    sending.current = false;
    setBusy(false);
    setConfirming(false);
    if (!outcome.ok) return setProblem({ message: outcome.status !== undefined && outcome.detail === undefined ? SAVE_FAILED : outcome.message });
    toggle(false);
    setNotice("Capital entry recorded.");
    router.refresh();
  }

  const field = (key: keyof EntryForm, label: string, control: React.ReactNode) => (
    <div className="field" style={{ margin: 0 }}>
      <label htmlFor={id(key)}>{label}</label>
      {control}
    </div>
  );

  if (!open) {
    return (
      <div style={{ display: "grid", gap: 8, justifyItems: "start" }}>
        {notice && <p className="form-message" role="status" style={{ margin: 0 }}>{notice}</p>}
        <button type="button" className="btn" onClick={() => toggle(true)}>Record a capital entry</button>
      </div>
    );
  }
  return (
    <form className="action-card" onSubmit={submit} noValidate aria-label="Record a capital entry" style={{ display: "grid", gap: 12, flexBasis: "100%" }}>
      <h3 style={{ margin: 0 }}>Record a capital entry</h3>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
        {field("partner_id", "Partner", (
          <select id={id("partner_id")} value={values.partner_id} onChange={set("partner_id")} {...invalid("partner_id")}>
            <option value="">Choose a partner</option>
            {partners.map((p) => <option key={p.id} value={p.id}>{p.full_name}</option>)}
          </select>
        ))}
        {field("entry_date", "Date", <input id={id("entry_date")} className="input" type="date" min="2000-01-01" max={today} value={values.entry_date} onChange={set("entry_date")} {...invalid("entry_date")} />)}
        {field("kind", "Kind", (
          <select id={id("kind")} value={values.kind} onChange={set("kind")} {...invalid("kind")}>
            <option value="">Choose a kind</option>
            {Object.entries(CAPITAL_KIND_LABEL).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
          </select>
        ))}
        {field("amount", "Amount (₹)", <input id={id("amount")} className="input" inputMode="decimal" value={values.amount} onChange={set("amount")} {...invalid("amount")} />)}
      </div>
      {field("note", "Note (optional)", <input id={id("note")} className="input" maxLength={500} value={values.note} onChange={set("note")} />)}
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>Entries can&apos;t be edited or deleted. To correct a mistake, record an opposing entry and say why in its note.</p>
      {problem && <p id={id("error")} className="form-error" role="alert" style={{ margin: 0 }}>{problem.message}</p>}
      <div className="actions">
        <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : confirming ? "Record it anyway" : "Save entry"}</button>
        <button type="button" className="btn secondary" onClick={() => toggle(false)} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}
