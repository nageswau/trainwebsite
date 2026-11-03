"use client";

import { useEffect, useState } from "react";

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
};

const STATE_LABELS: Record<FeeAccount["state"], string> = {
  not_billed: "No fee billed",
  enrolled_pending_payment: "Payment pending",
  partially_paid: "Partially paid",
  fully_paid: "Fully paid",
};

const money = (currency: string, value: number) => `${currency} ${value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export function FeeAccountCard({ account }: { account: FeeAccount }) {
  const rows: [string, number][] = [
    ["Course fee", account.course_fee],
    ["Approved discount", account.discount_approved],
    ["Tax", account.tax],
    ["Total payable", account.total_payable],
    ["Paid", account.paid_confirmed],
    ["Credits", account.credits],
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
