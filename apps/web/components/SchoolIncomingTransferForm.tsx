"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";

import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import { refocus } from "@/lib/focus";

// ENH-005 -- a coordinator asks for a student who is at ANOTHER school, by their Student ID (spec §5.2, §7.1).
// Security review S3: the server answers every well-formed code the same way, so this screen must too. It says one neutral
// sentence and never "found", "unknown" or "no such student" -- otherwise the form would be the existence oracle the
// identical 202 exists to prevent. The Student ID is only ever sent in a POST body, never a URL.
export const NEUTRAL_SUBMITTED = "If that Student ID belongs to a student at another school, your request has been sent to an admin for review.";

const CODE = /^[0-9A-Fa-f]{8}$/;

export default function SchoolIncomingTransferForm({ onSubmitted }: { onSubmitted?: () => void }) {
  const [code, setCode] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [alert, setAlert] = useState<{ text: string; expired?: boolean } | null>(null);
  const [done, setDone] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const inFlight = useRef(false); // `busy` is state: two clicks in one task both see false (found by the browser QA)

  useEffect(() => {
    if (alert) alertRef.current?.focus();
  }, [alert]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || inFlight.current) return;
    const value = code.trim().toUpperCase();
    setAlert(null);
    setDone(false);
    if (!CODE.test(value)) {
      setFieldError("Enter all 8 characters of the Student ID (digits 0-9 and letters A-F).");
      inputRef.current?.focus();
      return;
    }
    setFieldError(null);
    inFlight.current = true;
    setBusy(true);
    let response: Response;
    try {
      response = await fetch("/api/v1/school/transfer-requests/incoming", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ student_code: value, ...(reason.trim() ? { reason: reason.trim() } : {}) }),
      });
    } catch {
      inFlight.current = false;
      setBusy(false);
      setAlert({ text: NOT_COMPLETED });
      return;
    }
    const data = await response.json().catch(() => null);
    inFlight.current = false;
    setBusy(false);
    if (response.status === 401) {
      setAlert({ text: "Your session has expired. Your entry is kept. ", expired: true });
      return;
    }
    if (response.status !== 202 || data?.accepted !== true) {
      setAlert({ text: response.ok ? NOT_COMPLETED : detailMessage(data?.detail) });
      return;
    }
    setDone(true);
    setCode("");
    setReason("");
    // The field was disabled while the request ran and is only re-enabled on the next render, so focus it after that.
    refocus("incoming-code");
    onSubmitted?.();
  }

  return (
    <form className="form" onSubmit={submit} noValidate>
      <h3>Request a student from another school</h3>
      <p className="muted">Ask for a student to join your school using their Student ID. An admin reviews every request; nothing changes until it is approved.</p>
      <div className="field">
        <label htmlFor="incoming-code">Student ID</label>
        <input
          ref={inputRef} id="incoming-code" className="search" value={code} maxLength={8} autoComplete="off" autoCapitalize="characters" spellCheck={false}
          disabled={busy} aria-invalid={fieldError ? true : undefined} aria-describedby={fieldError ? "incoming-code-hint incoming-code-error" : "incoming-code-hint"}
          onChange={(e) => setCode(e.target.value)}
        />
        <span id="incoming-code-hint" className="muted">For example A3F9C21B.</span>
        {fieldError && <span id="incoming-code-error" className="form-error">{fieldError}</span>}
      </div>
      <div className="field">
        <label htmlFor="incoming-reason">Reason (optional)</label>
        <textarea id="incoming-reason" className="search" rows={3} maxLength={500} value={reason} disabled={busy} onChange={(e) => setReason(e.target.value)} />
      </div>
      <button type="submit" className="btn" disabled={busy}>{busy ? "Sending request…" : "Request student"}</button>
      <div role="status" aria-live="polite">{done && <div className="form-message">{NEUTRAL_SUBMITTED}</div>}</div>
      {alert && (
        <div ref={alertRef} tabIndex={-1} className="form-error" role="alert">
          {alert.text}
          {alert.expired && <Link href="/overseas/login">Sign in again</Link>}
        </div>
      )}
    </form>
  );
}
