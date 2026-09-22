"use client";

import { CSSProperties, FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";

function message(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  }
  return "Unable to update your profile. Try again in a moment.";
}

// Announced to assistive tech but not shown: the button label already says "Saving…" on screen.
const VISUALLY_HIDDEN: CSSProperties = { position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)", whiteSpace: "nowrap" };

// Where a signed-out visitor returns to after signing in.
const NEXT = encodeURIComponent("/account/profile");

export default function ProfileForm({ fullName, phone }: { fullName: string; phone: string | null }) {
  const [error, setError] = useState("");
  const [errorField, setErrorField] = useState<"full_name" | null>(null);
  const [notice, setNotice] = useState("");
  const [signedOut, setSignedOut] = useState(false);
  const [busy, setBusy] = useState(false);
  // Canonical values, updated only after a successful save (from the server's response) -- never
  // from onChange, so typing doesn't remount the inputs mid-edit. Keys the inputs below so React
  // re-mounts them with the new defaultValue exactly once, right after a save.
  const [saved, setSaved] = useState({ fullName, phone: phone ?? "" });
  const submitting = useRef(false);
  const [focusRequest, setFocusRequest] = useState<{ id: string } | null>(null);

  useEffect(() => {
    if (focusRequest) document.getElementById(focusRequest.id)?.focus();
  }, [focusRequest]);

  function finish(focusId = "profile-submit") {
    submitting.current = false;
    setBusy(false);
    setFocusRequest({ id: focusId });
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
    const phoneValue = String(data.get("phone") || "").trim();
    let response: Response;
    try {
      response = await fetch("/api/v1/auth/me", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: data.get("full_name"), phone: phoneValue || null }),
      });
    } catch {
      // Safe to retry (spec §4): this PATCH has no rate limiter or one-shot side effect, unlike
      // change-password, so there's no "unknown outcome" caveat needed here.
      setError("Network error. Try again.");
      finish();
      return;
    }
    const body = await response.json().catch(() => ({}));
    if (response.ok) {
      setSaved({ fullName: body.full_name, phone: body.phone ?? "" });
      setNotice("Your profile was updated.");
      finish();
      return;
    }
    if (response.status === 401) {
      setSignedOut(true);
      finish();
      return;
    }
    setError(message(body.detail));
    if (response.status === 422) {
      setErrorField("full_name");
      finish("profile-full-name");
      return;
    }
    finish();
  }

  return (
    <form className="form" onSubmit={submit} aria-label="Your profile" aria-busy={busy} noValidate>
      <div className="field">
        <label htmlFor="profile-full-name">Full name</label>
        <input
          id="profile-full-name"
          key={saved.fullName}
          name="full_name"
          type="text"
          minLength={2}
          maxLength={160}
          defaultValue={saved.fullName}
          aria-invalid={errorField === "full_name" ? true : undefined}
          aria-describedby={errorField === "full_name" ? "profile-error" : undefined}
          required
        />
      </div>
      <div className="field">
        <label htmlFor="profile-phone">Phone</label>
        <input id="profile-phone" key={saved.phone} name="phone" type="text" maxLength={40} defaultValue={saved.phone} />
      </div>
      {error && (
        <div id="profile-error" className="form-error" role="alert" aria-live="assertive">
          <p style={{ margin: 0 }}>{error}</p>
        </div>
      )}
      {signedOut && (
        <div className="form-error" role="alert" aria-live="assertive">
          <p style={{ margin: 0 }}>Your session has expired. Sign in again to update your profile.</p>
          <p style={{ margin: "6px 0 0" }}>
            <Link href={`/it/login?next=${NEXT}`} style={{ color: "var(--blue)", fontWeight: 800 }}>IT Training sign in</Link>{" "}
            <Link href={`/overseas/login?next=${NEXT}`} style={{ color: "var(--blue)", fontWeight: 800 }}>Overseas Education sign in</Link>
          </p>
        </div>
      )}
      {busy ? (
        <div role="status" aria-live="polite" style={VISUALLY_HIDDEN}>
          Saving your profile…
        </div>
      ) : (
        notice && (
          <div className="form-message" role="status" aria-live="polite">
            {notice}
          </div>
        )
      )}
      <button id="profile-submit" className="btn" aria-disabled={busy}>
        {busy ? "Saving…" : "Save changes"}
      </button>
    </form>
  );
}
