"use client";
import Link from "next/link";
import { type FormEvent, useEffect, useId, useState } from "react";

import LocalTime from "@/components/LocalTime";
import RecruiterApplicationInterviews from "@/components/RecruiterApplicationInterviews";
import RecruiterApplicationOffer from "@/components/RecruiterApplicationOffer";
import RecruiterApplicationScreening from "@/components/RecruiterApplicationScreening";
import type { ContactOption } from "@/components/RecruiterInterviewForm";
import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import type { PickOption } from "@/lib/lookups";
import {
  applicationUrl,
  candidateSearch,
  type HistoryEntry,
  isApplicationBody,
  isHistory,
  isRequirementCandidates,
  NOTE_MAX,
  type RecApplication,
  requirementCandidatesUrl,
  type RequirementCandidates,
} from "@/lib/recruiterApplications";
import { CANDIDATES_PATH } from "@/lib/recruiterCandidates";
import { contactsOf, isContactList } from "@/lib/recruiterContacts";

type Notice = { text: string; failed: boolean } | null;
const search = candidateSearch();

function NoteField({ id, value, onChange }: { id: string; value: string; onChange: (v: string) => void }) {
  return (
    <label htmlFor={id} style={{ display: "grid", gap: 4 }}>
      Note (optional)
      <textarea id={id} rows={2} maxLength={NOTE_MAX} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

/** Add one pool candidate at Sourced / Screened / Shortlisted. A duplicate or a closed requirement comes back as the API's message. */
function AddCandidate({ requirementId, data, onAdded, onCancel }: {
  requirementId: string; data: RequirementCandidates; onAdded: (a: RecApplication) => void; onCancel: () => void;
}) {
  const [picked, setPicked] = useState<PickOption | null>(null);
  const [status, setStatus] = useState("sourced");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const id = useId();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!picked || busy) return;
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(requirementCandidatesUrl(requirementId), "POST", { candidate_id: picked.id, status, ...(note.trim() ? { note: note.trim() } : {}) });
    setBusy(false);
    if (outcome.ok && isApplicationBody(outcome.data)) onAdded(outcome.data.application);
    else setFailure(outcome.ok ? "Unable to add the candidate." : outcome.message);
  }

  return (
    <form onSubmit={submit} className="action-card" style={{ gap: 10 }} aria-label="Add candidate">
      <SearchableSelect label="Candidate" noun="candidate" required search={search} onChange={setPicked} />
      <label htmlFor={`${id}-status`} style={{ display: "grid", gap: 4 }}>
        Starting status
        <select id={`${id}-status`} value={status} onChange={(e) => setStatus(e.target.value)}>
          {data.statuses.filter((s) => s.initial).map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
      </label>
      <NoteField id={`${id}-note`} value={note} onChange={setNote} />
      {failure && <p className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy || !picked}>{busy ? "Adding…" : "Add candidate"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

/** The application's status changes, newest first, read when opened. */
function History({ applicationId }: { applicationId: string }) {
  const [items, setItems] = useState<HistoryEntry[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch(applicationUrl(applicationId, "/history"), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => (isHistory(body) ? setItems(body.items) : setFailed(true)))
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [applicationId]);
  if (failed) return <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>Unable to load the history.</p>;
  if (items === null) return <p className="muted" role="status" style={{ margin: 0, fontSize: 13 }}>Loading history…</p>;
  return (
    <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
      {items.map((h, i) => (
        <li key={`${h.created_at}-${i}`}>
          <LocalTime value={h.created_at} time />: {h.from_label ? `${h.from_label} → ${h.to_label}` : `Added as ${h.to_label}`}
          {h.note && <> — <span style={{ overflowWrap: "anywhere" }}>{h.note}</span></>} <span className="muted">by {h.changed_by ? h.changed_by.full_name : "the system"}</span>
        </li>
      ))}
    </ul>
  );
}

function StatusForm({ application, onChanged, onCancel }: { application: RecApplication; onChanged: (a: RecApplication) => void; onCancel: () => void }) {
  const [status, setStatus] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const id = useId();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!status || busy) return;
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(applicationUrl(application.id, "/status"), "POST", { status, ...(note.trim() ? { note: note.trim() } : {}) });
    setBusy(false);
    if (outcome.ok && isApplicationBody(outcome.data)) onChanged(outcome.data.application);
    else setFailure(outcome.ok ? "Unable to change the status." : outcome.message);
  }

  return (
    <form onSubmit={submit} style={{ display: "grid", gap: 8 }} aria-label={`Change status of ${application.candidate.name}`}>
      <label htmlFor={`${id}-status`} style={{ display: "grid", gap: 4 }}>
        New status
        <select id={`${id}-status`} required value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Choose a status</option>
          {application.allowed_statuses.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
      </label>
      <NoteField id={`${id}-note`} value={note} onChange={setNote} />
      {failure && <p className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy || !status}>{busy ? "Saving…" : "Save status"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

/** One candidate as a stacked item (the rec-025 Calls pattern), so the status and actions stay on screen at phone width (QA-03). */
type Panel = "none" | "status" | "history" | "interviews" | "screening" | "offer";

function ApplicationItem({ application, contacts, onChanged, onInterview, onScreened }: {
  application: RecApplication; contacts: ContactOption[]; onChanged: (a: RecApplication) => void; onInterview: (notice: string) => void;
  onScreened: (a: RecApplication) => void;
}) {
  const [open, setOpen] = useState<Panel>("none");
  const toggle = (panel: Exclude<Panel, "none">) => setOpen((current) => (current === panel ? "none" : panel));
  const id = useId();
  return (
    <li className="action-card" style={{ listStyle: "none", gap: 6 }} aria-labelledby={`${id}-name`}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <Link id={`${id}-name`} href={`${CANDIDATES_PATH}/${application.candidate.id}`} style={{ ...LINK_STYLE, fontWeight: 600, overflowWrap: "anywhere" }}>
          {application.candidate.name}
        </Link>
        <span className="badge">{application.status_label}</span>
        {application.screening_result && <span className="badge">Screening: {application.screening_result.label}</span>}
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        {application.candidate.code} · since <LocalTime value={application.stage_changed_at} time />
      </p>
      <div className="actions" style={{ flexWrap: "wrap" }}>
        {application.allowed_statuses.length > 0 && (
          <button type="button" className="btn secondary small" aria-expanded={open === "status"} onClick={() => toggle("status")}>
            Change status<span className="visually-hidden"> of {application.candidate.name}</span>
          </button>
        )}
        <button type="button" className="btn secondary small" aria-expanded={open === "history"} onClick={() => toggle("history")}>
          History<span className="visually-hidden"> of {application.candidate.name}</span>
        </button>
        <button type="button" className="btn secondary small" aria-expanded={open === "interviews"} onClick={() => toggle("interviews")}>
          Interviews<span className="visually-hidden"> of {application.candidate.name}</span>
        </button>
        <button type="button" className="btn secondary small" aria-expanded={open === "screening"} onClick={() => toggle("screening")}>
          Screening<span className="visually-hidden"> of {application.candidate.name}</span>
        </button>
        <button type="button" className="btn secondary small" aria-expanded={open === "offer"} onClick={() => toggle("offer")}>
          Offer<span className="visually-hidden"> of {application.candidate.name}</span>
        </button>
      </div>
      {open === "status" && <StatusForm application={application} onCancel={() => setOpen("none")} onChanged={(next) => { setOpen("none"); onChanged(next); }} />}
      {open === "history" && <History applicationId={application.id} />}
      {open === "interviews" && (
        <RecruiterApplicationInterviews applicationId={application.id} candidateName={application.candidate.name} contacts={contacts} onChanged={onInterview} />
      )}
      {open === "screening" && (
        <RecruiterApplicationScreening applicationId={application.id} candidateName={application.candidate.name} onCancel={() => setOpen("none")}
          onSaved={(next) => { setOpen("none"); onScreened(next); }} />
      )}
      {open === "offer" && <RecruiterApplicationOffer applicationId={application.id} candidateName={application.candidate.name} onChanged={onInterview} />}
    </li>
  );
}

/** rec-017 (spec §5): the requirement's candidates and each one's §12 status. Writers (the requirement's recruiter, super_admin) add
 *  pool candidates and move statuses; managers and the assigned BDM read. Every write re-reads the list. rec-020: each row opens its
 *  interviews; the company's active contacts (when the caller can read them) feed the interview form. */
export default function RecruiterRequirementCandidates({ requirementId, companyId }: { requirementId: string; companyId?: string }) {
  const [data, setData] = useState<RequirementCandidates | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const headingId = `${useId()}-candidates`;
  const reload = () => setVersion((n) => n + 1);
  const [contacts, setContacts] = useState<ContactOption[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(requirementCandidatesUrl(requirementId), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => (isRequirementCandidates(body) ? setData(body) : setFailed(true)))
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [requirementId, version]);

  const canWrite = !!data && (data.can_add || data.items.some((a) => a.allowed_statuses.length > 0));
  useEffect(() => {
    if (!companyId || !canWrite) return;
    const controller = new AbortController();
    fetch(contactsOf(companyId), { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => isContactList(body) && setContacts(body.items.filter((c) => c.active).map((c) => ({ id: c.id, name: c.name }))))
      .catch(() => undefined); // contacts are optional: without them the form still schedules an interview
    return () => controller.abort();
  }, [companyId, canWrite]);

  const done = (text: string) => {
    setNotice({ text, failed: false });
    reload();
  };
  return (
    <section className="action-card wide" aria-labelledby={headingId}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id={headingId} style={{ margin: 0 }}>Candidates{data ? ` (${data.items.length})` : ""}</h3>
        {data?.can_add && !adding && (
          <button type="button" className="btn secondary small" onClick={() => { setAdding(true); setNotice(null); }}>Add candidate</button>
        )}
      </div>
      <div role="status" aria-live="polite">
        {notice && <p className={notice.failed ? "form-error" : "form-message"} style={{ margin: "6px 0 0", fontSize: 13 }}>{notice.text}</p>}
      </div>
      {adding && data?.can_add && (
        <AddCandidate requirementId={requirementId} data={data} onCancel={() => setAdding(false)}
          onAdded={(a) => { setAdding(false); done(`${a.candidate.name} added as ${a.status_label}.`); }} />
      )}
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the candidates.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading candidates…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ fontSize: 13, margin: 0 }}>No candidates on this requirement yet.</p>
      ) : (
        <ul aria-label="Candidates on this requirement" style={{ padding: 0, margin: "8px 0 0", display: "grid", gap: 8 }}>
          {data.items.map((application) => (
            <ApplicationItem key={application.id} application={application} contacts={contacts} onInterview={done}
              onChanged={(a) => done(`${a.candidate.name} is now ${a.status_label}.`)}
              onScreened={(a) => done(`Screening saved — ${a.candidate.name} is now ${a.status_label}.`)} />
          ))}
        </ul>
      )}
    </section>
  );
}
