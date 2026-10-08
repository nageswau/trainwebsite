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
        <ul aria-label="Applications" style={{ padding: 0, margin: "8px 0 0", display: "grid", gap: 8 }}>
          {items.map((a) => (
            <li key={a.id} className="action-card" style={{ listStyle: "none", gap: 4 }}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
                <strong style={{ overflowWrap: "anywhere" }}>{a.company.name}</strong>
                <span className="badge">{a.status_label}</span>
              </div>
              <div style={{ overflowWrap: "anywhere" }}>
                {a.in_scope ? <Link href={`${REQUIREMENTS_PATH}/${a.requirement.id}`} style={LINK_STYLE}>{a.requirement.title}</Link> : a.requirement.title}
              </div>
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                {a.requirement.code} · requirement {a.requirement.status_label} · since <LocalTime value={a.stage_changed_at} time />
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
