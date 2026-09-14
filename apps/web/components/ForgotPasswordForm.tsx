"use client";

import { FormEvent, useState } from "react";

export default function ForgotPasswordForm() {
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [devToken, setDevToken] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/v1/auth/forgot-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: form.get("email") }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    // Always show the same confirmation regardless of whether the account exists
    // (no user enumeration) -- the backend already returns an identical shape either way.
    setSubmitted(true);
    if (data.development_reset_token) setDevToken(data.development_reset_token);
  }

  if (submitted) {
    return (
      <div>
        <p role="status" aria-live="polite">
          If an account exists for that email, we&apos;ve sent instructions to reset the password.
        </p>
        {devToken && (
          <p className="muted" style={{ fontSize: 12 }}>
            Development only: <a href={`reset-password?token=${devToken}`}>reset link</a>
          </p>
        )}
      </div>
    );
  }

  return (
    <form className="form" onSubmit={submit}>
      <div className="field">
        <label htmlFor="forgot-email">Email</label>
        <input id="forgot-email" name="email" type="email" autoComplete="email" required />
      </div>
      <button className="btn" disabled={busy}>
        {busy ? "Sending…" : "Send reset instructions"}
      </button>
    </form>
  );
}
