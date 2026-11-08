"use client";
import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";

import { DetailList } from "@/components/BdmOrganizationProfileDetails";
import RecruiterRevenueForm, { type RevenueField } from "@/components/RecruiterRevenueForm";
import { sendRequest } from "@/lib/apiErrors";
import { formatCalendarDate } from "@/lib/formatDate";
import { inr } from "@/lib/recruiterRevenue";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { BILL_KINDS, billActionUrl, isVendorBillList, type MoneyTotals, type VendorBillList, vendorBillsUrl, vendorPerformancePath } from "@/lib/vendorCommercials";

type Mode = { kind: "view" } | { kind: "bill" } | { kind: "pay" | "cancel"; id: string; number: string };

const BILL_FIELDS: RevenueField[] = [
  { name: "kind", label: "Type", kind: "select", required: true, options: BILL_KINDS },
  { name: "bill_number", label: "Bill number", kind: "text", required: true, max: 40 },
  { name: "bill_date", label: "Bill date", kind: "date", required: true },
  { name: "due_date", label: "Payment due", kind: "date", required: true },
  { name: "amount", label: "Amount (₹)", kind: "amount", required: true },
  { name: "milestone", label: "Payment milestone", kind: "text", max: 120, hint: "Which milestone of the vendor agreement this settles, e.g. On joining." },
  { name: "note", label: "Note", kind: "textarea", max: 500 },
];
const PAYMENT_FIELDS: RevenueField[] = [
  { name: "paid_on", label: "Payment date", kind: "date", required: true },
  { name: "amount", label: "Amount (₹)", kind: "amount", required: true },
  { name: "reference", label: "Reference (UTR / cheque no.)", kind: "text", max: 100 },
];
const CANCEL_FIELDS: RevenueField[] = [{ name: "reason", label: "Reason", kind: "textarea", required: true, max: 500 }];

const totalsText = (t: MoneyTotals) =>
  `Billed ${inr(t.billed)} · Paid ${inr(t.paid)} · Outstanding ${inr(t.outstanding)}${t.last_paid_on ? ` · last payment ${formatCalendarDate(t.last_paid_on)}` : ""}`;

