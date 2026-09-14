"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { Scholarship } from "@/lib/types";

type ApplicationRow = { scholarship_id: string; title: string; amount: string; status: string };

function detailMessage(status: number, detail: unknown) {
  if (status === 409) return "You have already applied to this scholarship.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to submit the application.";
}

// OVS-006: the public /overseas/scholarships page only ever said "Sign in to apply" with
// no actual apply action anywhere -- the backend endpoint already existed and was already
// correctly RBAC'd (self-scoped, duplicate-blocked), but nothing in the UI ever called it.
export default function ScholarshipApplyPanel() {
  const router = useRouter();
  const [scholarships, setScholarships] = useState<Scholarship[] | null>(null);
  const [applications, setApplications] = useState<ApplicationRow[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);

  function loadApplications() {
    return fetch("/api/v1/portal/overseas/student/scholarships")
      .then((res) => (res.ok ? res.json() : { rows: [] }))
      .then((data) => setApplications(data.rows || []))
      .catch(() => setApplications([]));
  }

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/public/scholarships")
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => !cancelled && setScholarships(data))
      .catch(() => !cancelled && setScholarships([]));
    loadApplications();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function apply(scholarshipId: string) {
    setBusyId(scholarshipId);
    setMessage(null);
    const response = await fetch(`/api/v1/workflows/overseas/scholarships/${scholarshipId}/apply`, { method: "POST" });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ text: detailMessage(response.status, data.detail), failed: true });
      return;
    }
    setMessage({ text: "Application submitted.", failed: false });
    router.refresh();
    loadApplications();
  }

  if (scholarships === null || applications === null) {
    return (
      <div className="action-card">
        <h3>Apply to a Scholarship</h3>
        <p className="muted">Loading scholarships…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Apply to a Scholarship</h3>
      {scholarships.length === 0 ? (
        <p className="muted">No scholarships are currently open for application.</p>
      ) : (
        <div className="grid two">
          {scholarships.map((s) => {
            const application = applications.find((a) => a.scholarship_id === s.id);
            return (
              <div className="card" key={s.id} data-scholarship-id={s.id}>
                <h4>{s.title}</h4>
                <p className="muted" style={{ fontSize: 13 }}>{s.amount}</p>
                <p className="muted" style={{ fontSize: 13 }}>{s.eligibility}</p>
                {s.deadline && <p className="muted" style={{ fontSize: 13 }}><strong>Deadline:</strong> {new Date(s.deadline).toLocaleDateString("en-GB")}</p>}
                {application ? (
                  <span className="badge">{application.status}</span>
                ) : (
                  <button className="btn small" disabled={busyId === s.id} onClick={() => apply(s.id)}>
                    {busyId === s.id ? "Applying…" : "Apply"}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
      {message && (
        <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8 }}>
          {message.text}
        </div>
      )}
      <h4 style={{ marginTop: 24 }}>Your applications</h4>
      {applications.length === 0 ? (
        <p className="muted">You have not applied to any scholarship yet.</p>
      ) : (
        <ul className="list-clean">
          {applications.map((a) => (
            <li key={a.scholarship_id}>
              <strong>{a.title}</strong> — <span className="badge">{a.status}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
