"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type CurrentAgreement = {
  id: string;
  version: string;
  title: string;
  body: string;
  accepted: boolean;
  pending_enrollments: number;
};

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to record acceptance.";
}

// STU-009: "Enrolment cannot complete without acceptance." A newly booked slot is locked
// (holds its capacity) but the enrolment itself stays "pending_consent" -- not visible on
// the dashboard, live classes, or assignments -- until the student reviews and accepts
// this agreement. Renders nothing once there is nothing pending, so it never gets in the
// way of an already-active enrolment.
export default function AgreementConsentPanel() {
  const router = useRouter();
  const [agreement, setAgreement] = useState<CurrentAgreement | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    function load() {
      fetch("/api/v1/workflows/it/student/agreements/current")
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (cancelled) return;
          setAgreement(data);
          setLoaded(true);
        })
        .catch(() => {
          if (!cancelled) setLoaded(true);
        });
    }
    load();
    // BatchSlotPicker (STU-001) is a sibling client component -- it dispatches this after
    // a successful booking so a newly created pending_consent enrolment shows up here
    // immediately, without needing a full page reload.
    window.addEventListener("edusphere:enrollment-created", load);
    return () => {
      cancelled = true;
      window.removeEventListener("edusphere:enrollment-created", load);
    };
  }, []);

  if (!loaded || !agreement || agreement.pending_enrollments === 0) return null;

  async function accept() {
    if (!agreement) return;
    setBusy(true);
    setError(null);
    const response = await fetch(`/api/v1/workflows/it/student/agreements/${agreement.id}/accept`, { method: "POST" });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setError(detailMessage(data.detail));
      return;
    }
    router.refresh();
    setAgreement({ ...agreement, accepted: true, pending_enrollments: 0 });
  }

  return (
    <div className="action-card">
      <h3>Review and accept your enrolment agreement</h3>
      <p className="muted" style={{ fontSize: 13 }}>Version {agreement.version} · Required to activate your enrolment</p>
      <p style={{ marginTop: 12 }}>{agreement.body}</p>
      <button className="btn small" disabled={busy} onClick={accept} style={{ marginTop: 12 }}>
        {busy ? "Accepting…" : "I have read and accept this agreement"}
      </button>
      {error && (
        <div className="form-error" role="status" aria-live="polite" style={{ marginTop: 8 }}>
          {error}
        </div>
      )}
    </div>
  );
}
