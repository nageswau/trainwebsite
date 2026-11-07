"use client";
import { type ReactNode, useEffect, useId, useRef, useState } from "react";

import CopyComposer from "@/components/CopyComposer";
import EmailComposer from "@/components/EmailComposer";
import WhatsAppComposer from "@/components/WhatsAppComposer";
import type { Page } from "@/lib/apiErrors";
import type { CadenceRun } from "@/lib/recruiterCadences";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { CHANNEL_LABEL, isPending, linkedinTitle, messageTitle, type Channel, type CopyChannel, type MessageContext, type Party } from "@/lib/recruiterMessages";
import { getPage } from "@/lib/telecallerCatalogue";
import { sentLabel, type ComposerTarget, type DeliveryStatus } from "@/lib/telecallerMessages";

/** What a message line needs: rec-026's recruiter messages and upc-012's university messages both fit. ccrm-037's student messages add
 *  the application they are about and replies recorded by hand (`direction: "inbound"`). */
export type MessageLine = {
  id: string; contact?: { name: string } | null; candidate?: { name: string } | null; channel: Channel | "linkedin"; template: { name: string } | null;
  subject: string | null; body: string; delivery_status: DeliveryStatus | null; sent_at: string; sender: { full_name: string };
  direction?: "outbound" | "inbound"; application?: { label: string } | null;
  replied_at?: string | null; // pob-005 D7: a reply the recruiter logged on this message
  // pob-007 (A1/A3): a LinkedIn row's action; an outcome and its next follow-up
  linkedin_action?: string | null; outcome?: string | null; follow_up?: { id: string; due_at: string } | null;
  cadence?: CadenceRun | null; // pob-008 B6: the outreach cadence started on this message (type only; rendered by the recruiter's itemAction)
};
const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;
const POLL_MS = 5000; // a queued email is usually sent within seconds

function MessageItem({ message, showTo, action }: { message: MessageLine; showTo: boolean; action?: ReactNode }) {
  const id = useId();
  const to = message.contact?.name ?? message.candidate?.name;
  const reply = message.direction === "inbound";
  return (
    <li className="action-card" style={{ listStyle: "none", gap: 6 }} aria-labelledby={`${id}-title`}>
      <strong id={`${id}-title`}>
        {message.channel === "linkedin" ? sentLabel(message.sent_at, linkedinTitle(message.linkedin_action))
          : reply ? sentLabel(message.sent_at, `${CHANNEL_LABEL[message.channel]} reply received`) : messageTitle({ ...message, channel: message.channel })}
      </strong>
      <p className="muted" style={{ margin: 0 }}>
        {showTo && to ? `To ${to} · ` : ""}{message.application ? `About ${message.application.label} · ` : ""}
        {reply ? `Recorded by ${message.sender.full_name}` : `${message.template?.name ?? "Custom message"} · ${message.sender.full_name}`}
      </p>
      {message.subject && <p style={{ ...TEXT, margin: 0 }}><strong>Subject:</strong> {message.subject}</p>}
      {message.body && <p style={{ ...TEXT, margin: 0 }}>{message.body}</p>}
      {message.delivery_status === "failed" && (
        <p className="form-error" style={{ margin: 0, fontSize: 13 }}>This email was not delivered. Check the email address and send it again.</p>
      )}
      {message.delivery_status === "retrying" && (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>The mail server didn&apos;t accept it yet. It will be retried automatically.</p>
      )}
      {message.replied_at && <p className="form-message" style={{ margin: 0, fontSize: 13 }}>{sentLabel(message.replied_at, "Reply received")}</p>}
      {message.outcome && (
        <p style={{ ...TEXT, margin: 0, fontSize: 13 }}>
          <strong>Outcome:</strong> {message.outcome}{message.follow_up && ` (follow-up due ${formatSchoolDateTime(message.follow_up.due_at, true)})`}
        </p>
      )}
      {action}
    </li>
  );
}

/** rec-026 (spec §5), shared with upc-012: a Messages section -- the list (newest first; pending emails polled), and for a writer a
 *  recipient picker (`picker`) with Send WhatsApp and Send email, each disabled with its reason when the recipient has no usable number /
 *  address. WhatsApp is recorded only on the composer's confirm; an email is queued and its status refreshes. `parties` is null while the
 *  owner is still loading them. pob-023 (G10/G12): `copy` (recruiter sections only) adds LinkedIn and calling-script copy mode, with the
 *  record the messages are about. */
