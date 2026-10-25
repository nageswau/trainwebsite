"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { LeadStageControl } from "@/components/AdminLeadStage";
import BdmConfirm from "@/components/BdmConfirm";
import LeadContactFields, { contactChanges, contactDraft, contactRows } from "@/components/LeadContactFields";
import LeadFollowUps from "@/components/LeadFollowUps";
import LocalTime from "@/components/LocalTime";
import LeadMilestones from "@/components/LeadMilestones";
import LeadNotes from "@/components/LeadNotes";
import LeadQualificationForm from "@/components/LeadQualificationForm";
import LeadTimeline from "@/components/LeadTimeline";
import { staffFailure } from "@/lib/agentStaff";
import { isRequestBody, sendJson, sendRequest, type SendOutcome } from "@/lib/apiErrors";
import { formatCalendarDate } from "@/lib/formatDate";
import { counselorLeadUrl, counselorMoveStage, type CounselorLeadDetail as Detail, type StudentSuggestion } from "@/lib/leadHandover";
import { counselorTargets, stageLabel } from "@/lib/leadStages";
import { SOURCE_LABEL } from "@/lib/telecallerCatalogue";
import { counselorFollowUpApi } from "@/lib/telecallerFollowUps";

type Notice = { text: string; failed: boolean } | null;

function NoticeLine({ notice }: { notice: Notice }) {
  if (!notice) return null;
  return <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: "6px 0 0", fontSize: 13 }}>{notice.text}</p>;
}

const show = (value: string | number | null | undefined, empty = "—") => (value === null || value === undefined || value === "" ? <span className="muted">{empty}</span> : value);

/** ccrm-005 (LF7): the counselor's edit of the spec §3 contact, consent and referral fields -- changes only; the API answers with the lead. */
function ContactForm({ lead, onSaved, onCancel }: { lead: Detail; onSaved: (lead: Detail) => void; onCancel: () => void }) {
  const [values, setValues] = useState(contactDraft(lead));
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);

  async function save(event: FormEvent) {
    event.preventDefault();
    const changes = contactChanges(values, lead);
    if (Object.keys(changes).length === 0) return onCancel();
    setBusy(true);
    const outcome = await sendJson(counselorLeadUrl(lead.id), "PATCH", changes);
    setBusy(false);
    if (!outcome.ok || !isRequestBody(outcome.data)) return setNotice({ text: outcome.ok ? "Unable to save the details." : outcome.message, failed: true });
    onSaved(outcome.data as unknown as Detail);
  }

  return (
    <form onSubmit={save} noValidate aria-label="Lead details" style={{ display: "grid", gap: 8, marginTop: 8 }}>
      <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))" }}>
        <LeadContactFields idPrefix="counselor-lead" values={values} disabled={busy} onChange={(key, value) => setValues((v) => ({ ...v, [key]: value }))} />
      </div>
      <NoticeLine notice={notice} />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save details"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

/** T19 / HO4: back to the telecaller with a reason (required; kept in the stage history). */
function ReturnLeadForm({ lead, onReturned }: { lead: Detail; onReturned: () => void }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = reason.trim();
    if (!text) return setNotice({ text: "Add a reason for returning the lead.", failed: true });
    setBusy(true);
    const outcome = await sendJson(counselorLeadUrl(lead.id, "/return"), "POST", { reason: text });
    setBusy(false);
    if (!outcome.ok) return setNotice({ text: outcome.message, failed: true });
    onReturned();
  }

  if (!open) return <button type="button" className="btn secondary small" onClick={() => setOpen(true)}>Return to telecaller</button>;
  return (
    <form onSubmit={submit} noValidate aria-label="Return to telecaller" style={{ display: "grid", gap: 8, maxWidth: "32rem" }}>
      <div className="field">
        <label htmlFor={`${id}-reason`}>Reason for returning</label>
        <textarea id={`${id}-reason`} rows={3} maxLength={500} aria-required value={reason} disabled={busy}
          onChange={(e) => { setReason(e.target.value); setNotice(null); }} />
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>The lead goes back to Follow-up with {lead.telecaller?.full_name ?? "the telecaller"}; any open counselling appointment is cancelled.</p>
      <NoticeLine notice={notice} />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Returning…" : "Return lead"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={() => { setOpen(false); setNotice(null); }}>Cancel</button>
      </div>
    </form>
  );
}

