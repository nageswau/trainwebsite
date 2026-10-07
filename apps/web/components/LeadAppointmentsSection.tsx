"use client";

import { useEffect, useState } from "react";

import BookCounsellingForm from "@/components/BookCounsellingForm";
import LeadAppointmentCard from "@/components/LeadAppointmentCard";
import { CLOSED_STAGES } from "@/lib/leadStages";
import { OPEN_STATUSES, appointmentsUrl, type LeadAppointment } from "@/lib/leadAppointments";

const CLOSED = new Set<string>(CLOSED_STAGES.map(([key]) => key));

/** tel-016 (spec §4): the lead's counselling appointments on its detail page. The lead's telecaller books (AP2: never a manager, never
 *  on a handed-over or closed lead, never a second open one -- AP5, AP11) and may reschedule or cancel; a manager reads. Each change
 *  hands the lead's new stage back, so the page's stage line and activity follow (AC2, AP3). */
export default function LeadAppointmentsSection({ leadId, stage, canBook, onStage }: {
  leadId: string; stage: string; canBook: boolean; onStage: (status: string, label: string) => void;
}) {
  const [items, setItems] = useState<LeadAppointment[] | "failed" | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [booking, setBooking] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const closed = CLOSED.has(stage); // AP15: closing a lead cancels its open booking, so the list is re-read when the lead closes or reopens

  useEffect(() => {
    const controller = new AbortController();
    fetch(appointmentsUrl(leadId), { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Request failed (${response.status})`);
        setItems(((await response.json()) as { items: LeadAppointment[] }).items);
      })
      .catch(() => controller.signal.aborted || setItems("failed"));
    return () => controller.abort();
  }, [leadId, attempt, closed]);

  function changed(next: LeadAppointment) {
    setItems((list) => (Array.isArray(list) ? list.map((a) => (a.id === next.id ? next : a)) : list));
    onStage(next.lead.status, next.lead.status_label);
  }

  function booked(next: LeadAppointment) {
    setBooking(false);
    setItems((list) => [next, ...(Array.isArray(list) ? list : [])]);
    setNotice(`Appointment ${next.code} booked with ${next.counselor?.full_name ?? "the counselor"}.`);
    onStage(next.lead.status, next.lead.status_label);
  }

  const list = Array.isArray(items) ? items : [];
  const hasOpen = list.some((a) => OPEN_STATUSES.includes(a.status));
  const bookable = canBook && Array.isArray(items) && !hasOpen && !closed;
  let body: React.ReactNode;
  if (items === null) body = <p className="muted" role="status" style={{ fontSize: 13 }}>Loading appointments…</p>;
  else if (items === "failed") {
    body = (
      <p className="form-error" role="alert" style={{ fontSize: 13 }}>
        Unable to load the appointments. <button type="button" className="btn secondary small" onClick={() => { setItems(null); setAttempt((n) => n + 1); }}>Try again</button>
      </p>
    );
  } else if (items.length === 0) body = <p className="muted" style={{ fontSize: 13 }}>No counselling appointments yet.</p>;
  else body = <div style={{ display: "grid", gap: 8 }}>{items.map((a) => <LeadAppointmentCard key={a.id} appointment={a} showLead={false} onChanged={changed} />)}</div>;

  return (
    <section aria-labelledby="lead-appointments-heading" style={{ display: "grid", gap: 8 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id="lead-appointments-heading" style={{ margin: 0 }}>Counselling appointments</h3>
        {bookable && !booking && <button type="button" className="btn small" onClick={() => { setBooking(true); setNotice(null); }}>Book counselling</button>}
      </div>
      {canBook && hasOpen && <p className="muted" style={{ margin: 0, fontSize: 13 }}>This lead has an open appointment. Reschedule or cancel it to book another.</p>}
      {canBook && closed && <p className="muted" style={{ margin: 0, fontSize: 13 }}>This lead is closed. A manager can reopen it before a booking.</p>}
      {notice && <p className="form-message" role="status" style={{ margin: 0, fontSize: 13 }}>{notice}</p>}
      {booking && <BookCounsellingForm leadId={leadId} onBooked={booked} onCancel={() => setBooking(false)} />}
      {body}
    </section>
  );
}
