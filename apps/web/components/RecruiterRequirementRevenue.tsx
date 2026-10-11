"use client";
import { type ReactNode, useEffect, useState } from "react";

import { DetailList } from "@/components/BdmOrganizationProfileDetails";
import RecruiterInvoiceCard from "@/components/RecruiterInvoiceCard";
import RecruiterRevenueForm, { type RevenueField } from "@/components/RecruiterRevenueForm";
import { sendRequest } from "@/lib/apiErrors";
import { formatCalendarDate } from "@/lib/formatDate";
import { FEE_BASES } from "@/lib/recruiterContracts";
import {
  feeSourceText, INVOICES_URL, inr, invoiceActionUrl, isRequirementRevenue, requirementFeeUrl, requirementRevenueUrl, type RequirementRevenue,
} from "@/lib/recruiterRevenue";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Mode = { kind: "view" } | { kind: "fee" } | { kind: "invoice" } | { kind: "pay" | "cancel"; id: string; number: string };

const FEE_FIELDS: RevenueField[] = [
  { name: "fee_basis", label: "Fee basis", kind: "select", options: FEE_BASES },
  { name: "fee_value", label: "Fee per hire", kind: "amount", hint: "Rupees per hire, or a percentage of CTC. Leave both blank to use the company contract's fee." },
];
const INVOICE_FIELDS: RevenueField[] = [
  { name: "invoice_number", label: "Invoice number", kind: "text", required: true, max: 40 },
  { name: "invoice_date", label: "Invoice date", kind: "date", required: true },
  { name: "due_date", label: "Payment due", kind: "date", required: true },
  { name: "amount", label: "Amount (₹)", kind: "amount", required: true, hint: "As invoiced. EduSphere computes no GST." },
  { name: "note", label: "Note", kind: "textarea", max: 500 },
];
const PAYMENT_FIELDS: RevenueField[] = [
  { name: "received_on", label: "Received date", kind: "date", required: true },
  { name: "amount", label: "Amount (₹)", kind: "amount", required: true },
  { name: "reference", label: "Reference (UTR / cheque no.)", kind: "text", max: 100 },
];
const CANCEL_FIELDS: RevenueField[] = [{ name: "reason", label: "Reason", kind: "textarea", required: true, max: 500 }];

function figures(r: RequirementRevenue): [string, ReactNode][] {
  const unpriced = r.unpriced_hires > 0 ? ` (${r.unpriced_hires} joined candidate${r.unpriced_hires === 1 ? " has" : "s have"} no CTC in INR and ${r.unpriced_hires === 1 ? "is" : "are"} not counted)` : "";
  return [
    ["Candidates selected", String(r.selected)],
    ["Candidates joined", String(r.joined)],
    ["Fee per hire", feeSourceText(r.fee)],
    ["Expected revenue", r.expected_revenue === null ? "No fee set" : `${inr(r.expected_revenue)}${unpriced}`],
    ["Total invoiced", inr(r.invoiced)],
    ["Payment received", inr(r.received)],
    ["Outstanding amount", inr(r.outstanding)],
  ];
}

