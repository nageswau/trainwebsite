"use client";
import { type FormEvent, useEffect, useId, useState } from "react";

import MessagesSection, { type MessageLine } from "@/components/MessagesSection";
import { sendJson } from "@/lib/apiErrors";
import { istInputToIso, nowIstInput } from "@/lib/bdmAppointments";
import { fieldErrors } from "@/lib/bdmTravel";
import { contactsOf, type ContactList } from "@/lib/recruiterContacts";
import { REASONS } from "@/lib/recruiterFollowUps";
import {
  candidateMessagesUrl, companyMessagesUrl, MESSAGE_OUTCOME_MAX, MESSAGES_URL, messageOutcomeUrl, recruiterTarget, type MessageContext, type Party,
} from "@/lib/recruiterMessages";

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

/** pob-007 (DEC-SCOPE-421 A3): what came of a message to a contact, once, with an optional next follow-up (the company's). */
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

  return (
    <MessagesSection
      listUrl={source.kind === "candidate" ? candidateMessagesUrl(source.party.id) : companyMessagesUrl(source.companyId)}
      parties={contacts}
      picker={source.kind !== "candidate"}
      targetFor={(party) => recruiterTarget(party, context)}
      canWrite={canWrite}
      noParties="Add an active contact to send a message."
      copy={{ context }}
      itemAction={(message, done) =>
        canWrite && message.contact && (!message.replied_at || !message.outcome) ? (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "start" }}>
            {!message.replied_at && <LogReply message={message} done={done} />}
            {!message.outcome && <RecordOutcome message={message} done={done} />}
          </div>
        ) : null
      }
      onChanged={() => {
        setVersion((n) => n + 1);
        onChanged?.();
      }}
    />
  );
}
