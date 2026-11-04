"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { CANDIDATE_PORTAL_HOME, RESEND_URL, VERIFY_URL } from "@/lib/candidatePortal";

// hrc-022 (DEC-SCOPE-385 C3): the link verifies on a click, never on page load -- a mail scanner that opens the link must not use it up.
export default function CandidateVerifyEmail({ token }: { token: string }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string; purpose?: string } | null>(null);

  async function verify() {
    if (busy) return;
    setBusy(true);
    const outcome = await sendJson(VERIFY_URL, "POST", { token });
    setBusy(false);
    if (!outcome.ok) {
      return setResult({ ok: false, text: (outcome.status ?? 0) >= 500 ? "We couldn't verify the link. Please try again." : outcome.message });
    }
    const purpose = String(outcome.data.purpose);
    setResult({ ok: true, purpose, text: purpose === "email_change" ? "Your email address is updated." : "Your email is verified. You can now sign in." });
  }

  if (!token) return <div className="form-error" role="alert">This link is incomplete. Open the full link from your email.</div>;
  if (result?.ok) {
    return (
      <div className="form">
        <div className="form-message" role="status">{result.text}</div>
        <Link className="btn" href={result.purpose === "email_change" ? CANDIDATE_PORTAL_HOME : "/it/login"}>{result.purpose === "email_change" ? "Back to my profile" : "Sign in"}</Link>
      </div>
    );
  }
  return (
    <div className="form">
      {result && <div className="form-error" role="alert">{result.text}</div>}
      {result ? <ResendLink /> : <button className="btn" type="button" onClick={() => void verify()} disabled={busy}>{busy ? "Verifying…" : "Verify my email"}</button>}
    </div>
  );
}

// C5: a new link for an account that is still unverified. The answer is the same for any address.
function ResendLink() {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    const outcome = await sendJson(RESEND_URL, "POST", { email: String(new FormData(event.currentTarget).get("email") || "").trim() });
    setBusy(false);
    setMessage(outcome.ok ? "If that address has an account waiting for verification, a new link is on its way." : outcome.message);
  }

  return (
    <form className="form" onSubmit={submit}>
      <div className="field"><label htmlFor="resend-email">Your email, for a new link</label><input id="resend-email" name="email" type="email" autoComplete="email" required /></div>
      <button className="btn secondary" type="submit" disabled={busy}>{busy ? "Sending…" : "Send a new link"}</button>
      {message && <p className="muted" role="status">{message}</p>}
    </form>
  );
}
