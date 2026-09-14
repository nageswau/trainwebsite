"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ROLE_DASHBOARD_PATH } from "@/lib/navigation";

function message(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  }
  return "Unable to sign in";
}

export default function LoginForm({ division }: { division: "it" | "overseas" | "global" }) {
  const router = useRouter();
  const search = useSearchParams();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: form.get("email"), password: form.get("password"), division }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setError(message(data.detail));
      return;
    }
    router.push(search.get("next") || ROLE_DASHBOARD_PATH[data.user.role] || "/");
    router.refresh();
  }

  return <form className="form" onSubmit={submit}>
    <div className="field">
      <label htmlFor="login-email">Email</label>
      <input id="login-email" name="email" type="email" autoComplete="email" required />
    </div>
    <div className="field">
      <label htmlFor="login-password">Password</label>
      <input id="login-password" name="password" type="password" autoComplete="current-password" required />
    </div>
    {error && <div className="form-error" role="alert" aria-live="assertive">{error}</div>}
    <button className="btn" disabled={busy}>{busy ? "Signing in…" : "Sign in securely"}</button>
    {division !== "global" && (
      <p className="muted" style={{ fontSize: 13 }}>
        <Link href={`/${division}/forgot-password`} style={{ color: "var(--blue)", fontWeight: 800 }}>Forgot your password?</Link>
      </p>
    )}
    <p className="muted" style={{ fontSize: 13 }}>
      Use the portal that matches your account. Role and division access is verified by the API.
    </p>
  </form>;
}
