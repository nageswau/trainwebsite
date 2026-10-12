"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { BALANCE_FIELDS, BALANCE_LABEL, balancesBody, balancesUrl, fieldErrors, type AccountsMonth, type BalanceField, type BalancesDraft } from "@/lib/accounts";
import { sendJson } from "@/lib/apiErrors";
import { monthLabel } from "@/lib/salaries";

// mgmt-013 (spec AD7-AD9, AD13): the month-end cash/bank, payables and tax liabilities the accountant (or a partner) types in. A blank
// field is "not entered"; the API decides every rule and its 422s land on their fields.
export default function BalancesForm({ data }: { data: AccountsMonth }) {
  const router = useRouter();
  const saving = useRef(false);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<BalancesDraft>(() => Object.fromEntries(BALANCE_FIELDS.map((f) => [f, data.balances[f] ?? ""])) as BalancesDraft);
  const [errors, setErrors] = useState<Partial<Record<BalanceField, string>>>({});
  const [result, setResult] = useState<{ text: string; failed: boolean } | null>(null);
  const label = monthLabel(data.month);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (saving.current) return; // one save per double click
    saving.current = true;
    setBusy(true);
    setResult(null);
    const outcome = await sendJson(balancesUrl(data.month), "PUT", balancesBody(draft));
    saving.current = false;
    setBusy(false);
    if (outcome.ok) {
      setErrors({});
      setResult({ text: `Balances for ${label} saved.`, failed: false });
      router.refresh();
      return;
    }
    const placed = fieldErrors(outcome.detail);
    setErrors(placed);
    setResult({ text: Object.keys(placed).length ? "Check the highlighted figures and save again." : outcome.message, failed: true });
  }

  return (
    <form className="action-card" style={{ display: "grid", gap: 12 }} noValidate aria-labelledby="balances-title" onSubmit={(e) => void save(e)}>
      <h3 id="balances-title" style={{ margin: 0 }}>Month-end balances · {label}</h3>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        Enter the figures at the end of {label}. Leave a figure blank if it is not known yet; it shows as “Not entered”. Cash/bank can be
        negative for an overdraft.
      </p>
      <div className="analytics-form" style={{ margin: 0 }}>
        {BALANCE_FIELDS.map((f) => (
          <div className="field" style={{ margin: 0 }} key={f}>
            <label htmlFor={`balance-${f}`}>{BALANCE_LABEL[f]} (₹)</label>
            <input
              id={`balance-${f}`} className="input" inputMode="decimal" autoComplete="off" value={draft[f]}
              onChange={(e) => { setDraft((d) => ({ ...d, [f]: e.target.value })); setResult(null); }}
              aria-invalid={errors[f] ? true : undefined} aria-describedby={errors[f] ? `balance-${f}-error` : undefined}
            />
            {errors[f] && <div className="form-error" style={{ fontSize: 12 }} id={`balance-${f}-error`}>{errors[f]}</div>}
          </div>
        ))}
      </div>
      {result && <p className={result.failed ? "form-error" : "form-message"} role={result.failed ? "alert" : "status"}>{result.text}</p>}
      <div className="actions" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          {data.balances.updated_by ? <>Last saved by {data.balances.updated_by.full_name}.</> : <>Nothing entered for {label} yet.</>}
        </p>
        <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : `Save ${label} balances`}</button>
      </div>
    </form>
  );
}
