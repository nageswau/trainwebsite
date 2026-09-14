"use client";

import { useEffect, useState } from "react";

type ApplicationRow = { id: string; university: string; status: string };
type ChecklistItem = { item: string; verification_status: string };
type Checklist = { exists: boolean; status: string | null; checklist: ChecklistItem[]; appointment_date: string | null; tracking_reference: string | null };
type VisaStatus = { exists: boolean; status: string | null; appointment_date: string | null; tracking_reference: string | null; disclaimer: string };
type InterviewPrep = { application_id: string; university: string; country: string; available: boolean; content: string | null };

const DEFAULT_DISCLAIMER = "Visa decisions are made by the relevant government or immigration authority. EduSphere does not decide visa outcomes.";

// VISA-001: "Student completes checklist; status tracked." No student-facing view of
// this existed at all -- both backend endpoints were Counselor/Admin-only writes. This
// lists the student's own applications and, for each, its visa checklist merged with
// each item's real document verification status -- viewable even while items are still
// unverified (VISA-001-AC02); only *advancing* past the checklist stage is gated,
// enforced server-side, not hidden here.
//
// VISA-003: also surfaces each case's overall status/appointment/tracking reference via
// the dedicated `GET .../visa-status` endpoint, and its compliance disclaimer
// (VISA-003-AC02) -- sourced from the API response, not invented here.
//
// VISA-002: also surfaces interview-prep material via the dedicated, Self-only
// `GET /overseas/visa/interview-prep` (not per-application, unlike its siblings above --
// fetched once and matched to each application by `application_id`). A country with no
// prep content yet shows an honest "not published for <country> yet" message
// (VISA-002-AC02), never a fabricated placeholder.
export default function VisaChecklistPanel() {
  const [applications, setApplications] = useState<ApplicationRow[] | null>(null);
  const [checklists, setChecklists] = useState<Record<string, Checklist>>({});
  const [statuses, setStatuses] = useState<Record<string, VisaStatus>>({});
  const [prepByApplication, setPrepByApplication] = useState<Record<string, InterviewPrep>>({});

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/portal/overseas/student/applications")
      .then((res) => (res.ok ? res.json() : { rows: [] }))
      .then((data) => {
        if (cancelled) return;
        const rows = (data.rows || []) as ApplicationRow[];
        setApplications(rows);
        rows.forEach((row) => {
          fetch(`/api/v1/workflows/overseas/applications/${row.id}/visa-checklist`)
            .then((res) => (res.ok ? res.json() : null))
            .then((checklist) => !cancelled && checklist && setChecklists((current) => ({ ...current, [row.id]: checklist })));
          fetch(`/api/v1/workflows/overseas/applications/${row.id}/visa-status`)
            .then((res) => (res.ok ? res.json() : null))
            .then((status) => !cancelled && status && setStatuses((current) => ({ ...current, [row.id]: status })));
        });
      })
      .catch(() => !cancelled && setApplications([]));
    fetch("/api/v1/workflows/overseas/visa/interview-prep")
      .then((res) => (res.ok ? res.json() : []))
      .then((rows: InterviewPrep[]) => {
        if (cancelled) return;
        const byApplication: Record<string, InterviewPrep> = {};
        rows.forEach((row) => { byApplication[row.application_id] = row; });
        setPrepByApplication(byApplication);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  if (applications === null) {
    return (
      <div className="action-card">
        <h3>Visa Checklist</h3>
        <p className="muted">Loading your applications…</p>
      </div>
    );
  }

  if (applications.length === 0) {
    return (
      <div className="action-card">
        <h3>Visa Checklist</h3>
        <p className="muted">Apply to a university first -- your visa checklist appears here once your counselor starts one.</p>
      </div>
    );
  }

  const disclaimer = Object.values(statuses).find((s) => s.disclaimer)?.disclaimer || DEFAULT_DISCLAIMER;

  return (
    <div className="action-card">
      <h3>Visa Checklist</h3>
      <div className="grid two" style={{ marginTop: 16 }}>
        {applications.map((row) => {
          const checklist = checklists[row.id];
          const status = statuses[row.id];
          const prep = prepByApplication[row.id];
          return (
            <div className="card" key={row.id}>
              <h4>{row.university}</h4>
              {!checklist ? (
                <p className="muted" style={{ fontSize: 13 }}>Loading…</p>
              ) : !checklist.exists ? (
                <p className="muted" style={{ fontSize: 13 }}>No visa case has been started yet for this application.</p>
              ) : (
                <>
                  <span className="badge">{checklist.status?.replaceAll("_", " ")}</span>
                  {status?.tracking_reference && <p className="muted" style={{ fontSize: 13 }}>Tracking reference: {status.tracking_reference}</p>}
                  {status?.appointment_date && <p className="muted" style={{ fontSize: 13 }}>Appointment: {status.appointment_date}</p>}
                  <ul className="list-clean" style={{ marginTop: 10 }}>
                    {checklist.checklist.map((item) => (
                      <li key={item.item}>
                        {item.item} — <span className="muted">{item.verification_status.replaceAll("_", " ")}</span>
                      </li>
                    ))}
                  </ul>
                  {prep && (
                    <div style={{ marginTop: 10 }}>
                      <strong style={{ fontSize: 13 }}>Interview preparation</strong>
                      {prep.available ? (
                        <p className="muted" style={{ fontSize: 13 }}>{prep.content}</p>
                      ) : (
                        <p className="muted" style={{ fontSize: 13 }}>Interview preparation material has not been published for {prep.country} yet.</p>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>
      <p className="muted" style={{ marginTop: 16, fontSize: 13 }}>{disclaimer}</p>
    </div>
  );
}
