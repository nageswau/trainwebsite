"use client";

import { useState } from "react";

import FormMessage from "@/components/FormMessage";
import { tripUrl, type Trip } from "@/lib/bdmTravel";
import { useHydrated } from "@/lib/useHydrated";
import { jsonInit, useTripWrite } from "@/lib/useTripWrite";

const MAX = 2000;

// bdm-010: remarks stay editable in every state, including after completion (the travel reminder's "Add Remarks"); each save
// is audited by the API. A blank box clears them.
export default function TripRemarks({ trip }: { trip: Trip }) {
  const [value, setValue] = useState(trip.remarks ?? "");
  const { busy, message, run, resultProps } = useTripWrite();
  const ready = useHydrated(); // QA10-17: this box is server-rendered too
  return (
    <form className="form" onSubmit={(e) => { e.preventDefault(); run(tripUrl(trip.id), jsonInit("PATCH", { remarks: value.trim() || null }), "Remarks saved."); }}>
      <fieldset disabled={!ready} className="form" style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
      <div className="field">
        {/* QA10-14: the section heading already says "Remarks" on screen; the field keeps the name for assistive tech */}
        <label htmlFor="trip-remarks-edit" className="visually-hidden">Remarks</label>
        <textarea id="trip-remarks-edit" rows={3} maxLength={MAX} value={value} onChange={(e) => setValue(e.target.value)} aria-describedby="trip-remarks-count" />
        <p className="muted" id="trip-remarks-count" style={{ fontSize: 12, margin: 0 }}>{value.length} / {MAX}</p>
      </div>
      <div className="actions">
        <button className="btn secondary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save remarks"}</button>
      </div>
      </fieldset>
      <div {...resultProps}>{message && <FormMessage message={message} />}</div>
    </form>
  );
}
