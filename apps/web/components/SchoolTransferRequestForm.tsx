"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState, useTransition } from "react";

import { formatDate } from "@/lib/formatDate";
import { detailMessage, isRequestBody } from "@/lib/apiErrors";
import type { SchoolRef } from "@/lib/transfers";

// ENH-005 -- a coordinator asks to move ONE of their students to another school (spec §5.2, §7.1). Filing is reversible (the
// coordinator can cancel), so there is no confirm step; that is kept for the admin's irreversible approve/reject. The destinations
// and any pending request arrive as props, read on the server in the same Promise.all as the rest of the page, so opening this
// needs no client round-trip and no loading state.
type Pending = { to_school_name: string; created_at: string };

const NOT_COMPLETED = "The request did not complete. Check your connection and try again; your entry is kept.";
const UNCONFIRMED = "The reply could not be confirmed as a filed request. Your entry is kept; repeating it is safe (a student can have only one pending request).";

export default function SchoolTransferRequestForm({ studentId, destinations, pending }: { studentId: string; destinations: SchoolRef[] | null; pending: Pending | null }) {
  const router = useRouter();
  const [, startRefresh] = useTransition();
  const [school, setSchool] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  // `busy` is state, so two clicks in the same task both see false; a ref is updated at once (found by the browser QA).
  const inFlight = useRef(false);

  useEffect(() => {
    if (error) alertRef.current?.focus();
  }, [error]);

  if (sent) {
    return <div role="status" className="form-message">{sent}</div>;
  }
  if (pending) {
    return <div role="status" className="form-message">Transfer to {pending.to_school_name} requested {formatDate(pending.created_at)}. Waiting for admin review.</div>;
  }
  if (destinations === null) return <p className="muted">Transfers are unavailable right now.</p>;
  if (destinations.length === 0) return <p className="muted">No other partner schools are available.</p>;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || inFlight.current) return;
    setError(null);
    setExpired(false);
    if (!school) {
      setFieldError("Choose a school.");
      return;
    }
    setFieldError(null);
    inFlight.current = true;
    setBusy(true);
    let response: Response;
    try {
      response = await fetch(`/api/v1/school/students/${studentId}/transfer-requests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to_school_id: school, ...(reason.trim() ? { reason: reason.trim() } : {}) }),
      });
    } catch {
      inFlight.current = false;
      setBusy(false);
      setError(NOT_COMPLETED);
      return;
    }
    const data = await response.json().catch(() => null);
    inFlight.current = false;
    setBusy(false);
    if (response.status === 401) {
      setExpired(true);
      setError("Your session has expired. Your entry is kept. ");
      return;
    }
    if (!response.ok) {
      setError(detailMessage(data?.detail));
      return;
    }
    // A 2xx whose body is not the request (a proxy's page, an empty body) is not proof it was filed. Filing twice is harmless: a student can
    // have one pending request, so the repeat is a 409 at worst.
    if (!isRequestBody(data)) {
      setError(UNCONFIRMED);
      return;
    }
    setSent("Transfer request sent for review. An admin decides; nothing changes until it is approved.");
    startRefresh(() => router.refresh());
  }

  return (
    <form className="form" onSubmit={submit} noValidate>
      {/* `.field` is a grid item whose width follows its content, so a <select> holding one very long school name grew the field to 2,300px and
          `max-width: 100%` then resolved against that. `width: 100%` plus `min-width: 0` keeps both inside the form (measured in the live page). */}
      <div className="field" style={{ minWidth: 0 }}>
        <label htmlFor="transfer-destination">Destination school</label>
        <select
          id="transfer-destination" className="select" style={{ width: "100%", maxWidth: "100%" }} value={school} disabled={busy} aria-invalid={fieldError ? true : undefined}
          aria-describedby={fieldError ? "transfer-destination-error" : undefined} onChange={(e) => setSchool(e.target.value)}
        >
          <option value="" disabled>Select a school</option>
          {destinations.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        {fieldError && <span id="transfer-destination-error" className="form-error">{fieldError}</span>}
      </div>
      <div className="field">
        <label htmlFor="transfer-reason">Reason (optional)</label>
        <textarea id="transfer-reason" className="search" rows={3} maxLength={500} value={reason} disabled={busy} onChange={(e) => setReason(e.target.value)} />
      </div>
      <button type="submit" className="btn" disabled={busy}>{busy ? "Sending request…" : "Request transfer"}</button>
      {error && (
        <div ref={alertRef} tabIndex={-1} className="form-error" role="alert">
          {error}
          {expired && <Link href="/overseas/login">Sign in again</Link>}
        </div>
      )}
    </form>
  );
}
