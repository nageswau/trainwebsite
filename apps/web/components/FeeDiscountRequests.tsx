"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";

import { money } from "@/components/FeeAccountSummary";
import { sendJson } from "@/lib/apiErrors";
import { formatCalendarDate } from "@/lib/formatDate";
import { DISCOUNT_STATUS, discountRequestsUrl, type DiscountRequest } from "@/lib/feeDiscounts";

/** itc-014 (DEC-SCOPE-363): under a fee account on the staff student record -- the enrolment's discount requests and, while something is
 *  owed and none is waiting, a form to ask for one. A request changes nothing until an approver (never the requester) approves it. */
export default function FeeDiscountRequests({ enrollmentId, balance, currency }: { enrollmentId: string; balance: number; currency: string }) {
  const url = discountRequestsUrl(enrollmentId);
  const [items, setItems] = useState<DiscountRequest[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch(url, { cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      const data = await r.json();
      if (!Array.isArray(data)) throw new Error("shape");
      setItems(data);
    } catch {
      setLoadError(true);
    }
  }, [url]);

  useEffect(() => {
    load();
  }, [load]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const value = Number(amount);
    if (!/^\d+(\.\d{1,2})?$/.test(amount.trim()) || value <= 0 || value > balance) {
      return setNotice({ text: `Enter an amount above 0 and no more than ${money(currency, balance)}, the balance still owed.`, failed: true });
    }
    if (!reason.trim()) return setNotice({ text: "Give a reason for the discount.", failed: true });
    setBusy(true);
    setNotice(null);
    const outcome = await sendJson(url, "POST", { amount: value, reason: reason.trim() });
    setBusy(false);
    if (!outcome.ok) return setNotice({ text: outcome.message, failed: true });
    setAmount("");
    setReason("");
    setNotice({ text: "Discount requested. It changes the fee only once an approver approves it.", failed: false });
    await load();
  }

  const pending = items?.some((i) => i.status === "pending");
  const fieldId = `discount-${enrollmentId}`;
  return (
    <section aria-labelledby={`${fieldId}-heading`} style={{ marginTop: 12, display: "grid", gap: 8 }}>
      <h4 id={`${fieldId}-heading`} style={{ margin: 0, fontSize: 15 }}>Discounts and waivers</h4>
      {loadError ? (
        <p className="form-error" role="alert" style={{ margin: 0 }}>Discount requests could not be loaded. Refresh the page to try again.</p>
      ) : items === null ? (
        <p className="muted" role="status" style={{ margin: 0 }}>Loading…</p>
      ) : items.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No discount has been requested yet.</p>
      ) : (
        <ul aria-label="Discount requests" className="list-clean" style={{ display: "grid", gap: 8, margin: 0 }}>
          {items.map((i) => (
            <li key={i.id} style={{ fontSize: 13 }}>
              <span style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                <span>{money(currency, i.amount)} · {i.reason}</span>
                <span className={DISCOUNT_STATUS[i.status].tone}>{DISCOUNT_STATUS[i.status].label}</span>
              </span>
              <span className="muted" style={{ display: "block" }}>
                Asked by {i.requested_by.full_name} on {formatCalendarDate(i.created_at)}
                {i.decided_by ? ` · Decided by ${i.decided_by.full_name}${i.decision_note ? `: ${i.decision_note}` : ""}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
      {items !== null && !pending && balance > 0 && (
        <form onSubmit={submit} noValidate style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor={`${fieldId}-amount`}>Discount amount ({currency})</label>
            <input id={`${fieldId}-amount`} type="number" inputMode="decimal" min={0.01} max={balance} step="0.01" value={amount}
              onChange={(e) => setAmount(e.target.value)} disabled={busy} style={{ width: "10rem" }} />
          </div>
          <div className="field" style={{ marginBottom: 0, flex: "1 1 14rem" }}>
            <label htmlFor={`${fieldId}-reason`}>Reason</label>
            <input id={`${fieldId}-reason`} type="text" maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} disabled={busy} />
          </div>
          <button type="submit" className="btn secondary small" disabled={busy} aria-busy={busy}>{busy ? "Sending…" : "Request discount"}</button>
        </form>
      )}
      {notice && <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: 0, fontSize: 13 }}>{notice.text}</p>}
    </section>
  );
}
