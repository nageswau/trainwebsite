"use client";

import { useEffect, useState } from "react";
import Script from "next/script";

import { SCHOOL_TIME_ZONE, formatCalendarDate, formatDate } from "@/lib/formatDate";
import { newIdempotencyKey } from "@/lib/idempotencyKey";
import { openRazorpayCheckout } from "@/lib/razorpayCheckout";
import PaymentModeBanner from "./PaymentModeBanner";

type PaymentRow = {
  id: string;
  amount: number;
  currency: string;
  provider: string;
  status: string;
  due_date: string | null;
  reference_type: string;
  is_manual: boolean;
  emi_schedule_id: string | null;
  installment_no: number | null;
  // nehn-019 (DEC-SCOPE-312): `amount` is the net payable; optional so a response without them renders as before (AC3).
  gross_amount?: number;
  discount_amount?: number;
  paid_at?: string | null;
};

type EmiSchedule = {
  id: string;
  reference_type: string;
  total_amount: number;
  currency: string;
  installment_count: number;
  paid_amount?: number;
  balance?: number;
  installments: { id: string; installment_no: number; amount: number; discount_amount?: number; due_date: string | null; status: string }[];
};

// The receipt's payment date is the India calendar day (DEC-SCOPE-312 D3), so the panel shows the same day.
const paidOn = (paidAt: string) => `Paid on ${formatDate(paidAt, false, SCHOOL_TIME_ZONE)}`;

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to complete the request.";
}