// rec-031 (spec §4): the requirement's §23 revenue -- figures computed by the API (Joined only, AC3), the fee and where it comes from, the
// joined hires, and the invoices with their payments. Add invoice / Record payment / Cancel invoice / the fee override render from
// `permissions` only; the server enforces every rule. Each write re-reads the figures and announces a notice.
export default function RecruiterRequirementRevenue({ requirementId }: { requirementId: string }) {
  const [data, setData] = useState<RequirementRevenue | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const [mode, setMode] = useState<Mode>({ kind: "view" });
  const [notice, setNotice] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (part: string) => `revenue-${requirementId}-${part}`;

  async function reload() {
    const outcome = await sendRequest(requirementRevenueUrl(requirementId), { method: "GET" });
    if (outcome.ok && isRequirementRevenue(outcome.data)) {
      setData(outcome.data);
      return setState("ready");
    }
    if (data === null) setState("failed");
    else setNotice("Unable to show the latest revenue. Reload the page.");
  }

  useEffect(() => {
    void reload();
  }, [requirementId]); // eslint-disable-line react-hooks/exhaustive-deps -- load once per requirement; writes call reload()

  function done(text: string, next?: Record<string, unknown>) {
    setMode({ kind: "view" });
    setNotice(text);
    if (next && isRequirementRevenue(next)) setData(next);
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
        <p className="form-error">Unable to load revenue.</p>
        <button type="button" className="btn secondary small" onClick={() => { setState("loading"); void reload(); }}>Try again</button>
      </div>
    );
  } else if (mode.kind === "fee") {
    body = (
      <RecruiterRevenueForm id={id("fee")} label="Fee for this requirement" submitLabel="Save fee" url={requirementFeeUrl(requirementId)} method="PUT" fields={FEE_FIELDS}
        initial={{ fee_basis: data.fee.override?.basis ?? "", fee_value: data.fee.override?.value ?? "" }} onDone={(d) => done("Fee saved.", d)} onCancel={back(id("set-fee"))} />
    );
  } else if (mode.kind === "invoice") {
    body = (
      <RecruiterRevenueForm id={id("invoice")} label="Add invoice" submitLabel="Save invoice" url={INVOICES_URL} method="POST" fields={INVOICE_FIELDS}
        extra={{ requirement_id: requirementId }} onDone={() => done("Invoice saved.")} onCancel={back(id("add-invoice"))} />
    );
  } else if (mode.kind === "pay" || mode.kind === "cancel") {
    const pay = mode.kind === "pay";
    body = (
      <RecruiterRevenueForm id={id(`${mode.kind}-${mode.id}`)} label={`${pay ? "Record payment for" : "Cancel invoice"} ${mode.number}`} submitLabel={pay ? "Save payment" : "Cancel invoice"}
        url={invoiceActionUrl(mode.id, pay ? "payments" : "cancel")} method="POST" fields={pay ? PAYMENT_FIELDS : CANCEL_FIELDS}
        onDone={() => done(pay ? "Payment saved." : "Invoice cancelled.")} onCancel={back(id(`${mode.kind}-${mode.id}`))} />
    );
  } else {
    body = (
      <>
        <DetailList rows={figures(data)} />
        {data.over_invoiced && <p className="form-message">Invoiced more than the expected revenue from joined candidates. Check for a candidate who did not join.</p>}
        {data.hires.length > 0 && (
          <details>
            <summary>Joined candidates ({data.hires.length})</summary>
            <ul style={{ margin: 0, paddingLeft: 18 }} aria-label="Joined candidates">
              {data.hires.map((h) => (
                <li key={h.application_id} style={{ overflowWrap: "anywhere" }}>
                  {h.candidate.name} ({h.candidate.code}){h.joined_on ? ` · joined ${formatCalendarDate(h.joined_on)}` : ""} · {h.fee === null ? (data.fee.basis ? "no CTC in INR" : "no fee set") : inr(h.fee)}
                </li>
              ))}
            </ul>
          </details>
        )}
        <div className="actions">
          {data.permissions.can_invoice && <button id={id("add-invoice")} type="button" className="btn small" onClick={() => setMode({ kind: "invoice" })}>Add invoice</button>}
          {data.permissions.can_set_fee && (
            <button id={id("set-fee")} type="button" className="btn secondary small" onClick={() => setMode({ kind: "fee" })}>Set fee for this requirement</button>
          )}
        </div>
        <h4 style={{ margin: "8px 0 0" }}>Invoices</h4>
        {data.invoices.length === 0 ? (
          <p className="muted">No invoices yet.</p>
        ) : (
          <ul aria-label="Invoices" style={{ padding: 0, margin: 0, display: "grid", gap: 8 }}>
            {data.invoices.map((i) => (
              <RecruiterInvoiceCard key={i.id} invoice={i}>
                {(i.permissions.can_pay || i.permissions.can_cancel) && (
                  <div className="actions">
                    {i.permissions.can_pay && (
                      <button id={id(`pay-${i.id}`)} type="button" className="btn secondary small" aria-label={`Record payment for ${i.invoice_number}`}
                        onClick={() => setMode({ kind: "pay", id: i.id, number: i.invoice_number })}>Record payment</button>
                    )}
                    {i.permissions.can_cancel && (
                      <button id={id(`cancel-${i.id}`)} type="button" className="btn secondary small" aria-label={`Cancel invoice ${i.invoice_number}`}
                        onClick={() => setMode({ kind: "cancel", id: i.id, number: i.invoice_number })}>Cancel invoice</button>
                    )}
                  </div>
                )}
              </RecruiterInvoiceCard>
            ))}
          </ul>
        )}
      </>
    );
  }

  return (
    <section id="requirement-revenue" className="action-card wide" aria-labelledby={id("title")}>
      <h3 id={id("title")}>Revenue</h3>
      {notice && <p id={id("notice")} className="form-message" role="status" tabIndex={-1}>{notice}</p>}
      {body}
    </section>
  );
}
