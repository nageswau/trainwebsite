"use client";
import Link from "next/link";
import { useEffect, useId, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { type CandidateApplication, candidateApplicationsUrl, isCandidateApplications } from "@/lib/recruiterApplications";
import { REQUIREMENTS_PATH } from "@/lib/recruiterRequirements";

/** rec-017 (§12): one candidate's status on each requirement -- a candidate can be at Interview for one company and Rejected for another.
 *  A requirement links only when the viewer can open it (`in_scope`). */
export default function RecruiterCandidateApplications({ candidateId }: { candidateId: string }) {
  const [items, setItems] = useState<CandidateApplication[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const headingId = `${useId()}-applications`;

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(candidateApplicationsUrl(candidateId), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => (isCandidateApplications(body) ? setItems(body.items) : setFailed(true)))
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [candidateId, version]);

  return (
    <section className="action-card wide" aria-labelledby={headingId}>
      <h3 id={headingId} style={{ margin: 0 }}>Applications</h3>
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the applications.</p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((n) => n + 1)}>Retry</button>
        </div>
      ) : items === null ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading applications…</p>
      ) : items.length === 0 ? (
        <p className="muted" style={{ fontSize: 13, margin: 0 }}>Not on any job requirement yet.</p>
      ) : (
        <div className="table-wrap" role="region" aria-label="Applications" tabIndex={0}>
          <table className="table">
            <thead>
              <tr><th scope="col">Requirement</th><th scope="col">Company</th><th scope="col">Status</th><th scope="col">Since</th></tr>
            </thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.id}>
                  <td>
                    {a.in_scope ? (
                      <Link href={`${REQUIREMENTS_PATH}/${a.requirement.id}`} style={{ ...LINK_STYLE, overflowWrap: "anywhere" }}>{a.requirement.title}</Link>
                    ) : (
                      <span style={{ overflowWrap: "anywhere" }}>{a.requirement.title}</span>
                    )}
                    <div className="muted" style={{ fontSize: 12 }}>{a.requirement.code} · {a.requirement.status_label}</div>
                  </td>
                  <td style={{ overflowWrap: "anywhere" }}>{a.company.name}</td>
                  <td><span className="badge">{a.status_label}</span></td>
                  <td><LocalTime value={a.stage_changed_at} time /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