/** ccrm-003 (A2, A3): what the counselor does next and by when. Required (with its due date) before an open stage move; the API checks
 *  the date (today or later when changed) and answers with the lead. */
function NextActionPanel({ lead, onSaved }: { lead: Detail; onSaved: (lead: Detail) => void }) {
  const id = useId();
  const [editing, setEditing] = useState(false);
  const [action, setAction] = useState(lead.next_action ?? "");
  const [due, setDue] = useState(lead.next_action_due ?? "");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = action.trim();
    if (!text || !due) return setNotice({ text: "Add the next action and its due date.", failed: true });
    setBusy(true);
    const outcome = await sendJson(counselorLeadUrl(lead.id, "/next-action"), "PUT", { next_action: text, next_action_due: due });
    setBusy(false);
    if (!outcome.ok) return setNotice({ text: outcome.message, failed: true });
    if (!isRequestBody(outcome.data)) return setNotice({ text: "Unable to save the next action.", failed: true });
    setEditing(false);
    onSaved(outcome.data as unknown as Detail); // the page shows the result under the stage line
  }

  function open() {
    setAction(lead.next_action ?? "");
    setDue(lead.next_action_due ?? "");
    setNotice(null);
    setEditing(true);
  }

  return (
    <section aria-labelledby="lead-next-action-heading">
      <h3 id="lead-next-action-heading" style={{ margin: 0 }}>Next action</h3>
      {lead.next_action ? (
        <p style={{ margin: "6px 0 0", overflowWrap: "anywhere" }}>
          <strong>{lead.next_action}</strong> <span className="muted">· due {lead.next_action_due ? formatCalendarDate(lead.next_action_due) : "—"}</span>{" "}
          {lead.next_action_overdue && <span className="badge status error">Overdue</span>}
        </p>
      ) : lead.permissions.follow_up ? (
        <p className="muted" style={{ margin: "6px 0 0", fontSize: 13 }}>No next action set. Add one before moving the lead to an open stage.</p>
      ) : (
        <p className="muted" style={{ margin: "6px 0 0", fontSize: 13 }}>No next action.</p>  // QA-04: a closed lead has nothing to add
      )}
      {editing ? (
        <form onSubmit={submit} noValidate aria-label="Set the next action" style={{ display: "grid", gap: 8, maxWidth: "32rem", marginTop: 8 }}>
          <div className="field">
            <label htmlFor={`${id}-action`}>Action</label>
            <input id={`${id}-action`} maxLength={200} aria-required value={action} disabled={busy} placeholder="e.g. Send the university shortlist"
              onChange={(e) => { setAction(e.target.value); setNotice(null); }} />
          </div>
          <div className="field">
            <label htmlFor={`${id}-due`}>Due date</label>
            <input id={`${id}-due`} type="date" aria-required value={due} disabled={busy} onChange={(e) => { setDue(e.target.value); setNotice(null); }} />
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save next action"}</button>
            <button type="button" className="btn secondary small" disabled={busy} onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </form>
      ) : (
        lead.permissions.follow_up && (
          <div style={{ marginTop: 6 }}>
            <button type="button" className="btn secondary small" onClick={open}>{lead.next_action ? "Edit next action" : "Set next action"}</button>
          </div>
        )
      )}
      <NoticeLine notice={notice} />
    </section>
  );
}

