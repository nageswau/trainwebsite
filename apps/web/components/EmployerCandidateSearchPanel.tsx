"use client";

import { useEffect, useState } from "react";

type Candidate = { student_id: string; name: string; course: string | null; skills: string[]; availability: boolean };

// EMP-003: no endpoint or UI let an Employer search Student candidate profiles at all.
// `GET /employer/candidates` returns only a conservative allowlist -- name, course,
// skills, availability -- never raw contact info (EMP-003-AC02), so this panel has
// nothing to leak even by construction.
export default function EmployerCandidateSearchPanel() {
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);

  useEffect(() => {
    const params = query ? `?q=${encodeURIComponent(query)}` : "";
    fetch(`/api/v1/employer/candidates${params}`)
      .then((res) => (res.ok ? res.json() : []))
      .then(setCandidates)
      .catch(() => setCandidates([]));
  }, [query]);

  return (
    <div className="action-card">
      <h3>Search Candidates</h3>
      <div className="field">
        <label htmlFor="candidate-search">Search by name, course, or skill</label>
        <input id="candidate-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Python, Data Science, …" />
      </div>

      {candidates === null ? (
        <p className="muted">Loading candidates…</p>
      ) : candidates.length === 0 ? (
        <p className="muted">No matching candidates yet.</p>
      ) : (
        <div className="grid two" style={{ marginTop: 16 }}>
          {candidates.map((candidate) => (
            <div className="card" key={candidate.student_id}>
              <span className="badge">{candidate.availability ? "Available" : "Currently unavailable"}</span>
              <h4 style={{ marginTop: 10 }}>{candidate.name}</h4>
              {candidate.course && <p className="muted" style={{ fontSize: 13 }}>{candidate.course}</p>}
              {candidate.skills.length > 0 && <p className="muted" style={{ fontSize: 13 }}>{candidate.skills.join(", ")}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
