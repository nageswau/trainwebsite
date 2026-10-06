"use client";
import { useState } from "react";

import { formatInr } from "@/lib/bdmAppointments";
import { type Business, isBusiness, orgBusinessUrl } from "@/lib/bdmBusiness";

const NOT_TRACKED = <span className="badge">Not tracked yet</span>;
const pct = (count: number, total: number) => (total > 0 ? Math.min(100, Math.round((count / total) * 100)) : 0);

// bdm-021 (spec §5): a College organization's student funnel and revenue, computed live by the server. ENH-017's funnel markup: the
// count is the text and the bar is decoration sized against Leads. Untracked stages and lines say so -- never a fabricated 0 (AC2).
// `null` = the server page could not read the figures.
export default function BdmOrganizationBusiness({ organizationId, initial }: { organizationId: string; initial: Business | null }) {
  const [data, setData] = useState(initial);
  const [loading, setLoading] = useState(false);
  const headingId = `org-${organizationId}-business`;
  const revenueId = `org-${organizationId}-revenue`;

  async function load() {
    setLoading(true);
    try {
      const response = await fetch(orgBusinessUrl(organizationId));
      const body = response.ok ? await response.json() : null;
      if (isBusiness(body)) setData(body);
    } catch {
      // the alert stays; Try again is offered again
    } finally {
      setLoading(false);
    }
  }

  if (!data) {
    return (
      <section className="action-card wide" aria-labelledby={headingId}>
        <h3 id={headingId}>Business</h3>
        <div role="alert">
          <p className="form-error">Business figures couldn&apos;t be loaded.</p>
          <button type="button" className="btn secondary small" onClick={() => void load()} disabled={loading}>{loading ? "Loading…" : "Try again"}</button>
        </div>
      </section>
    );
  }
  const leads = data.funnel.find((s) => s.key === "leads")?.count ?? 0;
  return (
    <section className="action-card wide" aria-labelledby={headingId}>
      <h3 id={headingId}>Business</h3>
      <p className="muted">Live figures for this organization&apos;s student leads, since the first lead.</p>
      {leads === 0 && <p>No leads yet. The funnel fills in as leads are added and linked to student accounts.</p>}
      <ol className="pipeline-funnel" aria-label="Student funnel">
        {data.funnel.map((s) => (
          <li key={s.key} className="pipeline-stage">
            <span className="pipeline-label">{s.label}</span>
            {s.count === null ? NOT_TRACKED : <span className="pipeline-count">{s.count.toLocaleString("en-IN")}</span>}
            {s.count !== null && (
              <span className="pipeline-track" aria-hidden="true"><span className="pipeline-fill" style={{ width: `${pct(s.count, leads)}%` }} /></span>
            )}
            <span className="kpi-note muted" style={{ gridColumn: "1 / -1", marginTop: 0 }}>{s.definition}</span>
          </li>
        ))}
      </ol>
      <section aria-labelledby={revenueId} className="kpi-group">
        <h4 id={revenueId}>Revenue (INR)</h4>
        {data.revenue === null ? (
          <p className="muted">Revenue is visible to the organization&apos;s assigned BDM and their manager.</p>
        ) : (
          <dl className="kpi-grid">
            {data.revenue.lines.map((l) => (
              <div className="kpi-tile" key={l.key}>
                <dt>{l.label}</dt>
                <dd>
                  {l.amount === null ? NOT_TRACKED : <strong>{formatInr(l.amount)}</strong>}
                  <span className="kpi-note muted">{l.definition}</span>
                </dd>
              </div>
            ))}
          </dl>
        )}
      </section>
    </section>
  );
}
