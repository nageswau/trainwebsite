"use client";
import { type FormEvent, useEffect, useId, useState } from "react";

import MessagesSection, { type MessageLine } from "@/components/MessagesSection";
import { sendJson } from "@/lib/apiErrors";
import { istInputToIso, nowIstInput } from "@/lib/bdmAppointments";
import { fieldErrors } from "@/lib/bdmTravel";
import { type Cadence, type CadenceList, type CadenceRun, CADENCES_URL, endLabel, messageCadenceUrl, stepsSummary } from "@/lib/recruiterCadences";
import { contactsOf, type ContactList } from "@/lib/recruiterContacts";
import { REASONS } from "@/lib/recruiterFollowUps";
import {
  candidateMessagesUrl, companyMessagesUrl, MESSAGE_OUTCOME_MAX, MESSAGES_URL, messageOutcomeUrl, recruiterTarget, type MessageContext, type Party,
} from "@/lib/recruiterMessages";
import { sentLabel } from "@/lib/telecallerMessages";

/** pob-023 (G12): a requirement page writes to its company's contacts with the requirement as context; an interview writes to its
 *  candidate with the interview as context. */
type Source =
  | { kind: "company"; companyId: string }
  | { kind: "requirement"; companyId: string; jobId: string }
  | { kind: "candidate"; party: Party; context?: MessageContext };

/** pob-005 (DEC-SCOPE-411 D7): record that a contact replied to this message -- moves them to Replied. Set once by the API. */
function LogReply({ message, done }: { message: MessageLine; done: (text: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  async function log() {
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(`${MESSAGES_URL}/${encodeURIComponent(message.id)}/reply`, "POST", {});
    setBusy(false);
    if (outcome.ok) done(`Reply from ${message.contact?.name ?? "the contact"} logged.`);
    else setFailure(outcome.message);
  }
  return (
    <div style={{ display: "grid", gap: 4 }}>
      <div>
        <button type="button" className="btn secondary small" onClick={() => void log()} disabled={busy}>
          {busy ? "Logging…" : "Log reply"}<span className="visually-hidden"> from {message.contact?.name}</span>
        </button>
      </div>
      {failure && <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>{failure}</p>}
    </div>
  );
}

/** pob-007 (DEC-SCOPE-422 A3): what came of a message to a contact, once, with an optional next follow-up (the company's). */
function RecordOutcome({ message, done }: { message: MessageLine; done: (text: string) => void }) {
  const [open, setOpen] = useState(false);
  const [v, setV] = useState({ outcome: "", due: "", reason: "" });
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [now] = useState(nowIstInput);
  const id = useId();
  const withFollowUp = v.due !== "" || v.reason !== "";
  if (!open) {
    return (
      <div>
        <button type="button" className="btn secondary small" onClick={() => setOpen(true)}>
          Record outcome<span className="visually-hidden"> of the message to {message.contact?.name}</span>
        </button>
      </div>
    );
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    const missing: Record<string, string> = {};
    if (!v.outcome.trim()) missing.outcome = "Describe the outcome";
    if (withFollowUp && !v.due) missing.due_at = "Choose when the follow-up is due";
    if (withFollowUp && !v.reason) missing.reason = "Choose a follow-up reason";
    if (Object.keys(missing).length) return setErrors(missing);
    setBusy(true);
    setErrors({});
    setFailure(null);
    const result = await sendJson(messageOutcomeUrl(message.id), "POST", {
      outcome: v.outcome.trim(), ...(withFollowUp ? { next_follow_up: { due_at: istInputToIso(v.due), reason: v.reason } } : {}),
    });
    setBusy(false);
    if (result.ok) return done(withFollowUp ? "Outcome saved and follow-up added." : "Outcome saved.");
    const placed = fieldErrors(result.detail);
    if (Object.keys(placed).length) return setErrors(placed);
    setFailure(result.message);
  }
  const fid = (key: string) => `${id}-${key}`;
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });
  const error = (key: string) => errors[key] && <p id={`${fid(key)}-error`} className="form-error">{errors[key]}</p>;
  return (
    <form aria-label="Record message outcome" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && setOpen(false)} style={{ display: "grid", gap: 6 }}>
      <div className="field">
        <label htmlFor={fid("outcome")}>Outcome (required)</label>
        <input id={fid("outcome")} autoFocus maxLength={MESSAGE_OUTCOME_MAX} value={v.outcome} onChange={(e) => setV({ ...v, outcome: e.target.value })} {...invalid("outcome")} />
        {error("outcome")}
      </div>
      <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(12rem, 1fr))" }}>
        <div className="field">
          <label htmlFor={fid("due_at")}>Next follow-up due (IST, optional)</label>
          <input id={fid("due_at")} type="datetime-local" min={now} value={v.due} onChange={(e) => setV({ ...v, due: e.target.value })} {...invalid("due_at")} />
          {error("due_at")}
        </div>
        <div className="field">
          <label htmlFor={fid("reason")}>Follow-up reason</label>
          <select id={fid("reason")} value={v.reason} onChange={(e) => setV({ ...v, reason: e.target.value })} {...invalid("reason")}>
            <option value="">Select a reason</option>
            {REASONS.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
          </select>
          {error("reason")}
        </div>
      </div>
      {failure && <p className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save outcome"}</button>
        <button type="button" className="btn secondary small" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </form>
  );
}

