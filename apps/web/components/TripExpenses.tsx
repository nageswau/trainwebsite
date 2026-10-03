"use client";

import { useState } from "react";

import FormMessage from "@/components/FormMessage";
import TripExpenseRowForm from "@/components/TripExpenseRowForm";
import { CATEGORY_LABEL, formatInr, tripUrl, type Trip, type TripExpense } from "@/lib/bdmTravel";
import { refocus } from "@/lib/focus";
import { formatCalendarDate } from "@/lib/formatDate";
import { useTripWrite } from "@/lib/useTripWrite";

const ADD_ID = "expense-add";
const cents = (value: string) => Math.round(Number(value) * 100);

function difference(estimated: string, actual: string): string {
  const diff = cents(actual) - cents(estimated);
  if (diff === 0) return "On the estimate";
  return `${formatInr(String(Math.abs(diff) / 100))} ${diff > 0 ? "over" : "under"} the estimate`;
}

const lineName = (e: TripExpense) => `${CATEGORY_LABEL[e.category]} expense of ${formatInr(e.amount)}`;

// bdm-010 (T5/T7, D15): the cost summary and the itemized lines. Lines can be added once the trip is approved (the API's
// `can_add_expense`); actual cost is always the API's sum. Delete is confirmed inline; focus returns to a stable control.
export default function TripExpenses({ trip, ownerView = true }: { trip: Trip; ownerView?: boolean }) {
  const [editing, setEditing] = useState<string | null>(null); // "new" or an expense id
  const [deleting, setDeleting] = useState<TripExpense | null>(null);
  const { busy, message, run, announce, resultProps } = useTripWrite();
  const editable = trip.can_add_expense;
  const closeForm = () => {
    setEditing(null);
    refocus(ADD_ID);
  };
  // QA10-02: the line form unmounts on save, so the list announces the result and takes focus.
  const saved = (text: string) => {
    setEditing(null);
    announce(text);
  };

  async function remove(expense: TripExpense) {
    const outcome = await run(`${tripUrl(trip.id)}/expenses/${expense.id}`, { method: "DELETE" }, "Expense deleted.");
    if (outcome.ok) setDeleting(null); // the hook moves focus to the result
  }

  return (
    <div>
      <dl role="group" aria-label="Costs" className="form-grid" style={{ margin: "0 0 16px" }}>
        <div><dt className="muted">Estimated</dt><dd style={{ margin: 0 }}>{formatInr(trip.estimated_cost)}</dd></div>
        <div><dt className="muted">Actual</dt><dd style={{ margin: 0 }}>{formatInr(trip.actual_cost)}</dd></div>
        {/* QA10-10: no "under the estimate" before anything has been spent */}
        {trip.expenses.length > 0 && <div><dt className="muted">Difference</dt><dd style={{ margin: 0 }}>{difference(trip.estimated_cost, trip.actual_cost)}</dd></div>}
      </dl>
      {trip.expenses.length === 0 ? (
        <p className="muted" role="status">No expenses yet.</p>
      ) : (
        <div className="table-wrap" role="region" aria-label="Expenses" tabIndex={0}>
          <table>
            <caption className="visually-hidden">Expense lines</caption>
            <thead>
              <tr><th scope="col">Date</th><th scope="col">Category</th><th scope="col">Amount</th><th scope="col">Note</th>{editable && <th scope="col">Actions</th>}</tr>
            </thead>
            <tbody>
              {trip.expenses.map((e) => (
                <tr key={e.id}>
                  <td>{formatCalendarDate(e.expense_date)}</td>
                  <td>{CATEGORY_LABEL[e.category]}</td>
                  <td>{formatInr(e.amount)}</td>
                  <td style={{ whiteSpace: "pre-wrap" }}>{e.note ?? "—"}</td>
                  {editable && (
                    <td>
                      <div className="actions" style={{ marginTop: 0 }}>
                        <button type="button" className="btn ghost small" aria-label={`Edit ${lineName(e)}`} disabled={busy} onClick={() => setEditing(e.id)}>Edit</button>
                        <button type="button" className="btn ghost small" aria-label={`Delete ${lineName(e)}`} disabled={busy} onClick={() => setDeleting(e)}>Delete</button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {/* QA10-10: only the owner, and only while the trip can still be approved (not cancelled) */}
      {ownerView && !editable && trip.approval_status !== "approved" && trip.travel_status === "planned" && <p className="muted">Expenses can be added once the trip is approved.</p>}
      {deleting && (
        <div className="form-warning" role="group" aria-labelledby="expense-delete-title" style={{ marginTop: 12 }}
          onKeyDown={(e) => { if (e.key === "Escape" && !busy) { setDeleting(null); refocus(ADD_ID); } }}>
          <p id="expense-delete-title"><strong>Delete the {lineName(deleting)}?</strong></p>
          <div className="actions">
            <button autoFocus type="button" className="btn" disabled={busy} onClick={() => remove(deleting)}>{busy ? "Saving…" : "Delete expense"}</button>
            <button type="button" className="btn secondary" disabled={busy} onClick={() => { setDeleting(null); refocus(ADD_ID); }}>Keep</button>
          </div>
        </div>
      )}
      {editing ? (
        <TripExpenseRowForm tripId={trip.id} expense={trip.expenses.find((e) => e.id === editing)} defaultDate={trip.travel_date}
          onDone={saved} onCancel={closeForm} />
      ) : (
        editable && <div className="actions"><button id={ADD_ID} type="button" className="btn secondary" disabled={busy} onClick={() => setEditing("new")}>Add expense</button></div>
      )}
      <div {...resultProps}>{message && <FormMessage message={message} style={{ marginTop: 12 }} />}</div>
    </div>
  );
}
