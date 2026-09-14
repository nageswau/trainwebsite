"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type EnrollmentRow = { id: string; student: string; batch: string; progress_percent: number };
type Criteria = {
  eligible: boolean;
  progress_percent: number;
  attendance_percent: number;
  assignments_graded: number;
  assignments_total: number;
  assessments_passed: number;
  assessments_total: number;
  pending_fee: number;
};

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to issue certificate.";
}

// ADM-006: "Admin uploads/issues certificate" -- issuance (`POST
// /workflows/it/certificates/{enrollment_id}/issue`) already existed and already worked
// (own-batch RBAC for a Trainer, eligibility check, criteria snapshot), but no Admin-facing
// UI to use it existed at all -- only a Trainer-side form under "student-progress". This is
// that missing surface. ADM-006-AC02: issuing before completion criteria are met now
// requires a real written `override_reason`, not just a checkbox -- enforced server-side
// (422 without one), surfaced here as a required field that only appears once the fetched
// eligibility criteria say the enrollment isn't eligible yet.
export default function AdminCertificatePanel() {
  const router = useRouter();
  const [enrollments, setEnrollments] = useState<EnrollmentRow[]>([]);
  const [enrollmentId, setEnrollmentId] = useState("");
  const [criteria, setCriteria] = useState<Criteria | null>(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetch("/api/v1/admin/enrollments")
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setEnrollments(data))
      .catch(() => setEnrollments([]))
      .finally(() => setLoading(false));
  }, []);

  async function checkEligibility(id: string) {
    setEnrollmentId(id);
    setCriteria(null);
    setMessage("");
    if (!id) return;
    setChecking(true);
    const response = await fetch(`/api/v1/workflows/it/certificates/eligibility/${id}`);
    const data = await response.json().catch(() => ({}));
    setChecking(false);
    if (response.ok) setCriteria(data);
  }

  async function issue(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setFailed(false);
    const form = new FormData(event.currentTarget);
    const response = await fetch(`/api/v1/workflows/it/certificates/${enrollmentId}/issue`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ override: criteria && !criteria.eligible, override_reason: form.get("override_reason") || undefined }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setFailed(true);
      setMessage(detailMessage(data.detail));
      return;
    }
    setMessage(`Certificate ${data.certificate_no} issued.`);
    setEnrollmentId("");
    setCriteria(null);
    router.refresh();
  }

  return (
    <div className="action-card">
      <h3>Issue certificate</h3>
      <div className="field">
        <label htmlFor="admin-cert-enrollment">Enrolment</label>
        <select id="admin-cert-enrollment" value={enrollmentId} onChange={(event) => void checkEligibility(event.target.value)} disabled={loading}>
          <option value="">{loading ? "Loading enrolments…" : "Select enrolment"}</option>
          {enrollments.map((item) => (
            <option key={item.id} value={item.id}>{item.student} · {item.batch} · {item.progress_percent}%</option>
          ))}
        </select>
      </div>
      {checking && <p className="muted">Checking completion criteria…</p>}
      {criteria && (
        <form className="form" onSubmit={issue}>
          <p className={criteria.eligible ? "form-message" : "form-error"} role="status">
            {criteria.eligible
              ? "Completion criteria are met."
              : `Not yet eligible: progress ${criteria.progress_percent}%, attendance ${criteria.attendance_percent}%, assignments graded ${criteria.assignments_graded}/${criteria.assignments_total}, assessments passed ${criteria.assessments_passed}/${criteria.assessments_total}, pending fee ${criteria.pending_fee}.`}
          </p>
          {!criteria.eligible && (
            <div className="field">
              <label htmlFor="admin-cert-override-reason">Override reason (required to issue before criteria are met)</label>
              <textarea id="admin-cert-override-reason" name="override_reason" required />
            </div>
          )}
          <button className="btn small" disabled={busy}>{busy ? "Issuing…" : "Issue certificate"}</button>
        </form>
      )}
      {message && <div className={failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8 }}>{message}</div>}
    </div>
  );
}