/** pob-008 (DEC-SCOPE-423 B6): start an outreach cadence on this message (it is step 1). The API refuses a contact who replied, is Do Not
 *  Contact or already follows one. */
function StartCadence({ message, cadences, done }: { message: MessageLine; cadences: Cadence[]; done: (text: string) => void }) {
  const [open, setOpen] = useState(false);
  const [choice, setChoice] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const id = useId();
  if (!open) {
    return (
      <div>
        <button type="button" className="btn secondary small" onClick={() => setOpen(true)}>
          Start cadence<span className="visually-hidden"> for {message.contact?.name}</span>
        </button>
      </div>
    );
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!choice) return setFailure("Choose a cadence");
    setBusy(true);
    setFailure(null);
    const result = await sendJson(messageCadenceUrl(message.id), "POST", { cadence_id: choice });
    setBusy(false);
    if (result.ok) return done(`Cadence started for ${message.contact?.name ?? "the contact"}.`);
    setFailure(result.message);
  }
  const chosen = cadences.find((c) => c.id === choice);
  return (
    <form aria-label="Start an outreach cadence" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && setOpen(false)} style={{ display: "grid", gap: 6 }}>
      <div className="field">
        <label htmlFor={`${id}-cadence`}>Cadence</label>
        <select id={`${id}-cadence`} autoFocus value={choice} onChange={(e) => setChoice(e.target.value)} aria-invalid={failure ? true : undefined}
          aria-describedby={failure ? `${id}-error` : chosen ? `${id}-steps` : undefined}>
          <option value="">Select a cadence</option>
          {cadences.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        {chosen && <p id={`${id}-steps`} className="muted" style={{ margin: 0, fontSize: 13 }}>{stepsSummary(chosen.steps)}. This message is step 1.</p>}
      </div>
      {failure && <p id={`${id}-error`} className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Starting…" : "Start"}</button>
        <button type="button" className="btn secondary small" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </form>
  );
}

