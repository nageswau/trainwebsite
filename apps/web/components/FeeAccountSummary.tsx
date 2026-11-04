"use client";

import { useEffect, useState } from "react";

import { detailMessage } from "@/lib/apiErrors";
import LocalTime from "@/components/LocalTime";
import { formatCalendarDate } from "@/lib/formatDate";

// itc-013 (DEC-SCOPE-346): an IT student's fee account per enrolment -- computed by the API from confirmed payments only, so a pending
// online payment never lowers the balance. Tax is shown as the API sends it (0 until GST is confirmed, Q-12).
export type FeeAccount = {
  enrollment_id: string;
  enrollment_code: string | null;
  course: string | null;
  batch: string | null;
  currency: string;
  course_fee: number;
  discount_approved: number;
  tax: number;
  total_payable: number;
  paid_confirmed: number;
  credits: number;
  balance: number;
  state: "not_billed" | "enrolled_pending_payment" | "partially_paid" | "fully_paid";
  // itc-018 (DEC-SCOPE-353): the oldest owed bill, null when nothing is owed; optional so an older response renders as before.
  next_due?: { amount: number; due_date: string | null } | null;
  // itc-016 (DEC-SCOPE-358): the fee rows by due date, `overdue` derived by the API (IST), with the reminders sent; optional, as above.
  installments?: FeeInstallment[];
  // itc-015 (DEC-SCOPE-364): refunds paid back out of a credit, and every credit note / write-off / refund / correction; optional, as above.
  refunded?: number;
  adjustments?: FeeAdjustment[];
};

export type FeeAdjustment = {
  id: string;
  kind: "credit_note" | "write_off" | "refund" | "reversal";
  amount: number;
  reason: string;
  payment_mode: string | null;
  reference: string | null;
  document_no: string | null;
  created_at: string;
};

const ADJUSTMENT_LABELS: Record<FeeAdjustment["kind"], string> = { credit_note: "Credit note", write_off: "Write-off", refund: "Refund", reversal: "Payment corrected" };
const DOCUMENT_LABELS: Record<FeeAdjustment["kind"], string> = { credit_note: "credit note", write_off: "write-off", refund: "refund receipt", reversal: "" };
const MODE_LABELS: Record<string, string> = { cash: "Cash", upi: "UPI", card: "Card", bank_transfer: "Bank transfer", cheque: "Cheque" };

/** itc-015: the account's adjustments, oldest first; a credit note, write-off or refund downloads its document through a signed link. */
function AdjustmentList({ currency, items }: { currency: string; items: FeeAdjustment[] }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<{ id: string; text: string } | null>(null);

  async function download(item: FeeAdjustment) {
    setBusy(item.id);
    setError(null);
    const response = await fetch(`/api/v1/it/fee-adjustments/${item.id}/document`);
    const data = await response.json().catch(() => ({}));
    setBusy(null);
    if (!response.ok) {
      setError({ id: item.id, text: detailMessage(data.detail, "The document could not be downloaded. Please try again.") });
      return;
    }
    window.open(data.url, "_blank", "noreferrer");
  }

  return (
    <>
      <h5 style={{ margin: "14px 0 6px", fontSize: 14 }}>Credits and refunds</h5>
      <ul aria-label="Credits and refunds" className="list-clean" style={{ display: "grid", gap: 8, margin: 0 }}>
        {items.map((a) => (
          <li key={a.id} style={{ fontSize: 13 }}>
            <span style={{ display: "block" }}>{`${ADJUSTMENT_LABELS[a.kind]} · ${money(currency, a.amount)} · `}<LocalTime value={a.created_at} /></span>
            {a.payment_mode && (
              <span className="muted" style={{ display: "block", overflowWrap: "anywhere" }}>
                {[MODE_LABELS[a.payment_mode] ?? a.payment_mode, a.reference ? `Ref ${a.reference}` : null].filter(Boolean).join(" · ")}
              </span>
            )}
            <span className="muted" style={{ display: "block", overflowWrap: "anywhere" }}>{a.reason}</span>
            {a.document_no && (
              <button type="button" className="btn small secondary" style={{ marginTop: 4 }} aria-label={`Download ${DOCUMENT_LABELS[a.kind]} ${a.document_no}`}
                disabled={busy === a.id} onClick={() => download(a)}>
                {busy === a.id ? "Preparing…" : `Download ${DOCUMENT_LABELS[a.kind]}`}
              </button>
            )}
            {error?.id === a.id && <p className="form-error" role="alert" style={{ margin: "4px 0 0" }}>{error.text}</p>}
          </li>
        ))}
      </ul>
    </>
  );
}

export type FeeReminder = { kind: "due_soon" | "overdue"; offset_days: number; sent_on: string };
export type FeeInstallment = {
  id: string;
  installment_no: number | null;
  amount: number;
  due_date: string | null;
  status: "pending" | "paid";
  overdue: boolean;
  reminders: FeeReminder[];
};