export default function MessagesSection({ listUrl, parties, picker, targetFor, canWrite, onChanged, noParties, wide = false, copy, itemAction }: {
  listUrl: string; parties: Party[] | null; picker: boolean; targetFor: (party: Party) => ComposerTarget; canWrite: boolean; onChanged?: () => void;
  noParties: string; wide?: boolean; copy?: { context?: MessageContext };
  /** pob-005: an extra control under a message line (the recruiter's "Log reply"); `done` re-reads the list and tells the page. */
  itemAction?: (message: MessageLine, done: (text: string) => void) => ReactNode;
}) {
  const [data, setData] = useState<Page<MessageLine> | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [partyId, setPartyId] = useState(parties?.[0]?.id ?? "");
  const [composing, setComposing] = useState<Channel | CopyChannel | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const reasonId = useId();
  const pickerId = useId();
  const opener = useRef<Record<Channel | CopyChannel, HTMLButtonElement | null>>({ whatsapp: null, email: null, linkedin: null, call: null });
  const lastComposer = useRef<Channel | CopyChannel | null>(null);
  const reload = () => setVersion((n) => n + 1);
  const party = parties?.find((p) => p.id === partyId) ?? null;

  useEffect(() => {
    // the recipients arrived or changed: keep the chosen one while it is still offered
    if (parties) setPartyId((current) => (parties.some((p) => p.id === current) ? current : (parties[0]?.id ?? "")));
  }, [parties]);

  useEffect(() => {
    // the closed composer took the focus with it -- give it back to the button that opened it
    if (lastComposer.current && !composing) opener.current[lastComposer.current]?.focus();
    lastComposer.current = composing;
  }, [composing]);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<MessageLine>(listUrl, controller.signal).then(setData).catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [listUrl, version]);

  useEffect(() => {
    if (!data?.items.some(isPending)) return;
    const timer = setTimeout(reload, POLL_MS);
    return () => clearTimeout(timer);
  }, [data]);

  const done = (text: string) => {
    setComposing(null);
    setNotice(text);
    reload();
    onChanged?.();
  };
  const reasons = [
    party && !party.whatsappTo ? (party.whatsappOff ?? `No usable mobile number for ${party.name}.`) : null,
    party && !party.email ? `No email address for ${party.name}.` : null,
  ].filter(Boolean);

  return (
    <section aria-labelledby={`${pickerId}-heading`} className={wide ? "action-card wide" : "action-card"} style={{ display: "grid", gap: 8 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id={`${pickerId}-heading`} style={{ margin: 0 }}>Messages</h3>
        {canWrite && !composing && party && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <button ref={(el) => { opener.current.whatsapp = el; }} type="button" className="btn secondary small" disabled={!party.whatsappTo}
              aria-describedby={party.whatsappTo ? undefined : reasonId} onClick={() => { setComposing("whatsapp"); setNotice(null); }}>Send WhatsApp</button>
            <button ref={(el) => { opener.current.email = el; }} type="button" className="btn secondary small" disabled={!party.email}
              aria-describedby={party.email ? undefined : reasonId} onClick={() => { setComposing("email"); setNotice(null); }}>Send email</button>
            {copy && (["linkedin", "call"] as const).map((c) => (
              <button key={c} ref={(el) => { opener.current[c] = el; }} type="button" className="btn secondary small" onClick={() => { setComposing(c); setNotice(null); }}>
                {c === "linkedin" ? "LinkedIn message" : "Calling script"}
              </button>
            ))}
          </div>
        )}
      </div>
      {canWrite && picker && parties !== null && (
        parties.length === 0 ? <p className="muted" style={{ fontSize: 13, margin: 0 }}>{noParties}</p> : (
          <div className="field" style={{ maxWidth: 320 }}>
            <label htmlFor={pickerId}>To</label>
            <select id={pickerId} value={partyId} disabled={!!composing} onChange={(e) => { setPartyId(e.target.value); setNotice(null); }}>
              {parties.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
        )
      )}
      {canWrite && !composing && reasons.length > 0 && <p id={reasonId} className="muted" style={{ fontSize: 13, margin: 0 }}>{reasons.join(" ")}</p>}
      {notice && <p className="form-message" role="status" style={{ margin: 0, fontSize: 13 }}>{notice}</p>}
      {party && composing === "whatsapp" && party.whatsappTo && (
        <WhatsAppComposer key={party.id} target={targetFor(party)} to={party.whatsappTo} onCancel={() => setComposing(null)}
          onRecorded={() => done(`WhatsApp to ${party.name} recorded.`)} />
      )}
      {party && composing === "email" && party.email && (
        <EmailComposer key={party.id} target={targetFor(party)} onCancel={() => setComposing(null)} onSent={() => done(`Email to ${party.name} queued for sending.`)} />
      )}
      {party && copy && (composing === "linkedin" || composing === "call") && (
        <CopyComposer key={`${party.id}-${composing}`} channel={composing} party={party} context={copy.context} onCancel={() => setComposing(null)}
          onCopied={done} />
      )}
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the messages.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading messages…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ fontSize: 13, margin: 0 }}>No messages sent yet.</p>
      ) : (
        <ul aria-label="Messages" style={{ padding: 0, margin: 0, display: "grid", gap: 8 }}>
          {data.items.map((message) => <MessageItem key={message.id} message={message} showTo={picker} action={itemAction?.(message, done)} />)}
        </ul>
      )}
      {data && data.total > data.items.length && <p className="muted" style={{ fontSize: 13 }}>Showing the latest {data.items.length} of {data.total} messages.</p>}
    </section>
  );
}