// STU-010/PAY-001: the generic portal table listed payment rows as plain text with a
// raw-UUID "Start checkout" form (WorkflowPanel's checkoutSpec) -- the same "type in an id"
// UX gap fixed for ADM-001/003/005/007. This replaces it with a Pay Now action per pending
// row, receipt downloads (PRD-PAY-003, signed URLs -- STU-007's download pattern; nehn-020: no invoice for students),
// and the EMI installment timeline (PRD-STU-011).
export default function FeePaymentPanel() {
  const [rows, setRows] = useState<PaymentRow[] | null>(null);
  const [schedules, setSchedules] = useState<EmiSchedule[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);

  function load() {
    fetch("/api/v1/payments/mine")
      .then((res) => (res.ok ? res.json() : []))
      .then(setRows)
      .catch(() => setRows([]));
    fetch("/api/v1/payments/emi-schedule")
      .then((res) => (res.ok ? res.json() : []))
      .then(setSchedules)
      .catch(() => setSchedules([]));
  }

  useEffect(() => {
    load();
  }, []);

  async function payNow(row: PaymentRow) {
    setBusyId(row.id);
    setMessage(null);
    const response = await fetch(`/api/v1/payments/${row.id}/checkout`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": newIdempotencyKey() },
      body: JSON.stringify({ provider: "razorpay" }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      setBusyId(null);
      setMessage({ id: row.id, text: detailMessage(data.detail), failed: true });
      return;
    }
    if (data.status === "configuration_required") {
      setBusyId(null);
      setMessage({ id: row.id, text: "Payment gateway is not configured yet.", failed: true });
      return;
    }
    // Manual/other providers have no client-side checkout widget to open -- the previous
    // static message still applies to those. Razorpay's own real order id/key are already
    // returned by the backend; this is what was previously discarded instead of actually
    // opening the checkout.
    if (data.provider !== "razorpay" || !data.key_id || !data.provider_order_id) {
      setBusyId(null);
      setMessage({ id: row.id, text: "Checkout session created. Continue with the configured payment provider.", failed: false });
      load();
      return;
    }
    const opened = await openRazorpayCheckout(data, {
      description: row.reference_type,
      // Razorpay's own documented client-side confirmation step: the checkout widget
      // calls this the instant a payment succeeds in the browser, with a signature
      // this app can verify itself -- not just a hope that the webhook (which can
      // never reach a local dev server at all) eventually arrives. Without this, "Pay
      // Now" and no receipt option stayed forever after a real successful payment.
      onPaid: async (response) => {
        setMessage({ id: row.id, text: "Confirming payment…", failed: false });
        const verifyResponse = await fetch(`/api/v1/payments/${row.id}/verify`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(response),
        });
        const verifyData = await verifyResponse.json().catch(() => ({}));
        if (!verifyResponse.ok) {
          setMessage({ id: row.id, text: detailMessage(verifyData.detail), failed: true });
          return;
        }
        setMessage({ id: row.id, text: "Payment confirmed. Your receipt is ready to download.", failed: false });
        load();
      },
      onDismiss: () => setMessage({ id: row.id, text: "Checkout closed before completing payment.", failed: false }),
    });
    setBusyId(null);
    if (!opened) setMessage({ id: row.id, text: "Unable to load the payment provider. Please try again.", failed: true });
  }

  async function downloadReceipt(row: PaymentRow) {
    setBusyId(`${row.id}-receipt`);
    setMessage(null);
    const response = await fetch(`/api/v1/payments/${row.id}/receipt`);
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ id: row.id, text: detailMessage(data.detail), failed: true });
      return;
    }
    window.open(data.url, "_blank", "noreferrer");
  }

  if (rows === null || schedules === null) {
    return (
      <div className="action-card">
        <h3>Fee Payments</h3>
        <p className="muted">Loading your payments…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <Script src="https://checkout.razorpay.com/v1/checkout.js" strategy="afterInteractive" />
      <h3>Fee Payments</h3>
      <PaymentModeBanner />
      {rows.length === 0 ? (
        <p className="muted">No payment records yet.</p>
      ) : (
        <div className="grid two" style={{ marginTop: 16 }}>
          {rows.map((row) => (
            <div className="card" key={row.id}>
              <span className="badge">{row.status}</span>
              <h4 style={{ marginTop: 10 }}>{row.reference_type}{row.installment_no ? ` — Installment ${row.installment_no}` : ""}</h4>
              {row.discount_amount && row.gross_amount ? (
                <>
                  <p className="muted" style={{ fontSize: 13 }}>Original {row.currency} {row.gross_amount.toLocaleString()} · Discount {row.currency} {row.discount_amount.toLocaleString()}</p>
                  <p style={{ fontSize: 13 }}>{["paid", "succeeded"].includes(row.status) ? "Amount paid" : "Payable"} {row.currency} {row.amount.toLocaleString()}{row.due_date ? ` · due ${formatCalendarDate(row.due_date)}` : ""}</p>
                </>
              ) : (
                <p className="muted" style={{ fontSize: 13 }}>{row.currency} {row.amount.toLocaleString()}{row.due_date ? ` · due ${formatCalendarDate(row.due_date)}` : ""}</p>
              )}
              {row.paid_at && <p className="muted" style={{ fontSize: 13 }}>{paidOn(row.paid_at)}</p>}
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
                {["pending", "overdue"].includes(row.status) && (
                  <button className="btn small" disabled={busyId === row.id} onClick={() => payNow(row)}>
                    {busyId === row.id ? "Preparing…" : "Pay Now"}
                  </button>
                )}
                {["paid", "succeeded"].includes(row.status) && (
                  <button className="btn small secondary" disabled={busyId === `${row.id}-receipt`} onClick={() => downloadReceipt(row)}>
                    Receipt
                  </button>
                )}
              </div>
              {message?.id === row.id && (
                <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8, fontSize: 13 }}>
                  {message.text}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {schedules.length > 0 && (
        <>
          <h4 style={{ marginTop: 24 }}>EMI Schedule</h4>
          {schedules.map((schedule) => (
            <div key={schedule.id} style={{ marginBottom: 16 }}>
              <p className="muted" style={{ fontSize: 13 }}>
                {schedule.reference_type} — {schedule.currency} {schedule.total_amount.toLocaleString()} across {schedule.installment_count} installments
              </p>
              {schedule.balance !== undefined && schedule.paid_amount !== undefined && (
                <p style={{ fontSize: 13 }}>
                  Paid {schedule.currency} {schedule.paid_amount.toLocaleString()} · Remaining balance {schedule.currency} {schedule.balance.toLocaleString()}
                </p>
              )}
              <ul className="list-clean">
                {schedule.installments.map((i) => (
                  <li key={i.id}>
                    Installment {i.installment_no}: {schedule.currency} {i.amount.toLocaleString()}
                    {i.discount_amount ? ` (${schedule.currency} ${i.discount_amount.toLocaleString()} discount applied)` : ""}
                    {i.due_date ? ` · due ${formatCalendarDate(i.due_date)}` : ""} — <span className="badge">{i.status}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
