"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import AgentApplicationDepositForm from "./AgentApplicationDepositForm";
import { SESSION_EXPIRED, SIGN_IN_PATH } from "@/lib/activityFeedback";
import { detailMessage, sendJson, sendRequest } from "@/lib/apiErrors";
import { AgentApplicationDetail, DEPOSIT_STATUS_LABELS, depositUrl, formatInr, PAYMENT_UNAVAILABLE } from "@/lib/agentApplications";
import { formatDateTimeIn, viewerTimeZone } from "@/lib/formatDate";
import { newIdempotencyKey } from "@/lib/idempotencyKey";
import { openRazorpayCheckout, RazorpayOrder } from "@/lib/razorpayCheckout";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Props = {
  detail: AgentApplicationDetail;
  open: boolean; // the form is showing
  canOpen: boolean; // false while read-only or while another form of the detail is open
  onOpen: () => void;
  onCancel: () => void;
  onSaved: (d: AgentApplicationDetail, message: string) => void;
  onFailed: (message: string, status?: number) => void;
  onReload: () => void;
};

type Note = { text: string; failed?: boolean; expired?: boolean; refresh?: boolean };
const NOT_COMPLETED = "Payment not completed. You can try again.";
const NOT_LOADED = "The payment window could not be loaded. Nothing has been charged. Please try again.";
const CONFIRMING = "Payment received. Confirming…";
const PENDING_AFTER_PAY = "If you were charged, the payment will appear here shortly.";

