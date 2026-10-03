"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import FormMessage from "@/components/FormMessage";
import TripActions from "@/components/TripActions";
import TripDecision from "@/components/TripDecision";
import TripDetails from "@/components/TripDetails";
import TripExpenses from "@/components/TripExpenses";
import TripForm from "@/components/TripForm";
import TripRemarks from "@/components/TripRemarks";
import TripStatusBadges from "@/components/TripStatusBadges";
import { teamTripUrl, tripUrl, type Trip } from "@/lib/bdmTravel";
import { refocus } from "@/lib/focus";
import { TripLiveContext, isTrip, type TripLive } from "@/lib/tripLive";
import { WRITE_STARTED } from "@/lib/useTripWrite";

const NOTICE_ID = "trip-notice";

// bdm-010 (QA10-16): one trip page as one client workspace. The server page reads the trip once; every write below applies the
// trip it returns (useTripWrite + TripLiveContext), and a 409 re-reads it -- so two quick saves can never leave a stale render on
// screen. `view` "owner" is the BDM's own trip (actions, editor while draft/rejected, expenses, remarks); "manager" is the
// read-only team view with Approve/Reject when the API says this caller decides (`note` explains when it can't, QA10-13).
export default function TripWorkspace({ initialTrip, view, today, backHref, backLabel, note }: {
  initialTrip: Trip; view: "owner" | "manager"; today: string; backHref: string; backLabel: string; note?: string;
}) {
  const [trip, setTrip] = useState(initialTrip);
  const [notice, setNotice] = useState<string | null>(null); // why the last write was refused, shown once at the top
  const owner = view === "owner";
  const live = useMemo<TripLive>(() => ({
    apply: (next) => {
      setTrip(next);
      setNotice(null);
    },
    reload: async (reason) => {
      setNotice(reason);
      try {
        const response = await fetch(owner ? tripUrl(initialTrip.id) : teamTripUrl(initialTrip.id));
        const data = await response.json().catch(() => null);
        if (response.ok && isTrip(data)) setTrip(data);
      } catch {
        // the notice already says what was refused; the page keeps what it last knew
      }
      refocus(NOTICE_ID);
    },
  }), [owner, initialTrip.id]);
  useEffect(() => {
    const clear = () => setNotice(null); // a new write supersedes the old reason (QA10-09)
    window.addEventListener(WRITE_STARTED, clear);
    return () => window.removeEventListener(WRITE_STARTED, clear);
  }, []);

  return (
    <TripLiveContext.Provider value={live}>
      <div className="portal-title">
        <div>
          <div className="eyebrow">Travel · {trip.code}{owner ? "" : ` · ${trip.bdm.full_name}`}</div>
          <h2 style={{ overflowWrap: "anywhere" }}>{trip.from_place} → {trip.to_place}</h2>
          <p><TripStatusBadges trip={trip} /></p>
        </div>
        <Link className="btn secondary" href={backHref}>{backLabel}</Link>
      </div>
      <div id={NOTICE_ID} tabIndex={-1}>{notice && <FormMessage message={{ text: notice, failed: true }} style={{ marginBottom: 16 }} />}</div>
      {owner && trip.rejection_reason && (
        <div className="form-warning" role="note" style={{ marginBottom: 16 }}>
          <strong>Not approved.</strong> <span style={{ whiteSpace: "pre-wrap" }}>{trip.rejection_reason}</span> Edit the trip and submit it again.
        </div>
      )}
      {owner ? <TripActions trip={trip} /> : <TripDecision trip={trip} />}
      {!owner && note && <p className="muted" role="note" style={{ marginTop: 12 }}>{note}</p>}
      {!owner && trip.rejection_reason && (
        <div className="form-warning" role="note" style={{ marginTop: 16 }}>
          <strong>Reason given:</strong> <span style={{ whiteSpace: "pre-wrap" }}>{trip.rejection_reason}</span>
        </div>
      )}
      <section className="card" aria-labelledby="trip-details-heading" style={{ marginTop: 20 }}>
        <h3 id="trip-details-heading">Trip details</h3>
        <TripDetails trip={trip} />
      </section>
      {owner && trip.can_edit && (
        <section className="card" aria-labelledby="trip-edit-heading" style={{ marginTop: 20 }}>
          <h3 id="trip-edit-heading">Edit trip</h3>
          <TripForm trip={trip} today={today} />
        </section>
      )}
      <section className="card" aria-labelledby="trip-costs-heading" style={{ marginTop: 20 }}>
        <h3 id="trip-costs-heading">Costs and expenses</h3>
        <TripExpenses trip={trip} ownerView={owner} />
      </section>
      {(owner || trip.remarks) && (
        <section className="card" aria-labelledby="trip-remarks-heading" style={{ marginTop: 20 }}>
          <h3 id="trip-remarks-heading">Remarks</h3>
          {owner ? <TripRemarks trip={trip} /> : <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{trip.remarks}</p>}
        </section>
      )}
    </TripLiveContext.Provider>
  );
}
