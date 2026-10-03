"use client";

import { useState } from "react";

import FormMessage from "@/components/FormMessage";
import { tripUrl, type Trip } from "@/lib/bdmTravel";
import { refocus } from "@/lib/focus";
import { useTripWrite } from "@/lib/useTripWrite";

type Flag = "can_submit" | "can_withdraw" | "can_start" | "can_complete";
const ACTIONS: { action: string; flag: Flag; label: string; done: string }[] = [
  { action: "submit", flag: "can_submit", label: "Submit for approval", done: "Submitted for approval." },
  { action: "withdraw", flag: "can_withdraw", label: "Withdraw", done: "Withdrawn to draft." },
  { action: "start", flag: "can_start", label: "Start trip", done: "Trip started." },
  { action: "complete", flag: "can_complete", label: "Mark completed", done: "Trip completed." },
];
const CANCEL_ID = "trip-cancel";

// bdm-010: the owner's commands. Only the actions the API's `can_*` flags allow are shown; the API still decides (S2).
// Cancel is confirmed inline (the TierDowngradeConfirm idiom, no dialog library); Escape backs out and returns focus.
export default function TripActions({ trip }: { trip: Trip }) {
  const { busy, message, run, resultProps } = useTripWrite();
  const [confirming, setConfirming] = useState(false);
  const shown = ACTIONS.filter((a) => trip[a.flag]);
  if (!shown.length && !trip.can_cancel && !message) return null;

  const post = (action: string, done: string) => run(`${tripUrl(trip.id)}/${action}`, { method: "POST" }, done);
  const closeConfirm = () => {
    setConfirming(false);
    refocus(CANCEL_ID);
  };

  return (
    <div>
      <div className="actions">
        {shown.map((a) => (
          <button key={a.action} type="button" className={a.action === "withdraw" ? "btn secondary" : "btn"} disabled={busy} onClick={() => post(a.action, a.done)}>
            {a.label}
          </button>
        ))}
        {trip.can_cancel && !confirming && (
          <button id={CANCEL_ID} type="button" className="btn ghost" disabled={busy} onClick={() => setConfirming(true)}>Cancel trip</button>
        )}
      </div>
      {confirming && (
        <div className="form-warning" role="group" aria-labelledby="trip-cancel-title" style={{ marginTop: 12 }}
          onKeyDown={(e) => { if (e.key === "Escape" && !busy) closeConfirm(); }}>
          <p id="trip-cancel-title"><strong>Cancel {trip.code}?</strong> A cancelled trip can&apos;t be restarted. Expenses already added stay on it.</p>
          <div className="actions">
            <button autoFocus type="button" className="btn" disabled={busy} onClick={async () => { await post("cancel", "Trip cancelled."); setConfirming(false); }}>
              {busy ? "Saving…" : "Confirm cancel"}
            </button>
            <button type="button" className="btn secondary" disabled={busy} onClick={closeConfirm}>Keep trip</button>
          </div>
        </div>
      )}
      <div {...resultProps}>{message && <FormMessage message={message} style={{ marginTop: 12 }} />}</div>
    </div>
  );
}
