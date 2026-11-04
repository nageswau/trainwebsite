"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { CONSENT_TEXT, CONSENT_VERSION, REGISTER_URL, RESEND_URL } from "@/lib/candidatePortal";

// hrc-022 (DEC-SCOPE-386 C2/C5): the external candidate's registration. The server answers the same whatever the email, so the success
// state never says whether an account was created -- only "check your inbox", with a Resend link.
export default function CandidateRegisterForm() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [devToken, setDevToken] = useState<string | null>(null);
  const [resent, setResent] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    if (form.get("password") !== form.get("confirm_password")) return setError("The passwords do not match.");
    setBusy(true);
    setError("");
    const email = String(form.get("email") || "").trim();
    const outcome = await sendJson(REGISTER_URL, "POST", {
      full_name: form.get("full_name"), email, phone: form.get("phone") || null, password: form.get("password"), consent_version: CONSENT_VERSION,
    });
    setBusy(false);
    if (!outcome.ok) return setError((outcome.status ?? 0) >= 500 ? "We couldn't create your account. Please try again." : outcome.message);
    setSentTo(email);
    setDevToken(typeof outcome.data.development_verification_token === "string" ? outcome.data.development_verification_token : null);
  }

  async function resend() {
    if (!sentTo || busy) return;
    setBusy(true);
    const outcome = await sendJson(RESEND_URL, "POST", { email: sentTo });
    setBusy(false);
    if (outcome.ok && typeof outcome.data.development_verification_token === "string") setDevToken(outcome.data.development_verification_token);
    setResent(outcome.ok ? "If the address needs verifying, a new link is on its way." : outcome.message);
  }

  if (sentTo) {
    return (
      <div className="form">
        <div className="form-message" role="status">
          Check your inbox at <strong>{sentTo}</strong>. Open the link we sent to verify your email, then sign in. The link expires in 24 hours.
        </div>
        <div className="actions">
          <button type="button" className="btn secondary" onClick={() => void resend()} disabled={busy}>{busy ? "Sending…" : "Resend the link"}</button>
          <Link className="btn ghost" href="/it/login">Go to sign in</Link>
        </div>
        {resent && <p className="muted" role="status">{resent}</p>}
        {devToken && <p className="muted" style={{ fontSize: 13 }}>Development only: <Link href={`/it/careers/verify-email?token=${encodeURIComponent(devToken)}`} style={{ color: "var(--blue)", fontWeight: 800 }}>open the verification link</Link></p>}
      </div>
    );
  }

  return (
    <form className="form" onSubmit={submit}>
      <div className="field"><label htmlFor="cand-name">Full name</label><input id="cand-name" name="full_name" autoComplete="name" required minLength={2} maxLength={160} /></div>
      <div className="field"><label htmlFor="cand-email">Email</label><input id="cand-email" name="email" type="email" autoComplete="email" required maxLength={255} /></div>
      <div className="field"><label htmlFor="cand-phone">Mobile (optional)</label><input id="cand-phone" name="phone" type="tel" autoComplete="tel" maxLength={40} /></div>
      <div className="form-grid">
        <div className="field"><label htmlFor="cand-password">Password</label><input id="cand-password" name="password" type="password" autoComplete="new-password" required minLength={10} maxLength={128} aria-describedby="cand-password-hint" /></div>
        <div className="field"><label htmlFor="cand-confirm">Confirm password</label><input id="cand-confirm" name="confirm_password" type="password" autoComplete="new-password" required minLength={10} maxLength={128} /></div>
      </div>
      <p id="cand-password-hint" className="muted" style={{ fontSize: 13, margin: 0 }}>At least 10 characters.</p>
      <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
        <input type="checkbox" name="consent" required style={{ marginTop: 4 }} />
        <span className="muted" style={{ fontSize: 13 }}>{CONSENT_TEXT}</span>
      </label>
      {error && <div className="form-error" role="alert">{error}</div>}
      <button className="btn" type="submit" disabled={busy}>{busy ? "Creating account…" : "Create candidate account"}</button>
    </form>
  );
}
