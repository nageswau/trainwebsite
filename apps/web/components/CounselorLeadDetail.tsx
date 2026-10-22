"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useId, useMemo, useState } from "react";

import { LeadStageControl } from "@/components/AdminLeadStage";
import BdmConfirm from "@/components/BdmConfirm";
import LeadFollowUps from "@/components/LeadFollowUps";
import LocalTime from "@/components/LocalTime";
import LeadMilestones from "@/components/LeadMilestones";
import LeadNotes from "@/components/LeadNotes";
import LeadTimeline from "@/components/LeadTimeline";
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
    setNotice({ text: "Next action saved.", failed: false });
    onSaved(outcome.data as unknown as Detail);
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
      ) : (
        <p className="muted" style={{ margin: "6px 0 0", fontSize: 13 }}>No next action set. Add one before moving the lead to an open stage.</p>
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

/** tel-018 (spec §4): a lead handed to this counselor -- its details (read only), the student link (T20), the read-only milestones
 *  (T4), the return (T19) and the activity. ccrm-003: the next action, the CC8 stage moves and the follow-ups. `permissions` from the
 *  API decide which actions show; the API decides every rule. */
export default function CounselorLeadDetail({ initial }: { initial: Detail }) {
  const [lead, setLead] = useState(initial);
  const [returned, setReturned] = useState(false);
  const [activityVersion, setActivityVersion] = useState(0); // tel-015: a bump re-reads the timeline
  const [unlinking, setUnlinking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [stageNotice, setStageNotice] = useState<Notice>(null);
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
  ];

  return (
    <div className="action-card" style={{ display: "grid", gap: 16 }}>
      <div>
        <Link href={listHref} className="muted" style={{ fontSize: 13 }}>Back to my leads</Link>
        <div className="eyebrow" style={{ marginTop: 8 }}>{lead.lead_code}</div>
        <h2 style={{ margin: "4px 0" }}>{lead.name}</h2>
        <p className="muted" style={{ margin: 0 }}>Stage: <strong>{lead.status_label}</strong></p>
      </div>

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
              </div>
            ) : lead.permissions.link ? (
              <LinkStudentPanel lead={lead} onLinked={(outcome) => applied(outcome, "Student linked.")} />
            ) : (
              <p className="muted" style={{ fontSize: 13 }}>No student account is linked.</p>
            )}
            <NoticeLine notice={notice} />
          </section>
        </>
      )}

      {!returned && (
        <>
          <NextActionPanel lead={lead} onSaved={(next) => { setLead(next); reloadActivity(); }} />
          {lead.permissions.stage && (
            <section aria-labelledby="lead-stage-heading">
              <h3 id="lead-stage-heading" style={{ margin: 0 }}>Stage</h3>
              <div style={{ marginTop: 6 }}>
                <LeadStageControl lead={lead} targets={counselorTargets(lead.status)} move={counselorMoveStage}
                  onMessage={(m) => setStageNotice({ text: m.text, failed: m.failed })} onChanged={(status) => void stageChanged(status)} />
              </div>
              <NoticeLine notice={stageNotice} />
            </section>
          )}
          <LeadFollowUps leadId={lead.id} leadStage={lead.status} canWrite={lead.permissions.follow_up} api={followUpApi}
            onStageChanged={(status) => void stageChanged(status)} onChanged={reloadActivity} />
        </>
      )}

      <LeadMilestones milestones={lead.milestones} status={lead.status} />

      <section aria-labelledby="lead-details-heading">
        <h3 id="lead-details-heading" style={{ margin: 0 }}>Lead details</h3>
        <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(12rem, 1fr))", gap: "8px 16px", margin: "8px 0 0" }}>
          {fields.map(([term, value]) => (
            <div key={term}>
              <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
              <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>
            </div>
          ))}
        </dl>
        <p style={{ margin: "8px 0 0" }}><strong>{lead.subject}</strong></p>
        {lead.message && <p style={{ margin: "4px 0 0", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{lead.message}</p>}
      </section>

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
