"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";

import { AT_RISK_URL, formatRiskDate, riskReasonLabels, type RiskFlag } from "@/lib/itAtRisk";

/** itc-023 (DEC-SCOPE-352): the students the daily check flagged, within the reader's own scope (the API scopes it). Dashboards and the
 *  IT Admin's At Risk page. */
export default function ItAtRiskList({ emptyText = "No students are at risk right now.", batchId }: { emptyText?: string; batchId?: string | null }) {
  const [flags, setFlags] = useState<RiskFlag[] | null>(null);
  const [failed, setFailed] = useState(false);
  const id = useId();
  // itc-024 (DEC-SCOPE-355 W5): the trainer dashboard narrowed to one batch shows that batch's students only (its tile agrees).
  const shown = flags && batchId ? flags.filter((flag) => flag.batch.id === batchId) : flags;

  useEffect(() => {
    let cancelled = false;
    fetch(AT_RISK_URL)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((data: RiskFlag[]) => !cancelled && setFlags(data))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="card" aria-labelledby={`${id}-title`} style={{ marginBottom: 16 }}>
      <h3 id={`${id}-title`} style={{ fontSize: 18 }}>Students at risk</h3>
      {failed ? (
        <p className="form-error" role="alert" style={{ margin: 0 }}>Unable to load the at-risk students. Refresh the page to try again.</p>
      ) : shown === null ? (
        <p className="muted" role="status" style={{ margin: 0 }}>Loading at-risk students…</p>
      ) : shown.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>{emptyText}</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th scope="col">Student</th><th scope="col">Programme / batch</th><th scope="col">Why</th><th scope="col">Since</th></tr>
            </thead>
            <tbody>
              {shown.map((flag) => (
                <tr key={flag.id}>
                  <td>
                    {flag.profile_url ? <Link href={flag.profile_url}>{flag.student.full_name}</Link> : flag.student.full_name}
                    {flag.student.student_code && <div className="muted" style={{ fontSize: 13 }}>{flag.student.student_code}</div>}
                  </td>
                  <td>{flag.program}<div className="muted" style={{ fontSize: 13 }}>{flag.batch.name}</div></td>
                  <td>{riskReasonLabels(flag).map((label) => <span key={label} className="status error" style={{ marginRight: 6, display: "inline-block", marginBottom: 4 }}>{label}</span>)}</td>
                  <td>{formatRiskDate(flag.raised_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