/** T20 / HO1: the suggested match (same email or mobile) first, a search otherwise; the counselor confirms before anything is linked. */
function LinkStudentPanel({ lead, onLinked }: { lead: Detail; onLinked: (outcome: SendOutcome) => void }) {
  const id = useId();
  const [results, setResults] = useState<{ query: string; items: StudentSuggestion[] } | "loading" | "failed">("loading");
  const [query, setQuery] = useState("");
  const [confirming, setConfirming] = useState<StudentSuggestion | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);

  const load = useCallback(async (q: string, signal?: AbortSignal) => {
    setResults("loading");
    try {
      const response = await fetch(counselorLeadUrl(lead.id, `/link-suggestions${q ? `?${new URLSearchParams({ q })}` : ""}`), { signal });
      const data = response.ok ? await response.json() : null;
      if (!Array.isArray(data?.items)) throw new Error();
      setResults({ query: q, items: data.items });
    } catch {
      if (!signal?.aborted) setResults("failed");
    }
  }, [lead.id]);

  useEffect(() => {
    const controller = new AbortController();
    void load("", controller.signal);
    return () => controller.abort();
  }, [load]);

  function search(event: FormEvent) {
    event.preventDefault();
    const q = query.trim();
    if (q.length < 3) return setNotice({ text: "Enter at least 3 characters.", failed: true });
    setNotice(null);
    setConfirming(null);
    void load(q);
  }

  async function link(student: StudentSuggestion) {
    setBusy(true);
    const outcome = await sendJson(counselorLeadUrl(lead.id, "/student-link"), "POST", { student_id: student.id });
    setBusy(false);
    setConfirming(null);
    if (!outcome.ok) return setNotice({ text: outcome.message, failed: true });
    onLinked(outcome);
  }

  let list: React.ReactNode;
  if (results === "loading") list = <p className="muted" role="status" style={{ fontSize: 13 }}>Looking for student accounts…</p>;
  else if (results === "failed") list = <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load student accounts.</p>;
  else if (results.items.length === 0) {
    list = <p className="muted" style={{ fontSize: 13 }}>{results.query ? "No active student account matches that search." : "No student account has this lead's email or mobile. Search for one below."}</p>;
  } else {
    list = (
      <ul aria-label={results.query ? "Matching students" : "Suggested match"} style={{ margin: "6px 0 0", paddingLeft: 0, listStyle: "none", display: "grid", gap: 6 }}>
        {results.items.map((s) => (
          <li key={s.id} className="panel" style={{ padding: 10, display: "grid", gap: 6 }}>
            <div style={{ overflowWrap: "anywhere" }}><strong>{s.full_name}</strong> <span className="muted">{s.email}{s.phone ? ` · ${s.phone}` : ""}</span></div>
            {s.linked_elsewhere ? (
              <span className="muted" style={{ fontSize: 13 }}>Already linked to another lead</span>
            ) : confirming?.id === s.id ? (
              <BdmConfirm label="Confirm link" confirmText="Yes, link" busyText="Linking…" cancelText="Keep looking" busy={busy}
                onConfirm={() => void link(s)} onCancel={() => setConfirming(null)}>
                Link {s.full_name} to this lead? The lead moves to Application/Enrollment.
              </BdmConfirm>
            ) : (
              <div><button type="button" className="btn small" aria-label={`Link ${s.full_name}`} disabled={busy} onClick={() => setConfirming(s)}>Link</button></div>
            )}
          </li>
        ))}
      </ul>
    );
  }
  return (
    <div style={{ display: "grid", gap: 8 }}>
      {list}
      <form onSubmit={search} noValidate role="search" aria-label="Find a student account" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        <div className="field" style={{ flex: "1 1 14rem", margin: 0 }}>
          <label htmlFor={`${id}-q`}>Search students</label>
          <input id={`${id}-q`} type="search" maxLength={200} placeholder="Name, email or mobile" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <button type="submit" className="btn secondary small">Search</button>
      </form>
      <NoticeLine notice={notice} />
    </div>
  );
}

type Converted = { id: string; full_name: string; email: string; mailed: boolean };

/** ccrm-008 (DEC-SCOPE-252): one step from lead to a new overseas student -- the csc-002 account prefilled from the lead, the link and the
 *  copy of the lead's details into the profile. The entry is kept on any failure; a 409 for an existing student points at the link list. */
