"use client";
import { type ReactNode, useState } from "react";

import { sendRequest } from "@/lib/apiErrors";
import { isSchoolActivity, type SchoolActivity, schoolActivityUrl } from "@/lib/bdmSchoolActivity";
import { plural } from "@/lib/plural";

const UNABLE = "Unable to load the school activity.";
const count = (n: number | null) => (n ?? 0).toLocaleString("en-IN");

// bdm-020 (spec §3): the linked School's student development, with the School module's own Completed / Pending (D2) per metric.
// Read-only and aggregates only. A metric the School module has no figure for says "Not tracked", never a 0 (A2).
export default function BdmOrganizationSchoolActivity({ orgId, initial }: { orgId: string; initial: SchoolActivity | null }) {
  const [data, setData] = useState<SchoolActivity | null>(initial);
  const [loading, setLoading] = useState(false);

  async function reload() {
    setLoading(true);
    const outcome = await sendRequest(schoolActivityUrl(orgId), { method: "GET" });
    setLoading(false);
    if (outcome.ok && isSchoolActivity(outcome.data)) setData(outcome.data);
  }

  let body: ReactNode;
  if (data === null) {
    body = (
      <div role="alert">
        <p className="form-error">{UNABLE}</p>
        <button type="button" className="btn secondary small" onClick={() => void reload()} disabled={loading}>{loading ? "Loading…" : "Try again"}</button>
      </div>
    );
  } else if (!data.linked || !data.school) {
    body = <p className="muted">Not onboarded yet. Counts appear once Overseas Admin links the School.</p>;
  } else {
    const { name, school_code } = data.school;
    body = (
      <>
        <p>{name}{school_code ? ` (School ID ${school_code})` : ""} · {plural(data.total_students ?? 0, "student")}</p>
        <div className="table-scroll">
          <table className="table">
            <caption className="visually-hidden">Student development</caption>
            <thead>
              <tr><th scope="col">Metric</th><th scope="col">Completed</th><th scope="col">Pending</th></tr>
            </thead>
            <tbody>
              {data.metrics.map((m) => (
                <tr key={m.key}>
                  <th scope="row">{m.label}</th>
                  {m.tracked ? (
                    <>
                      <td>{count(m.completed)}</td>
                      <td>{count(m.pending)}</td>
                    </>
                  ) : (
                    <td colSpan={2} className="muted">Not tracked</td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </>
    );
  }

  return (
    <section className="action-card wide bdm-school-activity" aria-label="School activity">
      <h3>School activity</h3>
      {body}
    </section>
  );
}