/** pob-008 B7/B9: the cadence running on (or ended on) this message, with Stop while it runs. */
function CadenceStatus({ run, messageId, done }: { run: CadenceRun; messageId: string; done: (text: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  async function stop() {
    setBusy(true);
    setFailure(null);
    const result = await sendJson(`${messageCadenceUrl(messageId)}/stop`, "POST", {});
    setBusy(false);
    if (result.ok) done("Cadence stopped.");
    else setFailure(result.message);
  }
  const text = run.status === "active"
    ? `Cadence: ${run.name} · step ${run.step} of ${run.steps}${run.next_step_at ? ` · ${sentLabel(run.next_step_at, "next")}` : ""}`
    : `Cadence ${run.name} ${run.status === "completed" ? "completed" : `ended: ${endLabel(run.end_reason)}`} (step ${run.step} of ${run.steps})`;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
      <span className="badge">{text}</span>
      {run.can_stop && (
        <button type="button" className="btn secondary small" onClick={() => void stop()} disabled={busy}>
          {busy ? "Stopping…" : "Stop cadence"}<span className="visually-hidden"> {run.name}</span>
        </button>
      )}
      {failure && <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>{failure}</p>}
    </div>
  );
}

/** rec-026 (spec §5): the Messages section of a company page (to one of its active contacts, chosen in the section) or a candidate page.
 *  `canWrite` is the API's `can_edit` on a party that is not archived. The section itself (upc-012 shares it) is `MessagesSection`; this
 *  loads the company's active contacts, again after each send. pob-005: a writer can log a contact's reply on a message. pob-023: LinkedIn
 *  and calling copy mode, and a context record. */
export default function RecruiterMessages({ source, canWrite, onChanged }: { source: Source; canWrite: boolean; onChanged?: () => void }) {
  const [contacts, setContacts] = useState<Party[] | null>(source.kind === "candidate" ? [source.party] : null);
  const [version, setVersion] = useState(0);
  const companyId = source.kind === "candidate" ? null : source.companyId;
  const context: MessageContext | undefined = source.kind === "requirement" ? { jobId: source.jobId } : source.kind === "candidate" ? source.context : undefined;

  useEffect(() => {
    if (!companyId || !canWrite) return;
    const controller = new AbortController();
    fetch(contactsOf(companyId), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      // pob-005 QA-01: a Do Not Contact person is never offered (the API refuses the send anyway)
      .then((list: ContactList) => setContacts(list.items.filter((c) => c.active && c.status !== "do_not_contact").map((c): Party => ({ kind: "contact", id: c.id, name: c.name, whatsappTo: c.whatsapp_to ?? null, email: c.email }))))
      .catch(() => controller.signal.aborted || setContacts([]));
    return () => controller.abort();
  }, [companyId, canWrite, version]);

  // pob-008 B6: the active cadences a writer can start on a contact message (none offered when they cannot be loaded)
  const [cadences, setCadences] = useState<Cadence[] | null>(null);
  useEffect(() => {
    if (!companyId || !canWrite) return;
    const controller = new AbortController();
    fetch(CADENCES_URL, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((list: CadenceList) => setCadences(list.items))
      .catch(() => controller.signal.aborted || setCadences([]));
    return () => controller.abort();
  }, [companyId, canWrite]);

  return (
    <MessagesSection
      listUrl={source.kind === "candidate" ? candidateMessagesUrl(source.party.id) : companyMessagesUrl(source.companyId)}
      parties={contacts}
      picker={source.kind !== "candidate"}
      targetFor={(party) => recruiterTarget(party, context)}
      canWrite={canWrite}
      noParties="Add an active contact to send a message."
      copy={{ context }}
      itemAction={(message, done) => {
        if (!message.contact) return null;
        const cadence = message.cadence ? <CadenceStatus run={message.cadence} messageId={message.id} done={done} /> : null;
        const canStart = canWrite && !message.cadence && !message.replied_at && !!cadences?.length;
        if (!cadence && !canStart && !(canWrite && (!message.replied_at || !message.outcome))) return null;
        return (
          <div style={{ display: "grid", gap: 6 }}>
            {cadence}
            {canWrite && (!message.replied_at || !message.outcome || canStart) && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "start" }}>
                {!message.replied_at && <LogReply message={message} done={done} />}
                {!message.outcome && <RecordOutcome message={message} done={done} />}
                {canStart && <StartCadence message={message} cadences={cadences!} done={done} />}
              </div>
            )}
          </div>
        );
      }}
      onChanged={() => {
        setVersion((n) => n + 1);
        onChanged?.();
      }}
    />
  );
}
