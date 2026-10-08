"use client";
import Link from "next/link";
import { useEffect, useState } from "react";

import { isPage, type Page } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { DEADLINE_LABEL, REQUIREMENTS_PATH, REQUIREMENTS_URL, type RequirementRow } from "@/lib/recruiterRequirements";

// rec-007: a company's requirements on its page, newest first, with the "+ Add Job Requirement" quick action (EVID-018 §1) for the
// people who can add one. The full, filterable list is /recruiter/requirements.
const LIMIT = 20;

export default function RecruiterCompanyRequirements({ companyId, canAdd }: { companyId: string; canAdd: boolean }) {
  const [data, setData] = useState<Page<RequirementRow> | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let live = true;
    setFailed(false);
    fetch(`${REQUIREMENTS_URL}?${new URLSearchParams({ company_id: companyId, limit: String(LIMIT) })}`)
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (!response.ok || !isPage<RequirementRow>(body)) throw new Error("not a page");
        if (live) setData(body);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [companyId, version]);

  const headingId = `company-${companyId}-requirements`;
  return (
    <section className="action-card wide" aria-labelledby={headingId}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id={headingId}>Job requirements</h3>
        {canAdd && (
          <Link className="btn small" href={`${REQUIREMENTS_PATH}/new?company_id=${encodeURIComponent(companyId)}`}>
            Add job requirement
          </Link>
        )}
      </div>
      {failed ? (
        <>
          <p className="form-error" role="alert">
            Unable to load this company&apos;s requirements.
          </p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((v) => v + 1)}>
            Retry
          </button>
        </>
      ) : data === null ? (
        <p className="muted" role="status">
          Loading requirements…
        </p>
      ) : data.total === 0 ? (
        <p className="empty" role="status">
          No job requirements for this company yet.
        </p>
      ) : (
        <>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {data.items.map((r) => (
              <li key={r.id}>
                <Link href={`${REQUIREMENTS_PATH}/${r.id}`} style={LINK_STYLE}>
                  {r.code} — {r.title}
                </Link>{" "}
                <span className="badge">{r.status_label}</span>
                {r.deadline_state && <span className="muted"> · {DEADLINE_LABEL[r.deadline_state]}</span>}
              </li>
            ))}
          </ul>
          {data.total > data.items.length && (
            <p style={{ marginBottom: 0 }}>
              <Link href={`${REQUIREMENTS_PATH}?q=${encodeURIComponent(data.items[0].company.name)}`} style={LINK_STYLE}>
                See all {data.total} requirements
              </Link>
            </p>
          )}
        </>
      )}
    </section>
  );
}
