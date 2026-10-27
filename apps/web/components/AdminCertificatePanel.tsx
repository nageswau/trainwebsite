"use client";

import { FormEvent, useEffect, useState } from "react";
import type { CertificateRules } from "@/lib/certificates";

const RULES = "/api/v1/workflows/it/certificates/rules";

function detailMessage(detail: unknown, fallback: string) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return fallback;
}

// ADM-006 gave the admin a form to issue certificates. nehn-031 (DEC-ROLE-003, DEC-SCOPE-297) moved issuance to the Coordinator, so the
// admin's Certificates page now sets the eligibility thresholds instead (`certificates.configure`); the directory below it is unchanged.
export default function AdminCertificatePanel() {
  const [rules, setRules] = useState<CertificateRules | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetch(RULES)
      .then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(detailMessage(data.detail, "The certificate rules could not be loaded."));
        setRules(data);
      })
      .catch((error: Error) => {
        setFailed(true);
        setMessage(error.message || "The certificate rules could not be loaded.");
      });
  }, []);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setMessage("");
    setFailed(false);
    const body = { min_progress_percent: Number(form.get("min_progress_percent")), min_attendance_percent: Number(form.get("min_attendance_percent")) };
    const response = await fetch(RULES, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).catch(() => null);
    const data = await response?.json().catch(() => ({}));
    setBusy(false);
    if (!response?.ok) {
      setFailed(true);
      setMessage(detailMessage(data?.detail, "The certificate rules could not be saved."));
      return;
    }
    setRules(data);
    setMessage("Certificate rules saved. They apply to the next eligibility check.");
  }

  return (
    <div className="action-card">
      <h3>Certificate rules</h3>
      <p className="muted">Certificates are issued by the Coordinator. A learner is eligible when they meet these thresholds, have every published assignment graded, have passed every assessment and owe no fee.</p>
      {!rules && !failed && <p className="muted">Loading the certificate rules…</p>}
      {rules && (
        <form className="form" onSubmit={save} key={`${rules.min_progress_percent}-${rules.min_attendance_percent}`}>
          <div className="field">
            <label htmlFor="cert-min-progress">Minimum progress (%)</label>
            <input id="cert-min-progress" name="min_progress_percent" type="number" min={0} max={100} step={1} required defaultValue={rules.min_progress_percent} />
          </div>
          <div className="field">
            <label htmlFor="cert-min-attendance">Minimum attendance (%)</label>
            <input id="cert-min-attendance" name="min_attendance_percent" type="number" min={0} max={100} step={1} required defaultValue={rules.min_attendance_percent} />
          </div>
          <button className="btn small" disabled={busy}>{busy ? "Saving…" : "Save rules"}</button>
        </form>
      )}
      {message && <div className={failed ? "form-error" : "form-message"} role={failed ? "alert" : "status"} aria-live="polite">{message}</div>}
    </div>
  );
}
