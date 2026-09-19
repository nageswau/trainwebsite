"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

function message(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  }
  return "Unable to reset password";
}

export default function ResetPasswordForm({ division }: { division: "it" | "overseas" }) {
  const router = useRouter();
  const search = useSearchParams();
  const token = search.get("token") || "";
  const [error, setError] = useState("");
  const [expiredLink, setExpiredLink] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setExpiredLink(false);
    const form = new FormData(event.currentTarget);
    let response: Response;
    try {
      response = await fetch("/api/v1/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: form.get("new_password") }),
      });
    } catch {
      // A dropped connection never reaches the server, so the link is still valid: just let them retry.
      setBusy(false);
      setError("Network error -- your password was not changed. Check your connection and try again.");
      return;
    }
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setError(message(data.detail));
      // 400 is the one generic answer for an unknown, used, expired or revoked link (ENH-003), so it
      // is the only case where a way to get a fresh link helps; a 422 is about the password itself.
      setExpiredLink(response.status === 400);
      return;
    }
    router.push(`/${division}/login`);
  }

  if (!token) {
    return (
      <p role="alert" aria-live="assertive">
        This reset link is missing its token. Request a new one from the forgot-password page.
      </p>
    );
  }

  return (
    <form className="form" onSubmit={submit}>
      <div className="field">
        <label htmlFor="reset-new-password">New password</label>
        <input id="reset-new-password" name="new_password" type="password" minLength={10} maxLength={128} autoComplete="new-password" aria-describedby="reset-password-hint" required />
        <span id="reset-password-hint" className="muted" style={{ fontSize: 12 }}>Use at least 10 characters.</span>
      </div>
      {error && (
        <div className="form-error" role="alert" aria-live="assertive">
          <p style={{ margin: 0 }}>{error}</p>
          {expiredLink && (
            <p style={{ margin: "6px 0 0" }}>
              <Link href={`/${division}/forgot-password`} style={{ color: "var(--blue)", fontWeight: 800 }}>Request a new reset link</Link>{" "}
              or, if this was your first-time invitation, ask your administrator to re-send it.
            </p>
          )}
        </div>
      )}
      <button className="btn" disabled={busy}>
        {busy ? "Resetting…" : "Reset password"}
      </button>
    </form>
  );
}
