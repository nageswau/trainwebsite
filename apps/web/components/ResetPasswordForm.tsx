"use client";

import { FormEvent, useState } from "react";
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
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/v1/auth/reset-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, new_password: form.get("new_password") }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setError(message(data.detail));
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
        <input id="reset-new-password" name="new_password" type="password" minLength={10} autoComplete="new-password" required />
        <span className="muted" style={{ fontSize: 12 }}>Use at least 10 characters.</span>
      </div>
      {error && (
        <div className="form-error" role="alert" aria-live="assertive">
          {error}
        </div>
      )}
      <button className="btn" disabled={busy}>
        {busy ? "Resetting…" : "Reset password"}
      </button>
    </form>
  );
}