// pob-012 (DEC-SCOPE-433 W2/W3/W9): a vendor's bills -- what we owe them and what they owe us, recorded by hand, with their payments.
// Record bill / Record payment / Cancel render from `can_edit` / `permissions` only; the server enforces every rule. Each write re-reads.
export default function RecruiterVendorCommercials({ companyId }: { companyId: string }) {
  const [data, setData] = useState<VendorBillList | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const [mode, setMode] = useState<Mode>({ kind: "view" });
  const [notice, setNotice] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (part: string) => `vendor-bills-${companyId}-${part}`;

  async function reload() {
    const outcome = await sendRequest(vendorBillsUrl(companyId), { method: "GET" });
    if (outcome.ok && isVendorBillList(outcome.data)) {
      setData(outcome.data);
      return setState("ready");
    }
    if (data === null) setState("failed");
    else setNotice("Unable to show the latest bills. Reload the page.");
  }

  useEffect(() => {
    void reload();
  }, [companyId]); // eslint-disable-line react-hooks/exhaustive-deps -- load once per vendor; writes call reload()

  function done(text: string) {
    setMode({ kind: "view" });
    setNotice(text);
    focus(id("notice"));
    void reload();
  }
  const back = (target: string) => () => {
    setMode({ kind: "view" });
    focus(target);
  };

  let body: ReactNode;
  if (state === "loading") {
    body = <p className="muted" aria-live="polite">Loading…</p>;
  } else if (state === "failed" || data === null) {
    body = (
      <div role="alert">
        <p className="form-error">Unable to load vendor bills.</p>
        <button type="button" className="btn secondary small" onClick={() => { setState("loading"); void reload(); }}>Try again</button>
      </div>
    );
  } else if (mode.kind === "bill") {
    body = (
      <RecruiterRevenueForm id={id("bill")} label="Record bill" submitLabel="Save bill" url={vendorBillsUrl(companyId)} method="POST" fields={BILL_FIELDS}
        initial={{ kind: "payable" }} onDone={() => done("Bill saved.")} onCancel={back(id("add-bill"))} />
    );
  } else if (mode.kind === "pay" || mode.kind === "cancel") {
    const pay = mode.kind === "pay";
    body = (
      <RecruiterRevenueForm id={id(`${mode.kind}-${mode.id}`)} label={`${pay ? "Record payment for" : "Cancel bill"} ${mode.number}`} submitLabel={pay ? "Save payment" : "Cancel bill"}
        url={billActionUrl(mode.id, pay ? "payments" : "cancel")} method="POST" fields={pay ? PAYMENT_FIELDS : CANCEL_FIELDS}
        onDone={() => done(pay ? "Payment saved." : "Bill cancelled.")} onCancel={back(id(`${mode.kind}-${mode.id}`))} />
    );
  } else {
    body = (
      <>
        <DetailList rows={[["We owe the vendor", totalsText(data.totals.payable)], ["The vendor owes us", totalsText(data.totals.receivable)]]} />
        <div className="actions">
          {data.can_edit && <button id={id("add-bill")} type="button" className="btn small" onClick={() => setMode({ kind: "bill" })}>Record bill</button>}
          <Link className="btn secondary small" href={vendorPerformancePath(companyId)}>Vendor performance</Link>
        </div>
        <h4 style={{ margin: "8px 0 0" }}>Bills</h4>
        {data.items.length === 0 ? (
          <p className="muted">No bills yet.</p>
        ) : (
          <ul aria-label="Vendor bills" style={{ padding: 0, margin: 0, display: "grid", gap: 8 }}>
            {data.items.map((b) => (
              <li key={b.id} className="action-card" style={{ listStyle: "none", gap: 4 }}>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
                  <strong style={{ overflowWrap: "anywhere" }}>{b.bill_number}</strong>
                  <span className="badge">{b.kind_label}</span>
                  <span className="badge">{b.payment_status_label}</span>
                  {b.overdue && <span className="badge status error">Overdue</span>}
                </div>
                <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                  Bill date {formatCalendarDate(b.bill_date)} · Payment due {formatCalendarDate(b.due_date)}
                  {b.milestone && <> · Milestone: {b.milestone}</>}
                  {b.requirement && <> · {b.requirement.title} ({b.requirement.code})</>}
                </p>
                <p style={{ margin: 0 }}>Amount {inr(b.amount)} · Paid {inr(b.paid)} · Outstanding {inr(b.outstanding)}</p>
                {b.note && <p style={{ margin: 0, fontSize: 13, overflowWrap: "anywhere", whiteSpace: "pre-line" }}>Note: {b.note}</p>}
                {b.cancel_reason && <p style={{ margin: 0, fontSize: 13, overflowWrap: "anywhere", whiteSpace: "pre-line" }}>Cancelled: {b.cancel_reason}</p>}
                {b.payments.length > 0 && (
                  <ul aria-label={`Payments for ${b.bill_number}`} style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                    {b.payments.map((p) => (
                      <li key={p.id} style={{ overflowWrap: "anywhere" }}>
                        {inr(p.amount)} paid {formatCalendarDate(p.paid_on)}{p.reference ? ` · ${p.reference}` : ""} · by {p.created_by.full_name}
                      </li>
                    ))}
                  </ul>
                )}
                {(b.permissions.can_pay || b.permissions.can_cancel) && (
                  <div className="actions">
                    {b.permissions.can_pay && (
                      <button id={id(`pay-${b.id}`)} type="button" className="btn secondary small" aria-label={`Record payment for ${b.bill_number}`}
                        onClick={() => setMode({ kind: "pay", id: b.id, number: b.bill_number })}>Record payment</button>
                    )}
                    {b.permissions.can_cancel && (
                      <button id={id(`cancel-${b.id}`)} type="button" className="btn secondary small" aria-label={`Cancel bill ${b.bill_number}`}
                        onClick={() => setMode({ kind: "cancel", id: b.id, number: b.bill_number })}>Cancel bill</button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </>
    );
  }

  return (
    <section className="action-card wide" aria-labelledby={id("title")}>
      <h3 id={id("title")}>Vendor commercials</h3>
      {notice && <p id={id("notice")} className="form-message" role="status" tabIndex={-1}>{notice}</p>}
      {body}
    </section>
  );
}
