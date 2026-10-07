"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useId, useState } from "react";

import BdmAppointmentForm from "@/components/BdmAppointmentForm";
import type { BdmType } from "@/lib/bdm";
import { isoToIstInput } from "@/lib/bdmAppointments";
import type { Organization } from "@/lib/bdmOrganizations";
import type { TripRow } from "@/lib/bdmTravel";
import { sendJson } from "@/lib/apiErrors";
import { acceptUrl, APPOINTMENT_TYPE_FOR, declineUrl, type MeetingRequest } from "@/lib/meetingRequests";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const REASON_MAX = 500;

/** tel-019 (AC2, AC3, MR9): a BDM accepts a pending request by booking it (bdm-006's own form, started from the request) or declines it
 *  with a reason. Rendered only when the API says the caller may decide. */
export default function MeetingRequestDecide({ request, bdmType, initialOrganization, trips, tripsUnavailable }: {
  request: MeetingRequest; bdmType: BdmType; initialOrganization: Organization | null; trips?: TripRow[]; tripsUnavailable?: boolean;
}) {
  const router = useRouter();
  const idp = useId();
  const focus = useFocusAfterRender();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!request.permissions.can_accept && !request.permissions.can_decline) return null;

  const passed = new Date(request.proposed_at).getTime() <= Date.now(); // the edge case: the BDM picks a new time
  const prefill = {
    when: passed ? "" : isoToIstInput(request.proposed_at), type: APPOINTMENT_TYPE_FOR[request.request_type],
    location: request.location ?? "", purpose: request.purpose, remarks: request.remarks ?? "",
  };

  async function decline(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim()) {
      setError("Enter the reason for declining.");
      return focus(`${idp}-reason`);
    }
    setError(null);
    setBusy(true);
    const outcome = await sendJson(declineUrl(request.id), "POST", { reason: reason.trim() });
    setBusy(false);
    if (!outcome.ok) {
      setError((outcome.status ?? 0) >= 500 ? "We couldn't decline the request. Please try again." : outcome.message);
      return focus(`${idp}-reason`);
    }
    router.refresh();
  }

  return (
    <>
      {request.permissions.can_accept && (
        <section className="action-card wide" aria-labelledby={`${idp}-accept`}>
          <h3 id={`${idp}-accept`}>Accept and book</h3>
          <p className="muted">
            Choose one of your organizations and a contact; the appointment is booked when you accept.
            {passed && " The proposed time has passed — choose a new time."} Times are India time (IST).
          </p>
          <BdmAppointmentForm mode="create" bdmType={bdmType} initialOrganization={initialOrganization}
            request={{ acceptUrl: acceptUrl(request.id), prefill }} trips={trips} tripsUnavailable={tripsUnavailable} />
        </section>
      )}
      {request.permissions.can_decline && (
        <section className="action-card wide" aria-labelledby={`${idp}-decline`}>
          <h3 id={`${idp}-decline`}>Decline</h3>
          <form onSubmit={decline} noValidate style={{ display: "grid", gap: 8 }}>
            <div className="field">
              <label htmlFor={`${idp}-reason`}>Reason for declining</label>
              <textarea id={`${idp}-reason`} rows={2} maxLength={REASON_MAX} value={reason} disabled={busy} aria-required
                onChange={(e) => { setReason(e.target.value); setError(null); }}
                {...(error ? { "aria-invalid": true as const, "aria-describedby": `${idp}-reason-error` } : {})} />
              {error && <p id={`${idp}-reason-error`} className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
            </div>
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>The telecaller sees your reason. A declined request can&apos;t be reopened.</p>
            <div className="actions">
              <button type="submit" className="btn secondary" disabled={busy}>{busy ? "Declining…" : "Decline request"}</button>
            </div>
          </form>
        </section>
      )}
    </>
  );
}