const days = (n: number) => `${n} day${n === 1 ? "" : "s"}`;
const reminderLabel = (r: FeeReminder) => `${r.kind === "overdue" ? `${days(r.offset_days)} overdue` : `${days(r.offset_days)} before due`} on ${formatCalendarDate(r.sent_on)}`;

function InstallmentList({ currency, items }: { currency: string; items: FeeInstallment[] }) {
  return (
    <>
      <h5 style={{ margin: "14px 0 6px", fontSize: 14 }}>Installments</h5>
      <ul aria-label="Installments" className="list-clean" style={{ display: "grid", gap: 8, margin: 0 }}>
        {items.map((i) => {
          const [label, tone] = i.status === "paid" ? ["Paid", "status"] : i.overdue ? ["Overdue", "status error"] : ["Due", "status pending"];
          return (
            <li key={i.id} style={{ fontSize: 13 }}>
              <span style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                <span>
                  {[i.installment_no ? `Installment ${i.installment_no}` : null, money(currency, i.amount), i.due_date ? `due ${formatCalendarDate(i.due_date)}` : "no due date set"]
                    .filter(Boolean).join(" · ")}
                </span>
                <span className={tone}>{label}</span>
              </span>
              {i.reminders.length > 0 ? (
                <span className="muted" style={{ display: "block" }}>Reminders sent: {i.reminders.map(reminderLabel).join("; ")}</span>
              ) : i.status === "pending" ? (
                <span className="muted" style={{ display: "block" }}>No reminder sent yet</span>
              ) : null}
            </li>
          );
        })}
      </ul>
    </>
  );
}

const STATE_LABELS: Record<FeeAccount["state"], string> = {
  not_billed: "No fee billed",
  enrolled_pending_payment: "Payment pending",
  partially_paid: "Partially paid",
  fully_paid: "Fully paid",
};

export const money = (currency: string, value: number) => `${currency} ${value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export function FeeAccountCard({ account }: { account: FeeAccount }) {
  const rows: [string, number][] = [
    ["Course fee", account.course_fee],
    ["Approved discount", account.discount_approved],
    ["Tax", account.tax],
    ["Total payable", account.total_payable],
    ["Paid", account.paid_confirmed],
    ["Credits", account.credits],
    ...(account.refunded !== undefined ? [["Refunded", account.refunded] as [string, number]] : []),
  ];
  const credit = account.balance < 0;
  return (
    <div className="card fee-account" aria-label={`Fee account for ${account.course ?? "your course"}`}>
      <span className="badge">{STATE_LABELS[account.state]}</span>
      <h4 style={{ marginTop: 10 }}>{account.course ?? "Course"}</h4>
      {account.batch && <p className="muted" style={{ fontSize: 13 }}>{account.batch}{account.enrollment_code ? ` · ${account.enrollment_code}` : ""}</p>}
      {account.state === "not_billed" ? (
        <p className="muted" style={{ fontSize: 13 }}>No fee has been billed for this enrolment yet.</p>
      ) : (
        <dl className="fee-account-figures">
          {rows.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{money(account.currency, value)}</dd>
            </div>
          ))}
          <div className="fee-account-balance">
            <dt>{credit ? "Credit" : "Balance"}</dt>
            <dd>{money(account.currency, Math.abs(account.balance))}</dd>
          </div>
          {account.next_due !== undefined && (
            <div>
              <dt>Next due</dt>
              <dd>
                {account.next_due
                  ? `${money(account.currency, account.next_due.amount)} · ${account.next_due.due_date ? formatCalendarDate(account.next_due.due_date) : "no due date set"}`
                  : "Nothing due"}
              </dd>
            </div>
          )}
        </dl>
      )}
      {account.installments && account.installments.length > 0 && <InstallmentList currency={account.currency} items={account.installments} />}
      {account.adjustments && account.adjustments.length > 0 && <AdjustmentList currency={account.currency} items={account.adjustments} />}
    </div>
  );
}

export default function FeeAccountSummary() {
  const [accounts, setAccounts] = useState<FeeAccount[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetch("/api/v1/it/student/fee-accounts")
      .then((res) => {
        if (!res.ok) throw new Error(String(res.status));
        return res.json();
      })
      .then(setAccounts)
      .catch(() => setFailed(true));
  }, []);

  return (
    <section aria-labelledby="fee-summary-heading" style={{ marginBottom: 24 }}>
      <h4 id="fee-summary-heading">Fee summary</h4>
      {failed ? (
        <p className="form-error" role="alert">Your fee summary could not be loaded. Please refresh the page.</p>
      ) : accounts === null ? (
        <p className="muted" role="status">Loading your fee summary…</p>
      ) : accounts.length === 0 ? (
        <p className="muted">You are not enrolled in a course yet.</p>
      ) : (
        <div className="grid two">
          {accounts.map((account) => <FeeAccountCard key={account.enrollment_id} account={account} />)}
        </div>
      )}
    </section>
  );
}
