import type { ReactNode } from "react";

import LocalTime from "@/components/LocalTime";
import StudentDocumentDownload from "@/components/StudentDocumentDownload";
import { money } from "@/lib/applicationOffers";
import { formatCalendarDate } from "@/lib/formatDate";
import type { StudentDeposit, StudentFinance, StudentPayment } from "@/lib/overseasStudent360";

const paymentFile = (id: string, kind: "invoice" | "receipt") => `/api/v1/payments/${encodeURIComponent(id)}/${kind}`;

// QA-02: the badge colour follows the meaning (the label always says it in words); anything paid stays the default green.
const TONE: Record<string, string> = { pending: "pending", overdue: "pending", failed: "error", refunded: "closed", cancelled: "closed", not_required: "closed" };

function Empty({ children }: { children: ReactNode }) {
  return <p className="muted" style={{ margin: 0 }}>{children}</p>;
}

function Row({ title, status, label, children }: { title: ReactNode; status: string; label: string; children: ReactNode }) {
  return (
    <li>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        {title}
        <span className={TONE[status] ? `status ${TONE[status]}` : "status"}>{label}</span>
      </div>
      {children}
    </li>
  );
}

function Payment({ p }: { p: StudentPayment }) {
  return (
    <Row title={<strong>{p.description}</strong>} status={p.status} label={p.status_label}>
      <p>{money(p.currency, p.amount)}</p>
      <p className="muted">
        Billed <LocalTime value={p.created_at} />
        {p.due_date && <> · Due {formatCalendarDate(p.due_date)}</>}
        {p.invoice_no && <> · Invoice {p.invoice_no}</>}
        {p.receipt_no && <> · Receipt {p.receipt_no}</>}
      </p>
      {p.can_download && (p.invoice_no || p.receipt_no) && (
        <p style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {p.invoice_no && <StudentDocumentDownload id={p.id} name={`invoice ${p.invoice_no}`} url={paymentFile(p.id, "invoice")} text="Invoice" />}
          {p.receipt_no && <StudentDocumentDownload id={p.id} name={`receipt ${p.receipt_no}`} url={paymentFile(p.id, "receipt")} text="Receipt" />}
        </p>
      )}
    </Row>
  );
}

function Deposit({ d }: { d: StudentDeposit }) {
  return (
    <Row title={<strong>{d.university}</strong>} status={d.status} label={d.status_label}>
      <p className="muted">
        {[d.application_code, d.source === "agency" ? "Paid by the agency" : "Recorded by the counselor", d.mine && "Yours"].filter(Boolean).join(" · ")}
      </p>
      {d.required ? (
        <p>
          {money(d.currency, d.amount)}
          {d.due_date && <> · Due {formatCalendarDate(d.due_date)}</>}
          {d.paid_on && <> · Paid {formatCalendarDate(d.paid_on)}</>}
        </p>
      ) : (
        <p>No deposit is required.</p>
      )}
      {d.refund && (
        <p>
          Refunded {money(d.currency, d.refund.amount)} on {formatCalendarDate(d.refund.refunded_on)} — {d.refund.reason}
        </p>
      )}
      {d.receipt && (
        <p className="muted">
          Receipt: {d.receipt.name} {d.receipt.can_download && <StudentDocumentDownload id={d.receipt.id} name={d.receipt.name} />}
        </p>
      )}
    </Row>
  );
}

/** ccrm-039 (DEC-SCOPE-272): the student 360's finance tab -- read-only (F1). Fees and payments are recorded by the Overseas Admin,
 *  a deposit on its application. A download is offered only where its own route allows the reader (F5). */
export default function OverseasStudentFinance({ finance }: { finance: StudentFinance }) {
  return (
    <>
      <p className="muted">
        Read-only. Fees are recorded by the Overseas Admin; a university deposit is recorded on its application.
      </p>
      <section className="card" aria-labelledby="fin-payments">
        <h2 id="fin-payments">Fees and payments</h2>
        {finance.payments.length === 0 ? (
          <Empty>No fees or payments recorded for this student.</Empty>
        ) : (
          <ul className="s360-list">{finance.payments.map((p) => <Payment key={p.id} p={p} />)}</ul>
        )}
      </section>
      <section className="card" aria-labelledby="fin-deposits">
        <h2 id="fin-deposits">University deposits</h2>
        {finance.deposits.length === 0 ? (
          <Empty>No university deposit recorded on any application.</Empty>
        ) : (
          <ul className="s360-list">{finance.deposits.map((d) => <Deposit key={d.application_id} d={d} />)}</ul>
        )}
      </section>
      <section className="card" aria-labelledby="fin-refunds">
        <h2 id="fin-refunds">Refunds</h2>
        {finance.refunds.length === 0 ? (
          <Empty>No refunds.</Empty>
        ) : (
          <ul className="s360-list">
            {finance.refunds.map((r, i) => (
              <li key={`${r.kind}-${i}`}>
                <strong>{r.description}</strong> <span className="muted">· {money(r.currency, r.amount)}</span>
                <p className="muted">
                  Refunded {formatCalendarDate(r.refunded_on)}
                  {r.application_code && <> · {r.application_code}</>}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
