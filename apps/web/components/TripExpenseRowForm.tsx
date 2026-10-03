"use client";

import { useState } from "react";

import FormMessage from "@/components/FormMessage";
import { AMOUNT_PATTERN, CATEGORY_LABEL, fieldErrors, tripUrl, type ExpenseCategory, type TripExpense } from "@/lib/bdmTravel";
import { jsonInit, useTripWrite } from "@/lib/useTripWrite";

// bdm-010 (T7): one expense line -- category, INR amount, date, optional note. Adds a line, or edits `expense`.
// Category takes focus when the form opens; Escape or Cancel closes it (the parent returns focus).
export default function TripExpenseRowForm({ tripId, expense, defaultDate, onDone, onCancel }: {
  tripId: string; expense?: TripExpense; defaultDate: string; onDone: () => void; onCancel: () => void;
}) {
  const [category, setCategory] = useState<ExpenseCategory>(expense?.category ?? "travel");
  const [amount, setAmount] = useState(expense ? String(Number(expense.amount)) : "");
  const [date, setDate] = useState(expense?.expense_date ?? defaultDate);
  const [note, setNote] = useState(expense?.note ?? "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const { busy, message, run } = useTripWrite();
  const prefix = expense ? `expense-${expense.id}` : "expense-new";

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const found: Record<string, string> = {};
    if (!AMOUNT_PATTERN.test(amount.trim())) found.amount = "Enter an amount in rupees with up to 2 decimals";
    else if (Number(amount) <= 0) found.amount = "The amount must be more than ₹0";
    if (!date) found.expense_date = "Date is required";
    setErrors(found);
    if (Object.keys(found).length) return;
    const body = { category, amount: amount.trim(), expense_date: date, note: note.trim() || null };
    const url = expense ? `${tripUrl(tripId)}/expenses/${expense.id}` : `${tripUrl(tripId)}/expenses`;
    const outcome = await run(url, jsonInit(expense ? "PATCH" : "POST", body), expense ? "Expense updated." : "Expense added.");
    if (outcome.ok) onDone();
    else setErrors(fieldErrors(outcome.detail));
  }

  const describe = (key: string) => ({
    "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${prefix}-${key}-error` : undefined,
  });
  const error = (key: string) => errors[key] && <p className="form-error" id={`${prefix}-${key}-error`}>{errors[key]}</p>;

  return (
    <form className="form" onSubmit={save} noValidate aria-label={expense ? "Edit expense" : "Add expense"}
      onKeyDown={(e) => { if (e.key === "Escape" && !busy) onCancel(); }}>
      <div className="form-grid">
        <div className="field">
          <label htmlFor={`${prefix}-category`}>Category</label>
          <select id={`${prefix}-category`} autoFocus value={category} onChange={(e) => setCategory(e.target.value as ExpenseCategory)}>
            {Object.entries(CATEGORY_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor={`${prefix}-amount`}>Amount (₹)</label>
          <input id={`${prefix}-amount`} type="text" inputMode="decimal" autoComplete="off" value={amount} onChange={(e) => setAmount(e.target.value)} {...describe("amount")} />
          {error("amount")}
        </div>
        <div className="field">
          <label htmlFor={`${prefix}-expense_date`}>Date</label>
          <input id={`${prefix}-expense_date`} type="date" value={date} onChange={(e) => setDate(e.target.value)} {...describe("expense_date")} />
          {error("expense_date")}
        </div>
        <div className="field">
          <label htmlFor={`${prefix}-note`}>Note (optional)</label>
          <input id={`${prefix}-note`} type="text" maxLength={500} autoComplete="off" value={note} onChange={(e) => setNote(e.target.value)} {...describe("note")} />
          {error("note")}
        </div>
      </div>
      <div className="actions">
        <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : "Save expense"}</button>
        <button className="btn secondary" type="button" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
      {message?.failed && <FormMessage message={message} />}
    </form>
  );
}
