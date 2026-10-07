"use client";
import { type ReactNode, useState } from "react";

import { sendRequest } from "@/lib/apiErrors";
import { type AgentPerformance, agentPerformanceUrl, isAgentPerformance } from "@/lib/bdmAgentPerformance";

const UNABLE = "Unable to load the agent performance.";
const NOT_TRACKED = <span className="badge">Not tracked yet</span>;
const number = (n: number) => n.toLocaleString("en-IN");
const pct = (count: number, total: number) => (total > 0 ? Math.min(100, Math.round((count / total) * 100)) : 0);
// B8: the agency's status said in words (never colour alone); an active or pending agency needs no flag.
const STATUS_FLAG: Record<string, string> = {
  suspended: "Suspended — this agency's members can't sign in, so these figures are not changing.",
  rejected: "Not approved — this agency was rejected by Overseas Admin.",
};

// bdm-022 (spec §4): Agent → Students → Applications → Offers → Visa → Enrolled → Revenue for the linked agency, as the agency's own
// dashboard counts them. bdm-021's funnel markup: the count is the text, the bar is decoration sized against Students. Applications
// drills down by stage (aggregates only). An untracked step says so -- never a fabricated 0.
export default function BdmOrganizationAgentPerformance({ orgId, initial }: { orgId: string; initial: AgentPerformance | null }) {
  const [data, setData] = useState<AgentPerformance | null>(initial);
  const [loading, setLoading] = useState(false);
  const [showStages, setShowStages] = useState(false);
  const stagesId = `org-${orgId}-applications-by-stage`;

  async function reload() {
    setLoading(true);
    const outcome = await sendRequest(agentPerformanceUrl(orgId), { method: "GET" });
    setLoading(false);
    if (outcome.ok && isAgentPerformance(outcome.data)) setData(outcome.data);
  }

  let body: ReactNode;
  if (data === null) {
    body = (
      <div role="alert">
        <p className="form-error">{UNABLE}</p>
        <button type="button" className="btn secondary small" onClick={() => void reload()} disabled={loading}>{loading ? "Loading…" : "Try again"}</button>
      </div>
    );
  } else if (!data.linked || !data.agency) {
    body = <p className="muted">Not onboarded yet. Figures appear once Overseas Admin links the agent organization.</p>;
  } else {
    const students = data.steps.find((s) => s.key === "students")?.count ?? 0;
    const flag = STATUS_FLAG[data.agency.status];
    body = (
      <>
        <p>{data.agency.name} ({data.agency.prefix}) · live figures from the agency&apos;s own records.</p>
        {flag && <p><strong>{flag}</strong></p>}
        <ol className="pipeline-funnel" aria-label="Agent performance chain">
          {data.steps.map((s) => (
            <li key={s.key} className="pipeline-stage">
              <span className="pipeline-label">{s.label}</span>
              {s.count === null ? NOT_TRACKED : <span className="pipeline-count">{number(s.count)}</span>}
              {s.count !== null && (
                <span className="pipeline-track" aria-hidden="true"><span className="pipeline-fill" style={{ width: `${pct(s.count, students)}%` }} /></span>
              )}
              <span className="kpi-note muted" style={{ gridColumn: "1 / -1", marginTop: 0 }}>
                {s.definition}
                {s.key === "visa" && data.visa_applications !== null && ` ${number(s.count ?? 0)} approved of ${number(data.visa_applications)} visa applications.`}
              </span>
              {s.key === "applications" && (
                <div style={{ gridColumn: "1 / -1" }}>
                  <button type="button" className="btn secondary small" aria-expanded={showStages} aria-controls={stagesId} onClick={() => setShowStages((v) => !v)}>
                    {showStages ? "Hide applications by stage" : "Show applications by stage"}
                  </button>
                  <div id={stagesId} hidden={!showStages}>
                    {showStages && (
                      <div className="table-scroll">
                        <table className="table">
                          <caption className="visually-hidden">Applications by stage</caption>
                          <thead>
                            <tr><th scope="col">Stage</th><th scope="col">Applications</th></tr>
                          </thead>
                          <tbody>
                            {data.applications_by_stage.map((r) => (
                              <tr key={r.key}><th scope="row">{r.label}</th><td>{number(r.count)}</td></tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </li>
          ))}
        </ol>
      </>
    );
  }

  return (
    <section className="action-card wide" aria-label="Agent performance">
      <h3>Agent performance</h3>
      {body}
    </section>
  );
}
