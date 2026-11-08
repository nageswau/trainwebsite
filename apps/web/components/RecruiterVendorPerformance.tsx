import Link from "next/link";

import { formatCalendarDate, formatDateTimeIn, SCHOOL_TIME_ZONE } from "@/lib/formatDate";
import { inr } from "@/lib/recruiterRevenue";
import {
  hoursText, PERFORMANCE_LIMIT, rateText, VENDOR_PERFORMANCE_PATH, type VendorMetrics, type VendorPerformanceDetail, type VendorPerformancePage, vendorPerformancePath,
} from "@/lib/vendorCommercials";

const yes = (v: boolean) => (v ? "Yes" : "No");
const paymentsText = (m: VendorMetrics) => `We owe ${inr(m.payments.payable.outstanding)} · They owe ${inr(m.payments.receivable.outstanding)}`;

// pob-012 (DEC-SCOPE-433 W6/W9): one row per vendor in the caller's scope; each name opens the drill-down that its figures are counted from.
export function VendorPerformanceTable({ data, offset }: { data: VendorPerformancePage; offset: number }) {
  if (data.items.length === 0) return <p className="muted">No vendors yet.</p>;
  const prev = Math.max(0, offset - PERFORMANCE_LIMIT);
  const next = offset + PERFORMANCE_LIMIT;
  return (
    <>
      <div className="table-wrap" role="region" aria-labelledby="vendor-performance-title" tabIndex={0}>
        <table className="table stack">
          <caption className="visually-hidden" id="vendor-performance-title">Vendor performance</caption>
          <thead>
            <tr>
              <th scope="col">Vendor</th><th scope="col">Avg response</th><th scope="col">Submitted</th><th scope="col">Interview conversion</th>
              <th scope="col">Placements</th><th scope="col">Joining rate</th><th scope="col">Outstanding</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map(({ vendor, vendor_status_label, metrics: m }) => (
              <tr key={vendor.id}>
                <th scope="row" data-label="Vendor" style={{ overflowWrap: "anywhere" }}>
                  <Link className="kpi-link" href={vendorPerformancePath(vendor.id)}>{vendor.name}</Link>
                  {vendor_status_label && <span className="muted"> · {vendor_status_label}</span>}
                </th>
                <td data-label="Avg response">{hoursText(m.avg_response_hours)}</td>
                <td data-label="Submitted">{m.submitted}</td>
                <td data-label="Interview conversion">{rateText(m.interview_rate)} ({m.interviewed})</td>
                <td data-label="Placements">{m.placed}</td>
                <td data-label="Joining rate">{rateText(m.joining_rate)} ({m.joined})</td>
                <td data-label="Outstanding">{paymentsText(m)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.total > PERFORMANCE_LIMIT && (
        <nav className="actions" aria-label="Pages">
          {offset > 0 && <Link className="btn secondary small" href={`${VENDOR_PERFORMANCE_PATH}?offset=${prev}`}>Previous</Link>}
          <span className="muted">{offset + 1}–{Math.min(next, data.total)} of {data.total}</span>
          {next < data.total && <Link className="btn secondary small" href={`${VENDOR_PERFORMANCE_PATH}?offset=${next}`}>Next</Link>}
        </nav>
      )}
    </>
  );
}

// pob-012 W7: the figures and, below them, the exact rows each one is counted from (so every figure ties out to its drill-down).
export function VendorPerformanceDrillDown({ data }: { data: VendorPerformanceDetail }) {
  const m = data.metrics;
  const tile = (label: string, value: string) => (
    <div className="action-card" style={{ gap: 2 }}>
      <span className="muted" style={{ fontSize: 13 }}>{label}</span>
      <strong>{value}</strong>
    </div>
  );
  return (
    <>
      <section aria-label="Figures" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
        {tile("Avg response time", `${hoursText(m.avg_response_hours)} (${m.responded_requirements} of ${m.requirements} requirements)`)}
        {tile("Submitted", String(m.submitted))}
        {tile("Interview conversion", `${rateText(m.interview_rate)} (${m.interviewed})`)}
        {tile("Placements", String(m.placed))}
        {tile("Joining rate", `${rateText(m.joining_rate)} (${m.joined} joined)`)}
      </section>
      <section className="action-card wide" aria-labelledby="vp-payments">
        <h3 id="vp-payments">Payment history</h3>
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {(["payable", "receivable"] as const).map((k) => {
            const t = m.payments[k];
            return (
              <li key={k}>
                {k === "payable" ? "We owe the vendor" : "The vendor owes us"}: billed {inr(t.billed)} · paid {inr(t.paid)} · outstanding {inr(t.outstanding)}
                {t.last_paid_on ? ` · last payment ${formatCalendarDate(t.last_paid_on)}` : ""}
              </li>
            );
          })}
        </ul>
      </section>
      <section className="action-card wide" aria-labelledby="vp-requirements">
        <h3 id="vp-requirements">Requirements via this vendor ({data.requirements.length})</h3>
        {data.requirements.length === 0 ? <p className="muted">No requirements via this vendor yet.</p> : (
          <div className="table-wrap" role="region" aria-labelledby="vp-requirements" tabIndex={0}>
            <table className="table stack">
              <thead><tr><th scope="col">Requirement</th><th scope="col">Created</th><th scope="col">First shared</th><th scope="col">Response time</th></tr></thead>
              <tbody>
                {data.requirements.map((r) => (
                  <tr key={r.requirement.id}>
                    <th scope="row" data-label="Requirement" style={{ overflowWrap: "anywhere" }}>
                      <Link className="kpi-link" href={`/recruiter/requirements/${encodeURIComponent(r.requirement.id)}`}>{r.requirement.title} ({r.requirement.code})</Link>
                    </th>
                    <td data-label="Created">{formatDateTimeIn(r.created_at, SCHOOL_TIME_ZONE)}</td>
                    <td data-label="First shared">{r.first_submission_at ? formatDateTimeIn(r.first_submission_at, SCHOOL_TIME_ZONE) : "Not shared yet"}</td>
                    <td data-label="Response time">{hoursText(r.response_hours)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="action-card wide" aria-labelledby="vp-submissions">
        <h3 id="vp-submissions">Candidates shared with this vendor ({data.submissions.length})</h3>
        {data.submissions.length === 0 ? <p className="muted">No candidates shared with this vendor yet.</p> : (
          <div className="table-wrap" role="region" aria-labelledby="vp-submissions" tabIndex={0}>
            <table className="table stack">
              <thead>
                <tr><th scope="col">Candidate</th><th scope="col">Requirement</th><th scope="col">Shared</th><th scope="col">Interviewed</th><th scope="col">Placed</th><th scope="col">Joined</th></tr>
              </thead>
              <tbody>
                {data.submissions.map((s) => (
                  <tr key={s.application_id}>
                    <th scope="row" data-label="Candidate" style={{ overflowWrap: "anywhere" }}>{s.candidate.name} ({s.candidate.code})</th>
                    <td data-label="Requirement" style={{ overflowWrap: "anywhere" }}>{s.requirement.title} ({s.requirement.code})</td>
                    <td data-label="Shared">{formatDateTimeIn(s.submitted_at, SCHOOL_TIME_ZONE)}</td>
                    <td data-label="Interviewed">{yes(s.interviewed)}</td>
                    <td data-label="Placed">{yes(s.placed)}</td>
                    <td data-label="Joined">{yes(s.joined)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