function ConvertLeadForm({ lead, onConverted }: { lead: Detail; onConverted: (lead: Detail, student: Converted) => void }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [entry, setEntry] = useState({ full_name: lead.name, email: lead.email ?? "", phone: lead.phone ?? "" });
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [notice, setNotice] = useState<Notice>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    const full_name = entry.full_name.trim(), email = entry.email.trim(), phone = entry.phone.trim();
    if (!full_name || !email) return setNotice({ text: "Add the student's name and email.", failed: true });
    inFlight.current = true;
    setBusy(true);
    const outcome = await sendJson(counselorLeadUrl(lead.id, "/convert"), "POST", { full_name, email, phone: phone || null });
    inFlight.current = false;
    setBusy(false);
    if (!outcome.ok) return setNotice({ text: staffFailure(outcome, true), failed: true });
    const { student, lead: next, email_status } = outcome.data as { student?: Converted; lead?: unknown; email_status?: string };
    if (!student || !isRequestBody(next)) return setNotice({ text: "Unable to convert the lead.", failed: true });
    onConverted(next as unknown as Detail, { ...student, mailed: email_status === "sent" });
  }

  const field = (name: keyof typeof entry, label: string, type: string, max: number) => (
    <div className="field">
      <label htmlFor={`${id}-${name}`}>{label}</label>
      <input id={`${id}-${name}`} type={type} maxLength={max} autoComplete="off" aria-required={name !== "phone"} value={entry[name]} disabled={busy}
        onChange={(e) => { setEntry((v) => ({ ...v, [name]: e.target.value })); setNotice(null); }} />
    </div>
  );

  if (!open) return <div><button type="button" className="btn small" onClick={() => setOpen(true)}>Convert to student</button></div>;
  return (
    <form onSubmit={submit} noValidate aria-label="Convert to student" style={{ display: "grid", gap: 8, maxWidth: "32rem" }}>
      {field("full_name", "Full name", "text", 160)}
      {field("email", "Email", "email", 255)}
      {field("phone", "Phone (optional)", "tel", 40)}
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>Creates the student&apos;s account, copies this lead&apos;s details into their profile, emails a set-password link and moves the lead to Application/Enrollment.</p>
      <NoticeLine notice={notice} />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Creating…" : "Create student account"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={() => { setOpen(false); setNotice(null); }}>Cancel</button>
      </div>
    </form>
  );
}

/** tel-018 (spec §4): a lead handed to this counselor -- its details (read only), the student link (T20), the read-only milestones
 *  (T4), the return (T19) and the activity. ccrm-003: the next action, the CC8 stage moves and the follow-ups. `permissions` from the
 *  API decide which actions show; the API decides every rule. */
