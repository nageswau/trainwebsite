"use client";

import { useEffect, useState } from "react";

type JobRow = { id: string; company: string; title: string; status: string };
type ShortlistRow = { id: string; student: string; email: string; status: string; resume_url: string | null };

// ADM-008: "HR Team manages hiring requirements and shortlists." No way to view a
// specific requirement's shortlist existed at all -- only a flat, job-agnostic candidate
// pool and a flat list of requirements, with no bridge between the two. Real picker +
// drill-down. ADM-008-AC02: a requirement with no matching candidates shows a clear
// empty state, never an error -- the backend already returns a clean empty list for
// that case (`GET /workflows/it/jobs/{id}/shortlist`), this just renders it honestly.
export default function HrShortlistPanel() {
  const [jobs, setJobs] = useState<JobRow[] | null>(null);
  const [jobId, setJobId] = useState("");
  const [shortlist, setShortlist] = useState<ShortlistRow[] | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("/api/v1/workflows/it/jobs")
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setJobs(data))
      .catch(() => setJobs([]));
  }, []);

  async function selectJob(id: string) {
    setJobId(id);
    setShortlist(null);
    if (!id) return;
    setLoading(true);
    const response = await fetch(`/api/v1/workflows/it/jobs/${id}/shortlist`);
    const data = await response.json().catch(() => []);
    setLoading(false);
    if (response.ok) setShortlist(data);
  }

  return (
    <div className="action-card">
      <h3>Requirement shortlist</h3>
      <div className="field">
        <label htmlFor="hr-shortlist-job">Hiring requirement</label>
        <select id="hr-shortlist-job" value={jobId} onChange={(event) => void selectJob(event.target.value)} disabled={!jobs}>
          <option value="">{jobs === null ? "Loading requirements…" : "Select a requirement"}</option>
          {(jobs || []).map((job) => (
            <option key={job.id} value={job.id}>{job.title} · {job.company} · {job.status}</option>
          ))}
        </select>
      </div>
      {loading && <p className="muted">Loading shortlist…</p>}
      {shortlist !== null && (
        shortlist.length === 0 ? (
          <p className="muted" role="status">No candidates have applied to this requirement yet.</p>
        ) : (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Candidate</th>
                  <th scope="col">Status</th>
                  <th scope="col">Resume</th>
                </tr>
              </thead>
              <tbody>
                {shortlist.map((row) => (
                  <tr key={row.id}>
                    <th scope="row">{row.student}<br /><span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>{row.email}</span></th>
                    <td>{row.status}</td>
                    <td>{row.resume_url ? <a href={row.resume_url} target="_blank" rel="noreferrer">View</a> : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  );
}
