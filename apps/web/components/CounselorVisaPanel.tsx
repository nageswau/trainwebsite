"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import CounselorVisaCaseForm, { type VisaCaseView } from "@/components/CounselorVisaCaseForm";
import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { sendJson } from "@/lib/apiErrors";
import { visaStatusLabel } from "@/lib/visaStatus";

type ApplicationRow = { id: string; student: string; university: string };
type ChecklistItem = { item: string; verification_status: string };
type Checklist = Partial<VisaCaseView> & {
  exists: boolean;
  id?: string;
  status: string | null;
  checklist: ChecklistItem[];
  locked_reason?: string | null;
  template?: { name: string; items: string[] } | null;
};
type VisaStatus = { exists: boolean; disclaimer: string };

const DEFAULT_DISCLAIMER = "Visa decisions are made by the relevant government or immigration authority. EduSphere does not decide visa outcomes.";

// VISA-001: a Counselor previously had to type a raw application UUID (to start a case)
// or a raw visa-case UUID plus a free-typed status (to update one), with no visibility
// into which of their assigned applications already had a case or what its checklist
// items' real verification state was -- same class of gap already fixed for
// ADM-001/002/003/004/006/007. This lists the Counselor's own assigned applications,
// each with its checklist (if started) and, since ccrm-026, the case's Appendix A lifecycle form.
export default function CounselorVisaPanel() {
  const router = useRouter();
  const [applications, setApplications] = useState<ApplicationRow[] | null>(null);
  const [checklists, setChecklists] = useState<Record<string, Checklist>>({});
  const [statuses, setStatuses] = useState<Record<string, VisaStatus>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<(FormMessageState & { id: string }) | null>(null);

  function loadChecklist(applicationId: string) {
    fetch(`/api/v1/workflows/overseas/applications/${applicationId}/visa-checklist`)
      .then((res) => (res.ok ? res.json() : null))
      .then((checklist) => checklist && setChecklists((current) => ({ ...current, [applicationId]: checklist })));
    fetch(`/api/v1/workflows/overseas/applications/${applicationId}/visa-status`)
      .then((res) => (res.ok ? res.json() : null))
      .then((status) => status && setStatuses((current) => ({ ...current, [applicationId]: status })));
  }

  function load() {
    fetch("/api/v1/portal/overseas/counselor/applications")
      .then((res) => (res.ok ? res.json() : { rows: [] }))
      .then((data) => {
        const rows = (data.rows || []) as ApplicationRow[];
        setApplications(rows);
        rows.forEach((row) => loadChecklist(row.id));
      })
      .catch(() => setApplications([]));
  }

  useEffect(load, []);

  async function startCase(event: FormEvent<HTMLFormElement>, applicationId: string) {
    event.preventDefault();
    setBusyId(applicationId);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    const checklist = String(form.get("checklist") || "").split(",").map((s) => s.trim()).filter(Boolean);
    const result = await sendJson("/api/v1/workflows/overseas/visa", "POST", { application_id: applicationId, checklist });
    setBusyId(null);
    if (!result.ok) {
      setMessage({ id: applicationId, text: result.message, failed: true });
      return;
    }
    setMessage({ id: applicationId, text: "Visa case started.", failed: false });
    loadChecklist(applicationId);
    router.refresh();
  }

  function saved(applicationId: string) {
    loadChecklist(applicationId);
    router.refresh();
  }

  if (applications === null) {
    return (
      <div className="action-card">
        <h3>Visa Cases</h3>
        <p className="muted">Loading your assigned applications…</p>
      </div>
    );
  }

  if (applications.length === 0) {
    return (
      <div className="action-card">
        <h3>Visa Cases</h3>
        <p className="muted">No applications are assigned to you yet.</p>
      </div>
    );
  }

  const disclaimer = Object.values(statuses).find((s) => s.disclaimer)?.disclaimer || DEFAULT_DISCLAIMER;

  return (
    <div className="action-card">
      <h3>Visa Cases</h3>
      <div className="grid two" style={{ marginTop: 16 }}>
        {applications.map((row) => {
          const checklist = checklists[row.id];
          const verified = checklist?.checklist.filter((item) => item.verification_status === "verified").length ?? 0;
          return (
            <div className="card" key={row.id}>
              <h4>{row.student}</h4>
              <p className="muted" style={{ fontSize: 13 }}>{row.university}</p>
              {!checklist ? (
                <p className="muted" style={{ fontSize: 13 }}>Loading…</p>
              ) : !checklist.exists ? (
                <form className="form" onSubmit={(event) => startCase(event, row.id)}>
                  <div className="field">
                    <label htmlFor={`checklist-${row.id}`}>Checklist items (comma separated)</label>
                    {/* ccrm-026 (D5): pre-filled from the matching visa checklist template, still editable. */}
                    <input
                      id={`checklist-${row.id}`}
                      name="checklist"
                      placeholder="Passport, Offer letter, Financial evidence"
                      defaultValue={checklist.template?.items.join(", ") ?? ""}
                      required
                    />
                    {checklist.template && <span className="muted" style={{ fontSize: 13 }}>From the &ldquo;{checklist.template.name}&rdquo; visa checklist.</span>}
                  </div>
                  <button className="btn small" disabled={busyId === row.id}>
                    {busyId === row.id ? "Starting…" : "Start visa case"}
                  </button>
                </form>
              ) : (
                <>
                  <span className="badge">{visaStatusLabel(checklist.visa_status) || checklist.status}</span>
                  {checklist.tracking_reference && <p className="muted" style={{ fontSize: 13 }}>Reference: {checklist.tracking_reference}</p>}
                  {checklist.appointment_date && (
                    <p className="muted" style={{ fontSize: 13 }}>
                      Appointment: {checklist.appointment_date}
                      {checklist.appointment_place ? `, ${checklist.appointment_place}` : ""}
                    </p>
                  )}
                  {checklist.refusal_reason && <p className="muted" style={{ fontSize: 13 }}>Refusal reason (restricted): {checklist.refusal_reason}</p>}
                  {checklist.checklist.length > 0 && (
                    <p style={{ fontSize: 13, marginTop: 8 }}>
                      Checklist: {verified} of {checklist.checklist.length} verified
                    </p>
                  )}
                  <ul className="list-clean">
                    {checklist.checklist.map((item) => (
                      <li key={item.item}>{item.item} — <span className="muted">{item.verification_status.replaceAll("_", " ")}</span></li>
                    ))}
                  </ul>
                  {/* AGN-023 (DEC-SCOPE-090 H12): a decided or enrolled agency case offers no change; the server would refuse it. */}
                  {checklist.locked_reason ? (
                    <p className="muted" style={{ fontSize: 13 }}>{checklist.locked_reason}</p>
                  ) : (
                    checklist.visa_status && <CounselorVisaCaseForm key={checklist.id} visa={checklist as VisaCaseView} onSaved={() => saved(row.id)} />
                  )}
                </>
              )}
              {message?.id === row.id && <FormMessage message={message} style={{ marginTop: 8, fontSize: 13 }} />}
            </div>
          );
        })}
      </div>
      <p className="muted" style={{ marginTop: 16, fontSize: 13 }}>{disclaimer}</p>
    </div>
  );
}