export default function CounselorLeadDetail({ initial }: { initial: Detail }) {
  const [lead, setLead] = useState(initial);
  const [returned, setReturned] = useState(false);
  const [activityVersion, setActivityVersion] = useState(0); // tel-015: a bump re-reads the timeline
  const [unlinking, setUnlinking] = useState(false);
  const [converted, setConverted] = useState<Converted | null>(null); // ccrm-008: the account just created, for the mail outcome line
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [leadNotice, setLeadNotice] = useState<Notice>(null);
  const [editing, setEditing] = useState(false); // ccrm-005: the contact, consent and referral edit
  const [detailsNotice, setDetailsNotice] = useState<Notice>(null);
  const followUpApi = useMemo(() => counselorFollowUpApi(lead.division), [lead.division]);
  const listHref = `/${lead.division === "overseas" ? "overseas" : "it"}/counselor/leads`;
  const reloadActivity = () => setActivityVersion((n) => n + 1);
  // A closing move cancels open follow-ups and appointments on the server; re-read the lead so its permissions follow the new stage.
  async function stageChanged(status: string) {
    setLead((l) => ({ ...l, status, status_label: stageLabel(status) }));
    reloadActivity();
    const response = await fetch(counselorLeadUrl(lead.id)).catch(() => null);
    const data = response?.ok ? await response.json().catch(() => null) : null;
    if (isRequestBody(data)) setLead(data as unknown as Detail);
  }

  function applied(outcome: SendOutcome, text: string) {
    if (!outcome.ok || !isRequestBody(outcome.data)) return setNotice({ text: outcome.ok ? "Unable to update the lead." : outcome.message, failed: true });
    setLead(outcome.data as unknown as Detail);
    setNotice({ text, failed: false });
    setActivityVersion((n) => n + 1);
  }

  async function unlink() {
    setBusy(true);
    const outcome = await sendRequest(counselorLeadUrl(lead.id, "/student-link"), { method: "DELETE" });
    setBusy(false);
    setUnlinking(false);
    applied(outcome, "Student unlinked.");
  }

  const fields: [string, React.ReactNode][] = [
    ["Lead ID", lead.lead_code], ["Mobile number", show(lead.phone)], ["Email", show(lead.email)], ["City", show(lead.city)],
    ["Qualification", show(lead.qualification)], ["Lead source", SOURCE_LABEL[lead.source] ?? lead.source], ["Product interest", show(lead.product?.name)],
    ["Telecaller", show(lead.telecaller?.full_name, "Unassigned")], ["Lead date", <LocalTime key="date" value={lead.created_at} />],
    ...contactRows(lead), // ccrm-005
  ];

  return (
    <div className="action-card" style={{ display: "grid", gap: 16 }}>
      <div>
        <Link href={listHref} className="muted" style={{ fontSize: 13 }}>Back to my leads</Link>
        <div className="eyebrow" style={{ marginTop: 8 }}>{lead.lead_code}</div>
        <h2 style={{ margin: "4px 0" }}>{lead.name}</h2>
        <p className="muted" style={{ margin: 0 }}>Stage: <strong>{lead.status_label}</strong></p>
        {/* QA-02/QA-03: one line for the stage and next-action results -- stays visible when a closing move removes the stage control */}
        <NoticeLine notice={leadNotice} />
      </div>

      {/* ccrm-003 (QA-01): the counselor's daily actions come before the student link */}
      {!returned && (
        <>
          <NextActionPanel lead={lead} onSaved={(next) => { setLead(next); setLeadNotice({ text: "Next action saved.", failed: false }); reloadActivity(); }} />
          {lead.permissions.stage && (
            <section aria-labelledby="lead-stage-heading">
              <h3 id="lead-stage-heading" style={{ margin: 0 }}>Stage</h3>
              <div style={{ marginTop: 6 }}>
                <LeadStageControl lead={lead} targets={counselorTargets(lead.status)} move={counselorMoveStage}
                  onMessage={(m) => setLeadNotice({ text: m.text, failed: m.failed })} onChanged={(status) => void stageChanged(status)} />
              </div>
            </section>
          )}
          <LeadFollowUps leadId={lead.id} leadStage={lead.status} canWrite={lead.permissions.follow_up} api={followUpApi}
            onStageChanged={(status) => void stageChanged(status)} onChanged={reloadActivity} />
        </>
      )}

      {returned ? (
        <p className="form-message" role="status">Lead returned to the telecaller.</p>
      ) : (
        <>
          {lead.permissions.return && <ReturnLeadForm lead={lead} onReturned={() => setReturned(true)} />}
          <section aria-labelledby="lead-link-heading">
            <h3 id="lead-link-heading" style={{ margin: 0 }}>Student account</h3>
            {lead.converted_user ? (
              <div style={{ display: "grid", gap: 6, marginTop: 6 }}>
                <p style={{ margin: 0, overflowWrap: "anywhere" }}>Linked to <strong>{lead.converted_user.full_name}</strong> ({lead.converted_user.email})</p>
                {lead.permissions.unlink && (unlinking ? (
                  <BdmConfirm label="Confirm unlink" confirmText="Yes, unlink" busyText="Unlinking…" cancelText="Keep it" busy={busy}
                    onConfirm={() => void unlink()} onCancel={() => setUnlinking(false)}>
                    Unlink {lead.converted_user.full_name}? The lead goes back to Follow-up.
                  </BdmConfirm>
                ) : (
                  <div><button type="button" className="btn secondary small" onClick={() => { setUnlinking(true); setNotice(null); }}>Unlink student</button></div>
                ))}
                {lead.status === "converted" && <p className="muted" style={{ margin: 0, fontSize: 13 }}>The student has enrolled, so the lead is converted. Only an admin can unlink it.</p>}
                {converted && converted.id === lead.converted_user.id && (
                  <p className="form-message" role="status" style={{ margin: 0, fontSize: 13, overflowWrap: "anywhere" }}>
                    {converted.mailed
                      ? `Student account created for ${converted.full_name}. A set-password link was emailed to ${converted.email}.`
                      : `Student account created for ${converted.full_name}, but the set-password email was not delivered. Re-send it from My students.`}{" "}
                    <Link href={`/overseas/counselor/students/${encodeURIComponent(converted.id)}/profile`}>Open the student&apos;s profile</Link>
                  </p>
                )}
              </div>
            ) : lead.permissions.link ? (
              <div style={{ display: "grid", gap: 10, marginTop: 6 }}>
                {lead.permissions.convert ? (
                  <ConvertLeadForm lead={lead} onConverted={(next, student) => { setLead(next); setConverted(student); setNotice(null); reloadActivity(); }} />
                ) : lead.division === "overseas" && (
                  <p className="muted" style={{ margin: 0, fontSize: 13 }}>Move the lead to Qualified to convert it to a new student.</p>
                )}
                <LinkStudentPanel lead={lead} onLinked={(outcome) => applied(outcome, "Student linked.")} />
              </div>
            ) : (
              <p className="muted" style={{ fontSize: 13 }}>No student account is linked.</p>
            )}
            <NoticeLine notice={notice} />
          </section>
        </>
      )}

      <LeadMilestones milestones={lead.milestones} status={lead.status} />

      <section aria-labelledby="lead-details-heading">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
          <h3 id="lead-details-heading" style={{ margin: 0 }}>Lead details</h3>
          {!returned && !editing && (
            <button type="button" className="btn secondary small" onClick={() => { setEditing(true); setDetailsNotice(null); }}>Edit details</button>
          )}
        </div>
        {editing ? (
          <ContactForm lead={lead} onCancel={() => setEditing(false)}
            onSaved={(next) => { setLead(next); setEditing(false); setDetailsNotice({ text: "Details saved.", failed: false }); }} />
        ) : (
          <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(12rem, 1fr))", gap: "8px 16px", margin: "8px 0 0" }}>
            {fields.map(([term, value]) => (
              <div key={term}>
                <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
                <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>
              </div>
            ))}
          </dl>
        )}
        <NoticeLine notice={detailsNotice} />
        <p style={{ margin: "8px 0 0" }}><strong>{lead.subject}</strong></p>
        {lead.message && <p style={{ margin: "4px 0 0", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{lead.message}</p>}
      </section>

      {/* ccrm-005 (LF7): tel-009's qualification through the counselor's route; a returned lead has left this counselor's scope */}
      {!returned && (
        <LeadQualificationForm leadId={lead.id} url={counselorLeadUrl(lead.id, "/qualification")} productId={lead.product?.id ?? null} readOnly={false}
          onSaved={(q) => setLead((l) => ({ ...l, qualification: q.qualification, passing_year: q.passing_year, city: q.city, state: q.state }))} />
      )}

      {/* ccrm-002: a returned lead has left this counselor's scope (its notes stay on the lead for the telecaller) */}
      {!returned && (
        <section aria-labelledby="lead-notes-heading">
          <h3 id="lead-notes-heading" style={{ margin: 0 }}>Notes</h3>
          <LeadNotes url={counselorLeadUrl(lead.id, "/notes")} onAdded={() => setActivityVersion((n) => n + 1)} />
        </section>
      )}

      <section aria-labelledby="lead-activity-heading">
        <h3 id="lead-activity-heading" style={{ margin: 0 }}>Activity</h3>
        <LeadTimeline url={counselorLeadUrl(lead.id, "/timeline")} version={activityVersion} />
      </section>
    </div>
  );
}
