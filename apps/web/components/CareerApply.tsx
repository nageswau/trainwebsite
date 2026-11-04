"use client";

import Link from "next/link";
import { FormEvent, useId, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { CONSENT_TEXT, CONSENT_VERSION } from "@/lib/candidatePortal";
import { readUtm } from "@/lib/utm";

// hrc-023 (DEC-SCOPE-387): the public job application. The server creates or matches the applicant's candidate record (W3) with the
// visit's campaign (W1) and the consent shown here (W4); its answer is the same for a new and a known person, so this form never says
// which. `website` is a honeypot (W6): hidden from people and assistive technology, so only a bot fills it.
export default function CareerApply({ jobId, jobTitle }: { jobId: string; jobTitle: string }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState<{ code: string; email: string } | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setStatus("Uploading resume…");
    const upload = new FormData();
    upload.append("file", form.get("resume") as File);
    const uploaded = await fetch("/api/v1/public/career-upload", { method: "POST", body: upload }).catch(() => null);
    if (!uploaded?.ok) {
      setBusy(false);
      setStatus("");
      return setError("Resume upload failed. Use PDF, DOC or DOCX up to 5 MB.");
    }
    const { url } = await uploaded.json();
    setStatus("Submitting application…");
    const email = String(form.get("email") || "").trim();
    const outcome = await sendJson(`/api/v1/public/jobs/${encodeURIComponent(jobId)}/apply`, "POST", {
      full_name: form.get("full_name"), email, phone: form.get("phone") || null, resume_url: url, cover_note: form.get("cover_note") || null,
      consent_version: CONSENT_VERSION, utm: readUtm(), website: form.get("website") || undefined,
    });
    setBusy(false);
    setStatus("");
    if (!outcome.ok) return setError((outcome.status ?? 0) >= 500 ? "We couldn't submit your application. Please try again." : outcome.message);
    setDone({ code: String(outcome.data.tracking_code ?? ""), email });
  }

  if (!open) {
    return <div style={{ marginTop: 14 }}><button type="button" className="btn small" onClick={() => setOpen(true)}>Apply online</button></div>;
  }
  if (done) {
    return (
      <div className="form card soft" style={{ marginTop: 14 }}>
        <div className="form-message" role="status">
          Application submitted for {jobTitle}. Save your tracking code: <strong>{done.code}</strong>
        </div>
        <p className="muted" style={{ margin: 0 }}>
          Keep your profile current for EduSphere recruiters:{" "}
          <Link href={`/it/careers/register?email=${encodeURIComponent(done.email)}`} style={{ color: "var(--blue)", fontWeight: 800 }}>create a candidate account</Link>{" "}
          with the same email.
        </p>
      </div>
    );
  }
  return (
    <div style={{ marginTop: 14 }}>
      <form className="form card soft" onSubmit={submit} aria-labelledby={`${id}-title`}>
        <strong id={`${id}-title`}>Apply for {jobTitle}</strong>
        <div className="form-grid">
          <div className="field"><label htmlFor={`${id}-name`}>Full name *</label><input id={`${id}-name`} name="full_name" autoComplete="name" required maxLength={160} /></div>
          <div className="field"><label htmlFor={`${id}-email`}>Email *</label><input id={`${id}-email`} name="email" type="email" autoComplete="email" required maxLength={255} /></div>
        </div>
        <div className="field"><label htmlFor={`${id}-phone`}>Phone</label><input id={`${id}-phone`} name="phone" type="tel" autoComplete="tel" maxLength={40} /></div>
        <div className="field"><label htmlFor={`${id}-resume`}>Resume *</label><input id={`${id}-resume`} name="resume" type="file" accept=".pdf,.doc,.docx" required /></div>
        <div className="field"><label htmlFor={`${id}-note`}>Cover note</label><textarea id={`${id}-note`} name="cover_note" maxLength={5000} /></div>
        <div aria-hidden="true" style={{ position: "absolute", left: "-10000px", width: 1, height: 1, overflow: "hidden" }}>
          <label htmlFor={`${id}-website`}>Website</label><input id={`${id}-website`} name="website" tabIndex={-1} autoComplete="off" />
        </div>
        <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
          <input type="checkbox" name="consent" required style={{ marginTop: 4 }} />
          <span className="muted" style={{ fontSize: 13 }}>{CONSENT_TEXT}</span>
        </label>
        {error && <div className="form-error" role="alert">{error}</div>}
        {status && <div className="form-message" role="status">{status}</div>}
        <div className="actions">
          <button type="submit" className="btn small" disabled={busy}>{busy ? "Submitting…" : "Submit application"}</button>
          <button type="button" className="btn ghost small" onClick={() => setOpen(false)} disabled={busy}>Cancel</button>
        </div>
      </form>
    </div>
  );
}