// AGN-011 (DEC-SCOPE-057 §5): the application's deposit -- the recorded terms, the status in words, Pay deposit (Razorpay Checkout,
// AC1), the receipt once paid (AC5), and the remittance/refund Overseas Admin recorded. When online payment is unavailable it says so
// and offers no Pay button (AC6). Master and Staff both act (D7); a read-only application shows the record only. The Razorpay result is
// verified by `/payments/{id}/verify`; the webhook is the durable source of truth, so a still-pending deposit after paying says so.
export default function AgentApplicationDeposit({ detail, open, canOpen, onOpen, onCancel, onSaved, onFailed, onReload }: Props) {
  const deposit = detail.deposit ?? null;
  const focusAfter = useFocusAfterRender();
  const headingId = `deposit-heading-${detail.id}`;
  const openId = `deposit-open-${detail.id}`;
  const noteId = `deposit-note-${detail.id}`;
  const [busy, setBusy] = useState<"pay" | "receipt" | null>(null);
  const [note, setNote] = useState<Note | null>(null);
  const inFlight = useRef(false); // a same-tick second click opens nothing

  function say(next: Note) {
    setNote(next);
    focusAfter(noteId);
  }

  async function verify(paymentId: string, response: unknown) {
    say({ text: CONFIRMING });
    await sendJson(`/api/v1/payments/${paymentId}/verify`, "POST", response); // the webhook still pays it if this fails
    setNote({ text: PENDING_AFTER_PAY, refresh: true }); // replaced by the paid state when the reload shows it
    onReload();
  }

  async function pay() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy("pay");
    setNote(null);
    const outcome = await sendRequest(`${depositUrl(detail.id)}/checkout`, { method: "POST", headers: { "Idempotency-Key": newIdempotencyKey() } });
    inFlight.current = false;
    setBusy(null);
    if (!outcome.ok) {
      if (outcome.status === 409 || outcome.status === 404) return onFailed(outcome.message, outcome.status);
      if (outcome.status === 401) return say({ text: `${SESSION_EXPIRED} Sign in again in a new tab, then pay.`, failed: true, expired: true });
      return say({ text: outcome.message, failed: true }); // 429 (the wait), 502 (nothing charged), others in the server's words
    }
    const data = outcome.data as Partial<RazorpayOrder> & { status?: string; payment_id?: string };
    if (data.status === "configuration_required") return say({ text: PAYMENT_UNAVAILABLE, failed: true });
    if (data.status !== "ready" || !data.payment_id || !data.key_id || !data.provider_order_id) return say({ text: NOT_LOADED, failed: true });
    const paymentId = data.payment_id;
    const opened = await openRazorpayCheckout(data as RazorpayOrder, {
      description: `University deposit — ${detail.student}`,
      onPaid: (response) => void verify(paymentId, response),
      onDismiss: () => say({ text: NOT_COMPLETED }),
    });
    if (!opened) say({ text: NOT_LOADED, failed: true });
  }

  async function downloadReceipt() {
    setBusy("receipt");
    setNote(null);
    try {
      const response = await fetch(`${depositUrl(detail.id)}/receipt`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok || typeof data.url !== "string") return say({ text: detailMessage(data.detail, "The receipt could not be opened."), failed: true });
      window.open(data.url, "_blank", "noreferrer");
    } catch {
      say({ text: "Couldn't reach the server. Check your connection and try again.", failed: true });
    } finally {
      setBusy(null);
    }
  }

  const unpaid = !deposit || deposit.status === "pending" || deposit.status === "not_required";
  const pending = deposit?.status === "pending";
  const available = detail.payment_available !== false;
  const shownNote = note?.refresh && !pending ? null : note; // once the reload shows it paid, the "appear shortly" note goes

  return (
    <section aria-labelledby={headingId}>
      <h5 id={headingId} tabIndex={-1}>
        Deposit
      </h5>
      {open ? (
        <AgentApplicationDepositForm
          detail={detail}
          onSaved={(next, message) => {
            focusAfter(headingId);
            onSaved(next, message);
          }}
          onFailed={onFailed}
          onCancel={() => {
            focusAfter(openId);
            onCancel();
          }}
        />
      ) : (
        <>
          {!deposit ? (
            <p className="muted">No deposit recorded yet.</p>
          ) : (
            <dl className="card-stack">
              <dt>Status</dt>
              <dd>
                <span className={deposit.status === "pending" ? "badge" : "status"}>{DEPOSIT_STATUS_LABELS[deposit.status]}</span>
              </dd>
              {deposit.amount && (
                <>
                  <dt>Amount</dt>
                  <dd>{formatInr(deposit.amount)}</dd>
                </>
              )}
              {deposit.required && (
                <>
                  <dt>Due date</dt>
                  <dd>{deposit.due_date ?? "—"}</dd>
                </>
              )}
              {deposit.paid_at && (
                <>
                  <dt>Paid on</dt>
                  <dd>{formatDateTimeIn(deposit.paid_at, viewerTimeZone(), true)}</dd>
                  <dt>Paid by</dt>
                  <dd>{deposit.paid_by ?? "—"}</dd>
                </>
              )}
              {deposit.remitted_at && (
                <>
                  <dt>Remitted on</dt>
                  <dd>
                    {deposit.remitted_at} · Ref. {deposit.remittance_reference}
                  </dd>
                </>
              )}
              {deposit.refunded_at && deposit.refund_amount && (
                <>
                  <dt>Refunded</dt>
                  <dd>
                    {formatInr(deposit.refund_amount)} on {deposit.refunded_at}
                  </dd>
                  <dt>Refund reason</dt>
                  <dd className="history-note">{deposit.refund_reason}</dd>
                </>
              )}
            </dl>
          )}
          {pending && !available && <p className="form-warning">{PAYMENT_UNAVAILABLE}</p>}
          {pending && available && deposit.checkout_in_progress && !note && (
            <p className="muted">A payment was started for this deposit. If it was completed, it will appear here shortly.</p>
          )}
          {shownNote && (
            <p id={noteId} tabIndex={-1} className={shownNote.failed ? "form-error" : "form-message"} role={shownNote.failed ? "alert" : "status"}>
              {shownNote.text}
              {shownNote.expired && (
                <>
                  {" "}
                  <Link href={SIGN_IN_PATH} target="_blank" rel="noopener">
                    Sign in again
                  </Link>
                </>
              )}
            </p>
          )}
          <div className="actions">
            {pending && available && canOpen && (
              <button type="button" className="btn small" disabled={busy !== null} aria-busy={busy === "pay"} onClick={pay}>
                {busy === "pay" ? "Opening checkout…" : "Pay deposit"}
              </button>
            )}
            {shownNote?.refresh && (
              <button type="button" className="btn secondary small" onClick={onReload}>
                Refresh
              </button>
            )}
            {deposit?.receipt_available && (
              <button type="button" className="btn secondary small" disabled={busy !== null} onClick={downloadReceipt}>
                {busy === "receipt" ? "Preparing…" : "Download receipt"}
              </button>
            )}
            {unpaid && canOpen && (
              <button
                id={openId}
                type="button"
                className="btn secondary small"
                onClick={() => {
                  focusAfter(`deposit-required-${deposit?.required === false ? "no" : "yes"}-${detail.id}`);
                  onOpen();
                }}
              >
                {deposit ? "Edit deposit" : "Record deposit"}
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}
