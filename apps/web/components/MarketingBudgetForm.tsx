"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { budgetErrors, budgetsBody, budgetsUrl, type BudgetDraft, type MarketingMonth } from "@/lib/marketing";
import { monthLabel } from "@/lib/salaries";

// mgmt-012 (spec MK3, MK4, MK14): the month's budget per channel, typed by a partner or the accountant. A blank field means no budget
// ("Not set"); saving replaces the whole month. The API decides every rule and its 422s land on their channel.
export default function MarketingBudgetForm({ data }: { data: MarketingMonth }) {
  const router = useRouter();
  const saving = useRef(false);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<BudgetDraft>(() => Object.fromEntries(data.channels.map((c) => [c.channel, c.budget ?? ""])));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [result, setResult] = useState<{ text: string; failed: boolean } | null>(null);
  const label = monthLabel(data.month);
  const channels = data.channels.map((c) => c.channel);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (saving.current) return; // one save per double click
    saving.current = true;
    setBusy(true);
    setResult(null);
    const body = budgetsBody(draft, channels);
    const outcome = await sendJson(budgetsUrl(data.month), "PUT", body);
    saving.current = false;
    setBusy(false);
    if (outcome.ok) {
      setErrors({});
      setResult({ text: `Budgets for ${label} saved.`, failed: false });
      router.refresh();
      return;
    }
    const placed = budgetErrors(outcome.detail, body.budgets.map((b) => b.channel));
    setErrors(placed);
    setResult({ text: Object.keys(placed).length ? "Check the highlighted budgets and save again." : outcome.message, failed: true });
  }

  return (
    <form className="action-card" style={{ display: "grid", gap: 12 }} noValidate aria-labelledby="budgets-title" onSubmit={(e) => void save(e)}>
      <h3 id="budgets-title" style={{ margin: 0 }}>Budgets · {label}</h3>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        Enter each channel&apos;s marketing budget for {label}. Leave a channel blank if it has no budget; it shows as “Not set”. Spend comes
        from the ledger: tag a marketing expense with its channel when you record it.
      </p>
      <div className="analytics-form" style={{ margin: 0 }}>
        {data.channels.map((c) => (
          <div className="field" style={{ margin: 0 }} key={c.channel}>
            <label htmlFor={`budget-${c.channel}`}>{c.label} budget (₹)</label>
            <input
              id={`budget-${c.channel}`} className="input" inputMode="decimal" autoComplete="off" value={draft[c.channel]}
              onChange={(e) => { setDraft((d) => ({ ...d, [c.channel]: e.target.value })); setResult(null); }}
              aria-invalid={errors[c.channel] ? true : undefined} aria-describedby={errors[c.channel] ? `budget-${c.channel}-error` : undefined}
            />
            {errors[c.channel] && <div className="form-error" style={{ fontSize: 12 }} id={`budget-${c.channel}-error`}>{errors[c.channel]}</div>}
          </div>
        ))}
      </div>
      {result && <p className={result.failed ? "form-error" : "form-message"} role={result.failed ? "alert" : "status"}>{result.text}</p>}
      <div className="actions" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          {data.budgets_updated_by ? <>Last saved by {data.budgets_updated_by.full_name}.</> : <>No budget saved for {label} yet.</>}
        </p>
        <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : `Save ${label} budgets`}</button>
      </div>
    </form>
  );
}
