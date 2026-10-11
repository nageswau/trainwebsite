"use client";
import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";

import { DetailList } from "@/components/BdmOrganizationProfileDetails";
import { sendRequest } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { type CompanyRevenue, companyRevenueUrl, feeSourceText, inr, isCompanyRevenue, RECEIVABLES_PATH } from "@/lib/recruiterRevenue";

// rec-031 (spec §4): the company's revenue -- totals over the requirements the caller can see, and one row per requirement linking to its
// Revenue section, where invoices and payments are recorded. Read only here; loading, empty and error-with-retry states.
export default function RecruiterCompanyRevenue({ companyId }: { companyId: string }) {
  const [data, setData] = useState<CompanyRevenue | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const titleId = `company-revenue-${companyId}-title`;

  async function load() {
    const outcome = await sendRequest(companyRevenueUrl(companyId), { method: "GET" });
    if (outcome.ok && isCompanyRevenue(outcome.data)) {
      setData(outcome.data);
      return setState("ready");
    }
    setState("failed");
  }

  useEffect(() => {
    void load();
  }, [companyId]); // eslint-disable-line react-hooks/exhaustive-deps -- load once per company

  let body: ReactNode;
  if (state === "loading") {
    body = <p className="muted" aria-live="polite">Loading…</p>;
  } else if (state === "failed" || data === null) {
    body = (
      <div role="alert">
        <p className="form-error">Unable to load revenue.</p>
        <button type="button" className="btn secondary small" onClick={() => { setState("loading"); void load(); }}>Try again</button>
      </div>
    );
  } else if (data.requirements.length === 0) {
    body = <p className="muted">No job requirements for this company yet.</p>;
  } else {
    const t = data.totals;
    body = (
      <>
        <DetailList rows={[
          ["Candidates selected", String(t.selected)], ["Candidates joined", String(t.joined)], ["Expected revenue", inr(t.expected_revenue)],
          ["Total invoiced", inr(t.invoiced)], ["Payment received", inr(t.received)], ["Outstanding amount", inr(t.outstanding)],
        ]} />
        <ul aria-label="Revenue by requirement" style={{ padding: 0, margin: 0, display: "grid", gap: 8 }}>
          {data.requirements.map((r) => (
            <li key={r.requirement.id} style={{ listStyle: "none", borderTop: "1px solid var(--line, #e5e7eb)", paddingTop: 8 }}>
              <p style={{ margin: 0, overflowWrap: "anywhere" }}>
                <Link href={`/recruiter/requirements/${encodeURIComponent(r.requirement.id)}#requirement-revenue`} style={LINK_STYLE}>{r.requirement.title} ({r.requirement.code})</Link>
                {" "}<span className="badge">{r.status_label}</span>
              </p>
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                Selected {r.selected} · Joined {r.joined} · {feeSourceText(r.fee)}
              </p>
              <p style={{ margin: 0, fontSize: 13 }}>
                Expected {r.expected_revenue === null ? "—" : inr(r.expected_revenue)} · Invoiced {inr(r.invoiced)} · Received {inr(r.received)} · Outstanding {inr(r.outstanding)}
              </p>
            </li>
          ))}
        </ul>
        <p style={{ margin: 0 }}>
          <Link href={`${RECEIVABLES_PATH}?company_id=${encodeURIComponent(companyId)}`} style={LINK_STYLE}>Receivables for this company</Link>
        </p>
      </>
    );
  }

  return (
    <section id="company-revenue" className="action-card wide" aria-labelledby={titleId}>
      <h3 id={titleId}>Revenue</h3>
      {body}
    </section>
  );
}
