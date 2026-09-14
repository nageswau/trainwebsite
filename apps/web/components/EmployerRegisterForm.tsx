"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ROLE_DASHBOARD_PATH } from "@/lib/navigation";

function message(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  }
  return "Unable to complete registration";
}

// EMP-001: registration completes and signs the employer in immediately -- whether
// registration needs Admin approval before activation is an explicitly open item
// (FEATURE_QUESTIONS.md #7), so this form never asks the user to "wait for approval."
export default function EmployerRegisterForm() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/v1/employer/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: form.get("email"),
        password: form.get("password"),
        full_name: form.get("full_name"),
        phone: form.get("phone") || null,
        company_name: form.get("company_name"),
        company_website: form.get("company_website") || null,
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setError(message(data.detail));
      return;
    }
    router.push(ROLE_DASHBOARD_PATH[data.user.role] || "/");
    router.refresh();
  }

  return (
    <form className="form" onSubmit={submit}>
      <div className="field">
        <label htmlFor="emp-reg-company">Company name</label>
        <input id="emp-reg-company" name="company_name" required minLength={2} maxLength={180} />
      </div>
      <div className="field">
        <label htmlFor="emp-reg-website">Company website (optional)</label>
        <input id="emp-reg-website" name="company_website" type="url" placeholder="https://" />
      </div>
      <div className="field">
        <label htmlFor="emp-reg-name">Your name</label>
        <input id="emp-reg-name" name="full_name" required minLength={2} maxLength={160} />
      </div>
      <div className="field">
        <label htmlFor="emp-reg-phone">Phone (optional)</label>
        <input id="emp-reg-phone" name="phone" type="tel" />
      </div>
      <div className="field">
        <label htmlFor="emp-reg-email">Work email</label>
        <input id="emp-reg-email" name="email" type="email" autoComplete="email" required />
      </div>
      <div className="field">
        <label htmlFor="emp-reg-password">Password</label>
        <input id="emp-reg-password" name="password" type="password" autoComplete="new-password" required minLength={10} maxLength={128} />
      </div>
      {error && <div className="form-error" role="alert" aria-live="assertive">{error}</div>}
      <button className="btn" disabled={busy}>{busy ? "Creating your account…" : "Register your company"}</button>
    </form>
  );
}
