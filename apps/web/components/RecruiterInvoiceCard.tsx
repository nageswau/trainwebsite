import Link from "next/link";
import type { ReactNode } from "react";

import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { formatCalendarDate } from "@/lib/formatDate";
import { type Invoice, inr } from "@/lib/recruiterRevenue";

// rec-031 (spec §4): one invoice -- number, payment status as text (never colour alone), Overdue, dates, amount / received / outstanding,
// and its payments. The receivables list adds the requirement link; the requirement section adds its actions as `children`.
export default function RecruiterInvoiceCard({ invoice: i, showRequirement = false, children }: { invoice: Invoice; showRequirement?: boolean; children?: ReactNode }) {
  return (
    <li className="action-card" style={{ listStyle: "none", gap: 4 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <strong style={{ overflowWrap: "anywhere" }}>{i.invoice_number}</strong>
        <span className="badge">{i.payment_status_label}</span>
        {i.overdue && <span className="badge status error">Overdue</span>}
      </div>
      {showRequirement && (
        <p style={{ margin: 0, overflowWrap: "anywhere" }}>
          <Link href={`/recruiter/requirements/${encodeURIComponent(i.requirement.id)}`} style={LINK_STYLE}>{i.requirement.title} ({i.requirement.code})</Link>
          {" · "}{i.company.name}
        </p>
      )}
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        Invoice date {formatCalendarDate(i.invoice_date)} · Payment due {formatCalendarDate(i.due_date)}
      </p>
      <p style={{ margin: 0 }}>
        Amount {inr(i.amount)} · Received {inr(i.received)} · Outstanding {inr(i.outstanding)}
      </p>
      {i.note && <p style={{ margin: 0, fontSize: 13, overflowWrap: "anywhere", whiteSpace: "pre-line" }}>Note: {i.note}</p>}
      {i.cancel_reason && <p style={{ margin: 0, fontSize: 13, overflowWrap: "anywhere", whiteSpace: "pre-line" }}>Cancelled: {i.cancel_reason}</p>}
      {i.payments.length > 0 && (
        <ul aria-label={`Payments for ${i.invoice_number}`} style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
          {i.payments.map((p) => (
            <li key={p.id} style={{ overflowWrap: "anywhere" }}>
              {inr(p.amount)} received {formatCalendarDate(p.received_on)}{p.reference ? ` · ${p.reference}` : ""} · by {p.created_by.full_name}
            </li>
          ))}
        </ul>
      )}
      {children}
    </li>
  );
}
