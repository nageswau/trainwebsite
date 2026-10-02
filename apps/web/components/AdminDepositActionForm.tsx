"use client";

import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import { sendJson } from "@/lib/apiErrors";
import { formatInr, todayIso } from "@/lib/agentApplications";

export type AdminDeposit = {
  id: string;
  application_id: string;
  agency: string | null;
  student: string;
  university: string;
  amount: string | null;
  currency: string;
  status: "pending" | "paid" | "remitted" | "refunded";
  due_date: string | null;
  paid_at: string | null;
  paid_by: string | null;
  remitted_at: string | null;
  remittance_reference: string | null;
  refunded_at: string | null;
  refund_amount: string | null;
  refund_reason: string | null;
  unlinked_paid_payments: number;
};
export type DepositAction = "remit" | "refund";
export const DEPOSITS_URL = "/api/v1/overseas-admin/deposits";
// The server's state machine (D3): remit from paid; one refund from paid or remitted.
export const DEPOSIT_ACTIONS_FOR: Record<AdminDeposit["status"], DepositAction[]> = { pending: [], paid: ["remit", "refund"], remitted: ["refund"], refunded: [] };
export const ACTION_LABELS: Record<DepositAction, string> = { remit: "Record remittance", refund: "Record refund" };

type Props = { deposit: AdminDeposit; action: DepositAction; onDone: (next: AdminDeposit) => void; onCancel: () => void };

// AGN-011 (DEC-SCOPE-058 D3/D12): record a remittance (date + reference) or the one refund (date, amount up to what was paid, reason).
// A refund asks for confirmation first -- it is final. The server checks every rule again; its message stays beside the form with the
// entry kept. Escape cancels.
export default function AdminDepositActionForm({ deposit, action, onDone, onCancel }: Props) {
  const refund = action === "refund";
  const id = (part: string) => `deposit-${action}-${part}-${deposit.id}`;
  const [on, setOn] = useState(todayIso());
  const [reference, setReference] = useState("");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const inFlight = useRef(false);
  const name = `${ACTION_LABELS[action]} for ${deposit.student}`;

  async function save() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    const body = refund ? { refunded_on: on, amount: amount.trim(), reason: reason.trim() } : { remitted_on: on, reference: reference.trim() };
    const outcome = await sendJson(`${DEPOSITS_URL}/${deposit.id}/${action}`, "POST", body);
    inFlight.current = false;
    setBusy(false);
    setConfirming(false);
    if (!outcome.ok) return setFailure(outcome.message);
    onDone(outcome.data as AdminDeposit);
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (refund) setConfirming(true);
    else save();
  }

  return (
    <form className="form" aria-label={name} onSubmit={submit} onKeyDown={(event: KeyboardEvent) => event.key === "Escape" && (confirming ? setConfirming(false) : onCancel())}>
      <div className="field">
        <label htmlFor={id("on")}>{refund ? "Refunded on" : "Remitted on"}</label>
        <input id={id("on")} type="date" required max={todayIso()} value={on} onChange={(event) => setOn(event.target.value)} autoFocus />
      </div>
      {refund ? (
        <>
          <div className="field">
            <label htmlFor={id("amount")}>Refund amount in ₹ (INR)</label>
            <input id={id("amount")} inputMode="decimal" required autoComplete="off" aria-describedby={id("max")} value={amount} onChange={(event) => setAmount(event.target.value)} />
            {deposit.amount && (
              <small id={id("max")} className="muted">
                At most {formatInr(deposit.amount)}
              </small>
            )}
          </div>
          <div className="field">
            <label htmlFor={id("reason")}>Reason</label>
            <textarea id={id("reason")} required maxLength={500} rows={3} value={reason} onChange={(event) => setReason(event.target.value)} />
          </div>
        </>
      ) : (
        <div className="field">
          <label htmlFor={id("reference")}>Remittance reference</label>
          <input id={id("reference")} required maxLength={100} autoComplete="off" value={reference} onChange={(event) => setReference(event.target.value)} />
        </div>
      )}
      {failure && (
        <p className="form-error" role="alert">
          {failure}
        </p>
      )}
      {confirming ? (
        <div role="group" aria-label="Confirm refund">
          <p>
            Record a refund of {amount.trim() ? formatInr(amount.trim()) : "this amount"} for {deposit.student}? It cannot be changed afterwards.
          </p>
          <div className="actions">
            <button type="button" className="btn small" disabled={busy} onClick={save} autoFocus>
              {busy ? "Saving…" : "Yes, record refund"}
            </button>
            <button type="button" className="btn ghost small" onClick={() => setConfirming(false)}>
              Go back
            </button>
          </div>
        </div>
      ) : (
        <div className="actions">
          <button className="btn small" disabled={busy}>
            {busy ? "Saving…" : refund ? "Save refund" : "Save remittance"}
          </button>
          <button type="button" className="btn ghost small" onClick={onCancel}>
            Cancel
          </button>
        </div>
      )}
    </form>
  );
}
