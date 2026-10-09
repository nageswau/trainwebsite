"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import LocalTime from "@/components/LocalTime";
import { detailMessage } from "@/lib/apiErrors";

// rec-010 (DEC-SCOPE-138): an IT student joins or leaves the placement candidate pool. Consent is the gate to employer visibility,
// so joining needs the box ticked and sends the version that was shown (the server answers 409 if the wording changed since).
// Leaving asks first. A ref guards double submits; every write returns the new state, so nothing is re-fetched.
type PoolEvent = { action: "opt_in" | "opt_out"; consent_version: string; created_at: string };
type PoolState = { opted_in: boolean; consent: { version: string; text: string }; history: PoolEvent[] };

const URL = "/api/v1/account/placement-pool";
const LOAD_FAILED = "Couldn't load your placement pool status.";
const SAVE_FAILED = "Couldn't save. Check your connection and try again.";

export default function PlacementPoolCard() {
  const [pool, setPool] = useState<PoolState | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const submitting = useRef(false);

  const load = useCallback(() => {
    setLoadFailed(false);
    fetch(URL)
      .then(async (response) => {
        if (!response.ok) throw new Error(String(response.status));
        setPool(await response.json());
      })
      .catch(() => setLoadFailed(true));
  }, []);

  useEffect(load, [load]);

  async function change(path: "opt-in" | "opt-out", done: string) {
    if (submitting.current || !pool) return;
    submitting.current = true;
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch(`${URL}/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: path === "opt-in" ? JSON.stringify({ consent_version: pool.consent.version }) : undefined,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setMessage({ text: detailMessage(data.detail, SAVE_FAILED), failed: true });
        return;
      }
      setPool(data);
      setAgreed(false);
      setConfirming(false);
      setMessage({ text: done, failed: false });
    } catch {
      setMessage({ text: SAVE_FAILED, failed: true });
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  if (loadFailed)
    return (
      <div className="action-card">
        <h3>Placement candidate pool</h3>
        <FormMessage message={{ text: LOAD_FAILED, failed: true }} />
        <button className="btn small secondary" style={{ marginTop: 12 }} onClick={load}>
          Retry
        </button>
      </div>
    );
  if (!pool)
    return (
      <div className="action-card">
        <p className="muted">Loading your placement pool status…</p>
      </div>
    );

  return (
    <div className="action-card">
      {pool.opted_in ? (
        <>
          <span className="badge">In the placement pool</span>
          <h3 style={{ marginTop: 10 }}>Placement candidate pool</h3>
          <p className="muted" style={{ fontSize: 13 }}>
            EduSphere recruiters can contact you about jobs. Employers see your name, course, skills and availability, never your email or phone.
          </p>
          {confirming ? (
            <div role="group" aria-label="Confirm leaving the pool" style={{ marginTop: 12 }}>
              <p>Leave the pool? Employers will no longer find you; your applications continue.</p>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
                <button className="btn small" disabled={busy} onClick={() => change("opt-out", "You have left the placement candidate pool.")}>
                  {busy ? "Leaving…" : "Yes, leave"}
                </button>
                <button className="btn small secondary" disabled={busy} onClick={() => setConfirming(false)}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button className="btn small secondary" style={{ marginTop: 12 }} onClick={() => setConfirming(true)}>
              Leave the pool
            </button>
          )}
        </>
      ) : (
        <>
          <h3>Join the placement candidate pool</h3>
          <p style={{ marginTop: 8 }}>{pool.consent.text}</p>
          <p className="muted" style={{ fontSize: 13 }}>
            Version {pool.consent.version}
          </p>
          <label style={{ display: "flex", gap: 8, alignItems: "flex-start", marginTop: 12 }}>
            <input type="checkbox" checked={agreed} onChange={(event) => setAgreed(event.target.checked)} />
            <span>I agree to the consent text above</span>
          </label>
          <button className="btn small" style={{ marginTop: 12 }} disabled={!agreed || busy} onClick={() => change("opt-in", "You have joined the placement candidate pool.")}>
            {busy ? "Joining…" : "Join the pool"}
          </button>
        </>
      )}
      {message && <FormMessage message={message} style={{ marginTop: 8 }} />}
      {pool.history.length > 0 && (
        <ul className="muted" style={{ fontSize: 13, marginTop: 12, paddingLeft: 18 }} aria-label="Pool history">
          {pool.history.map((event) => (
            <li key={`${event.action}-${event.created_at}`}>
              {event.action === "opt_in" ? "Joined" : "Left"} · <LocalTime value={event.created_at} /> · consent {event.consent_version}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
