"use client";

import { FormEvent, useRef, useState } from "react";
import Link from "next/link";
import { refocus } from "@/lib/focus";

function message(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  }
  return "Unable to change password. Try again in a moment.";
}

function waitLabel(seconds: number) {
  const minutes = Math.ceil(seconds / 60);
  return minutes <= 1 ? "a minute" : `${minutes} minutes`;
}

// Where a signed-out visitor returns to after signing in (LoginForm honours `?next=`).
const NEXT = encodeURIComponent("/account/password");

export default function ChangePasswordForm({ email, forgotPasswordHref }: { email: string; forgotPasswordHref?: string }) {
  const [error, setError] = useState("");
  const [errorField, setErrorField] = useState<"current" | "new" | null>(null);
  const [notice, setNotice] = useState("");
  const [signedOut, setSignedOut] = useState(false);
  const [showPasswords, setShowPasswords] = useState(false);
  const [busy, setBusy] = useState(false);
  // State lags a render, so a second submit event could slip past `busy`; a repeat after success would be a 400 that
  // burns one of the five rate-limit attempts.
  const submitting = useRef(false);

  function finish(focusId: string) {
    submitting.current = false;
    setBusy(false);
    refocus(focusId); // a control disabled while busy loses keyboard focus; put it where the user needs it next
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    submitting.current = true;
    const form = event.currentTarget;
    setBusy(true);
    setError("");
    setErrorField(null);
    setNotice("");
    setSignedOut(false);
    const data = new FormData(form);
    let response: Response;
    try {
      response = await fetch("/api/v1/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: data.get("current_password"), new_password: data.get("new_password") }),
      });
    } catch {
      // The server commits the change BEFORE it answers, so a lost response is an unknown outcome -- and resubmitting
      // the same form would fail with "Incorrect current password" if the change did go through.
      setError("Network error -- we could not confirm whether your password was changed. Sign in with your new password; if that fails, try again.");
      finish("change-password-submit");
      return;
    }
    const body = await response.json().catch(() => ({}));
    if (response.ok) {
      form.reset();
      setNotice("Your password was changed.");
      finish("change-password-submit");
      return;
    }
    if (response.status === 401) {
      setSignedOut(true);
      finish("change-password-submit");
      return;
    }
    if (response.status === 429) {
      const seconds = Number(response.headers.get("Retry-After"));
      setError(Number.isFinite(seconds) && seconds > 0 ? `Too many incorrect attempts. Try again in ${waitLabel(seconds)}.` : message(body.detail));
      finish("change-password-submit");
      return;
    }
    setError(message(body.detail));
    if (response.status === 400) {
      // Clear the wrong value, keep the new password the user already typed, and put the cursor where they retype.
      const current = form.elements.namedItem("current_password");
      if (current instanceof HTMLInputElement) current.value = "";
      setErrorField("current");
      finish("change-current-password");
      return;
    }
    if (response.status === 422) {
      setErrorField("new");
      finish("change-new-password");
      return;
    }
    finish("change-password-submit");
  }

  const inputType = showPasswords ? "text" : "password";

  return (
    <form className="form" onSubmit={submit} aria-label="Change password" aria-busy={busy}>
      {/* Lets password managers update the right saved login. Visually hidden, not focusable, never sent. */}
      <input type="text" name="username" autoComplete="username" value={email} readOnly tabIndex={-1} aria-hidden="true" style={{ position: "absolute", width: 1, height: 1, opacity: 0, pointerEvents: "none" }} />
      <div className="field">
        <label htmlFor="change-current-password">Current password</label>
        <input
          id="change-current-password"
          name="current_password"
          type={inputType}
          maxLength={1024}
          autoComplete="current-password"
          autoCapitalize="off"
          spellCheck={false}
          aria-invalid={errorField === "current" ? true : undefined}
          aria-describedby={errorField === "current" ? "change-password-error" : undefined}
          required
        />
      </div>
      <div className="field">
        <label htmlFor="change-new-password">New password</label>
        <input
          id="change-new-password"
          name="new_password"
          type={inputType}
          minLength={10}
          maxLength={128}
          autoComplete="new-password"
          autoCapitalize="off"
          spellCheck={false}
          aria-invalid={errorField === "new" ? true : undefined}
          aria-describedby={errorField === "new" ? "change-password-hint change-password-error" : "change-password-hint"}
          required
        />
        <span id="change-password-hint" className="muted" style={{ fontSize: 12 }}>Use at least 10 characters.</span>
      </div>
      <div className="field">
        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <input id="change-show-passwords" type="checkbox" checked={showPasswords} onChange={(event) => setShowPasswords(event.target.checked)} />
          Show passwords
        </label>
      </div>
      {error && (
        <div id="change-password-error" className="form-error" role="alert" aria-live="assertive">
          <p style={{ margin: 0 }}>{error}</p>
          {errorField === "current" && forgotPasswordHref && (
            <p style={{ margin: "6px 0 0" }}>
              <Link href={forgotPasswordHref} style={{ color: "var(--blue)", fontWeight: 800 }}>Forgot your current password?</Link>
            </p>
          )}
        </div>
      )}
      {signedOut && (
        <div className="form-error" role="alert" aria-live="assertive">
          <p style={{ margin: 0 }}>Your session has expired. Sign in again to change your password.</p>
          <p style={{ margin: "6px 0 0" }}>
            <Link href={`/it/login?next=${NEXT}`} style={{ color: "var(--blue)", fontWeight: 800 }}>IT Training sign in</Link>{" "}
            <Link href={`/overseas/login?next=${NEXT}`} style={{ color: "var(--blue)", fontWeight: 800 }}>Overseas Education sign in</Link>
          </p>
        </div>
      )}
      {notice && (
        <div className="form-message" role="status" aria-live="polite">
          {notice}
        </div>
      )}
      <button id="change-password-submit" className="btn" disabled={busy}>
        {busy ? "Changing…" : "Change password"}
      </button>
      <p className="muted" style={{ fontSize: 13, margin: 0 }}>
        You stay signed in on this device. Other devices stay signed in until their sessions expire.
      </p>
    </form>
  );
}
