"use client";

import { FormEvent, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import {
  CONTACT_OPTIONS,
  EMAIL_URL,
  FIELDS,
  PROFILE_URL,
  changedFields,
  displayValue,
  toForm,
  type CandidateProfile,
} from "@/lib/candidatePortal";

const SERVER_ERROR = "We couldn't save your changes. Please try again.";

// hrc-022 (DEC-SCOPE-385 C10/C11): the candidate's own record. Only the allow-listed fields are inputs; the rest are shown read-only
// with "ask your recruiter". The mobile is never self-service (C8); the email changes only through a link to the new address (C9).
export default function CandidateProfileForm({ initial }: { initial: CandidateProfile }) {
  const [profile, setProfile] = useState(initial);
  const [form, setForm] = useState(() => toForm(initial.fields));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const editable = FIELDS.filter((f) => profile.editable.includes(f.key));
  const fixed = FIELDS.filter((f) => !profile.editable.includes(f.key));

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const body = changedFields(form, profile.fields, profile.editable);
    if (Object.keys(body).length === 0) return setMessage({ text: "Nothing to save -- no field has changed.", failed: false });
    setBusy(true);
    setMessage(null);
    const outcome = await sendJson(PROFILE_URL, "PATCH", body);
    setBusy(false);
    if (!outcome.ok) return setMessage({ text: (outcome.status ?? 0) >= 500 ? SERVER_ERROR : outcome.message, failed: true });
    const saved = outcome.data as CandidateProfile;
    setProfile(saved);
    setForm(toForm(saved.fields));
    setMessage({ text: "Your profile is saved.", failed: false });
  }

  return (
    <div className="grid" style={{ gap: 18 }}>
      <section className="card" aria-labelledby="cand-account">
        <h3 id="cand-account">Account</h3>
        <dl className="candidate-facts">
          <div><dt>Candidate ID</dt><dd>{profile.candidate_code}</dd></div>
          <div><dt>Name</dt><dd>{profile.name}</dd></div>
          <div><dt>Email</dt><dd>{profile.email}{profile.email_verified && <span className="status" style={{ marginLeft: 8 }}>Verified</span>}</dd></div>
          <div><dt>Mobile</dt><dd>{profile.mobile || "Not provided"} <span className="muted" style={{ fontSize: 13 }}>· ask your recruiter to change it</span></dd></div>
        </dl>
      </section>

      <form className="card form" onSubmit={save} aria-labelledby="cand-details">
        <h3 id="cand-details" style={{ marginBottom: 0 }}>My details</h3>
        {editable.length === 0 ? <p className="muted">The recruitment team has not opened any field for self-service yet.</p> : (
          <div className="form-grid">
            {editable.map((f) => (
              <div className="field" key={f.key}>
                <label htmlFor={`cand-${f.key}`}>{f.label}</label>
                {f.kind === "yesno" || f.kind === "contact" ? (
                  <select id={`cand-${f.key}`} value={form[f.key]} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}>
                    <option value="">Not set</option>
                    {(f.kind === "yesno" ? [{ value: "yes", label: "Yes" }, { value: "no", label: "No" }] : CONTACT_OPTIONS).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                ) : (
                  <input
                    id={`cand-${f.key}`}
                    type={f.kind === "number" ? "number" : f.kind === "date" ? "date" : f.kind === "url" ? "url" : "text"}
                    min={f.kind === "number" ? 0 : undefined}
                    max={f.kind === "number" ? 365 : undefined}
                    value={form[f.key]}
                    aria-describedby={f.hint ? `cand-${f.key}-hint` : undefined}
                    onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                  />
                )}
                {f.hint && <span id={`cand-${f.key}-hint`} className="muted" style={{ fontSize: 12 }}>{f.hint}</span>}
              </div>
            ))}
          </div>
        )}
        {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} style={{ margin: 0 }}>{message.text}</p>}
        {editable.length > 0 && <button className="btn" type="submit" disabled={busy} style={{ justifySelf: "start" }}>{busy ? "Saving…" : "Save my details"}</button>}
        {fixed.length > 0 && (
          <div>
            <h4 style={{ margin: "8px 0" }}>Kept by your recruiter</h4>
            <dl className="candidate-facts">
              {fixed.map((f) => <div key={f.key}><dt>{f.label}</dt><dd>{displayValue(f.key, profile.fields[f.key])}</dd></div>)}
            </dl>
          </div>
        )}
      </form>

      <EmailChange pending={profile.pending_email} />
    </div>
  );
}

function EmailChange({ pending }: { pending: string | null }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const formEl = event.currentTarget;
    const data = new FormData(formEl);
    const email = String(data.get("new_email") || "").trim().toLowerCase();
    setBusy(true);
    setMessage(null);
    const outcome = await sendJson(EMAIL_URL, "POST", { new_email: email, current_password: data.get("current_password") });
    setBusy(false);
    if (!outcome.ok) return setMessage({ text: (outcome.status ?? 0) >= 500 ? SERVER_ERROR : outcome.message, failed: true });
    formEl.reset();
    setMessage({ text: `If ${email} can be used, we've sent a confirmation link to it. Your current email stays in use until you open that link.`, failed: false });
  }

  return (
    <form className="card form" onSubmit={submit} aria-labelledby="cand-email-change">
      <h3 id="cand-email-change" style={{ marginBottom: 0 }}>Change my email</h3>
      {pending && <p className="status pending" style={{ justifySelf: "start", margin: 0 }}>Waiting for confirmation: {pending}</p>}
      <div className="form-grid">
        <div className="field"><label htmlFor="cand-new-email">New email</label><input id="cand-new-email" name="new_email" type="email" autoComplete="email" required maxLength={255} /></div>
        <div className="field"><label htmlFor="cand-current-password">Current password</label><input id="cand-current-password" name="current_password" type="password" autoComplete="current-password" required /></div>
      </div>
      {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} style={{ margin: 0 }}>{message.text}</p>}
      <button className="btn secondary" type="submit" disabled={busy} style={{ justifySelf: "start" }}>{busy ? "Sending…" : "Send confirmation link"}</button>
    </form>
  );
}
