"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ROLE_DASHBOARD_PATH } from "@/lib/navigation";

function message(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to accept this invite.";
}

// SCH-003-AC06: a consumed, expired, or revoked token gets an honest, specific message
// -- never a generic broken-link page. The backend already distinguishes these cases in
// its error detail; this form surfaces that text directly rather than inventing its own.
export default function SchoolInviteAcceptForm({ token }: { token: string }) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const response = await fetch(`/api/v1/school/invites/${token}/accept`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: form.get("password") }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setError(message(data.detail));
      return;
    }
    router.push(ROLE_DASHBOARD_PATH[data.role] || "/");
    router.refresh();
  }

  return (
    <form className="form" onSubmit={submit}>
      <div className="field">
        <label htmlFor="invite-password">Choose a password</label>
        <input id="invite-password" name="password" type="password" minLength={10} autoComplete="new-password" required />
        <span className="muted" style={{ fontSize: 12 }}>Use at least 10 characters.</span>
      </div>
      {error && (
        <div className="form-error" role="alert" aria-live="assertive">
          {error}
        </div>
      )}
      <button className="btn" disabled={busy}>
        {busy ? "Setting up your account…" : "Accept and set up login"}
      </button>
    </form>
  );
}
