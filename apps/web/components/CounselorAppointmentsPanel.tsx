"use client";

import { useEffect, useId, useState } from "react";

import LeadAppointmentCard from "@/components/LeadAppointmentCard";
import { isPage, type Page } from "@/lib/apiErrors";
import { COUNSELOR_APPOINTMENTS_URL, STATUS_LABEL, type AppointmentStatus, type LeadAppointment } from "@/lib/leadAppointments";

const PAGE_SIZE = 20;

/** tel-016 (spec §4; AP2, AP13, AP14): the counselor's lead appointments -- open ones first, soonest first -- with Confirm, Complete,
 *  No-show, Reschedule and Cancel as `permissions` allow. Filtered by status, 20 a page. */
export default function CounselorAppointmentsPanel() {
  const idp = useId();
  const [status, setStatus] = useState<AppointmentStatus | "">("");
  const [page, setPage] = useState<Page<LeadAppointment> | "failed" | null>(null);
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset), ...(status ? { status } : {}) });
    fetch(`${COUNSELOR_APPOINTMENTS_URL}?${query}`, { signal: controller.signal })
      .then(async (response) => {
        const data = response.ok ? await response.json() : null;
        if (!isPage<LeadAppointment>(data)) throw new Error(`Request failed (${response.status})`);
        setPage(data);
      })
      .catch(() => controller.signal.aborted || setPage("failed"));
    return () => controller.abort();
  }, [status, offset, attempt]);

  const changed = (next: LeadAppointment) =>
    setPage((p) => (p && p !== "failed" ? { ...p, items: p.items.map((a) => (a.id === next.id ? next : a)) } : p));

  let body: React.ReactNode;
  if (page === null) body = <p className="muted" role="status">Loading appointments…</p>;
  else if (page === "failed") {
    body = (
      <p className="form-error" role="alert">
        Unable to load your appointments. <button type="button" className="btn secondary small" onClick={() => { setPage(null); setAttempt((n) => n + 1); }}>Try again</button>
      </p>
    );
  } else if (page.items.length === 0) {
    body = <p className="muted">{status ? `No ${STATUS_LABEL[status].toLowerCase()} lead appointments.` : "No lead appointments booked with you yet."}</p>;
  } else {
    body = (
      <>
        <div style={{ display: "grid", gap: 8 }}>{page.items.map((a) => <LeadAppointmentCard key={a.id} appointment={a} showLead onChanged={changed} />)}</div>
        <nav aria-label="Appointment pages" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <span className="muted" style={{ fontSize: 13 }}>{page.offset + 1}–{page.offset + page.items.length} of {page.total}</span>
          {page.offset > 0 && <button type="button" className="btn secondary small" onClick={() => setOffset(Math.max(0, page.offset - PAGE_SIZE))}>Previous</button>}
          {page.offset + page.items.length < page.total && <button type="button" className="btn secondary small" onClick={() => setOffset(page.offset + PAGE_SIZE)}>Next</button>}
        </nav>
      </>
    );
  }
  return (
    <section aria-labelledby={`${idp}-heading`} className="portal-content" style={{ display: "grid", gap: 12 }}>
      <div className="portal-title">
        <div>
          <div className="eyebrow">Appointments</div>
          <h2 id={`${idp}-heading`}>Lead appointments</h2>
          <p className="muted">Counselling sessions telecallers booked with you for leads. Confirm them, then mark each one completed or a no-show.</p>
        </div>
      </div>
      <div className="field" style={{ maxWidth: "16rem" }}>
        <label htmlFor={`${idp}-status`}>Status</label>
        <select id={`${idp}-status`} value={status} onChange={(e) => { setStatus(e.target.value as AppointmentStatus | ""); setOffset(0); setPage(null); }}>
          <option value="">All statuses</option>
          {(Object.keys(STATUS_LABEL) as AppointmentStatus[]).map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
        </select>
      </div>
      {body}
    </section>
  );
}
