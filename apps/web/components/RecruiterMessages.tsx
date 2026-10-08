"use client";
import { useEffect, useId, useRef, useState } from "react";

import EmailComposer from "@/components/EmailComposer";
import WhatsAppComposer from "@/components/WhatsAppComposer";
import type { Page } from "@/lib/apiErrors";
import { contactsOf, type ContactList } from "@/lib/recruiterContacts";
import { candidateMessagesUrl, companyMessagesUrl, isPending, messageTitle, recruiterTarget, type Party, type RecMessage } from "@/lib/recruiterMessages";
import { getPage } from "@/lib/telecallerCatalogue";

type Channel = "whatsapp" | "email";
type Source = { kind: "company"; companyId: string } | { kind: "candidate"; party: Party };
const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;
const POLL_MS = 5000; // a queued email is usually sent within seconds

function MessageItem({ message, showTo }: { message: RecMessage; showTo: boolean }) {
  const id = useId();
  const to = message.contact?.name ?? message.candidate?.name;
  return (
    <li className="action-card" style={{ listStyle: "none", gap: 6 }} aria-labelledby={`${id}-title`}>
      <strong id={`${id}-title`}>{messageTitle(message)}</strong>
      <p className="muted" style={{ margin: 0 }}>{showTo && to ? `To ${to} · ` : ""}{message.template?.name ?? "Custom message"} · {message.sender.full_name}</p>
      {message.subject && <p style={{ ...TEXT, margin: 0 }}><strong>Subject:</strong> {message.subject}</p>}
      <p style={{ ...TEXT, margin: 0 }}>{message.body}</p>
      {message.delivery_status === "failed" && (
        <p className="form-error" style={{ margin: 0, fontSize: 13 }}>This email was not delivered. Check the email address and send it again.</p>
      )}
      {message.delivery_status === "retrying" && (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>The mail server didn&apos;t accept it yet. It will be retried automatically.</p>
      )}
    </li>
  );
}

/** rec-026 (spec §5): the Messages section of a company page (to one of its active contacts, chosen here) or a candidate page. `canWrite`
 *  (the API's `can_edit`, party not archived) offers Send WhatsApp and Send email, each disabled with its reason when the recipient has no
 *  usable number / address. WhatsApp is recorded only on the composer's confirm (AC3); an email is queued and its status refreshes (AC2). */
export default function RecruiterMessages({ source, canWrite, onChanged }: { source: Source; canWrite: boolean; onChanged?: () => void }) {
  const [data, setData] = useState<Page<RecMessage> | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [contacts, setContacts] = useState<Party[] | null>(source.kind === "candidate" ? [source.party] : null);
  const [partyId, setPartyId] = useState(source.kind === "candidate" ? source.party.id : "");
  const [composing, setComposing] = useState<Channel | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const reasonId = useId();
  const pickerId = useId();
  const opener = useRef<Record<Channel, HTMLButtonElement | null>>({ whatsapp: null, email: null });
  const lastComposer = useRef<Channel | null>(null);
  const reload = () => setVersion((n) => n + 1);
  const listUrl = source.kind === "company" ? companyMessagesUrl(source.companyId) : candidateMessagesUrl(source.party.id);
  const companyId = source.kind === "company" ? source.companyId : null;
  const party = contacts?.find((p) => p.id === partyId) ?? null;

  useEffect(() => {
    if (!companyId || !canWrite) return;
    const controller = new AbortController();
    fetch(contactsOf(companyId), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((list: ContactList) => {
        const active = list.items.filter((c) => c.active).map((c): Party => ({ kind: "contact", id: c.id, name: c.name, whatsappTo: c.whatsapp_to ?? null, email: c.email }));
        setContacts(active);
        setPartyId((current) => (active.some((p) => p.id === current) ? current : (active[0]?.id ?? "")));
      })
      .catch(() => controller.signal.aborted || setContacts([]));
    return () => controller.abort();
  }, [companyId, canWrite, version]);

  useEffect(() => {
    // the closed composer took the focus with it -- give it back to the button that opened it
    if (lastComposer.current && !composing) opener.current[lastComposer.current]?.focus();
    lastComposer.current = composing;
  }, [composing]);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<RecMessage>(listUrl, controller.signal).then(setData).catch(() => controller.signal.aborted || setFailed(true));
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
    party && !party.whatsappTo ? `No usable mobile number for ${party.name}.` : null,
    party && !party.email ? `No email address for ${party.name}.` : null,
  ].filter(Boolean);

  return (
    <section aria-labelledby={`${pickerId}-heading`} className="action-card" style={{ display: "grid", gap: 8 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id={`${pickerId}-heading`} style={{ margin: 0 }}>Messages</h3>
        {canWrite && !composing && party && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <button ref={(el) => { opener.current.whatsapp = el; }} type="button" className="btn secondary small" disabled={!party.whatsappTo}
              aria-describedby={party.whatsappTo ? undefined : reasonId} onClick={() => { setComposing("whatsapp"); setNotice(null); }}>Send WhatsApp</button>
            <button ref={(el) => { opener.current.email = el; }} type="button" className="btn secondary small" disabled={!party.email}
              aria-describedby={party.email ? undefined : reasonId} onClick={() => { setComposing("email"); setNotice(null); }}>Send email</button>
          </div>
        )}
      </div>
      {canWrite && source.kind === "company" && contacts !== null && (
        contacts.length === 0 ? <p className="muted" style={{ fontSize: 13, margin: 0 }}>Add an active contact to send a message.</p> : (
          <div className="field" style={{ maxWidth: 320 }}>
            <label htmlFor={pickerId}>To</label>
            <select id={pickerId} value={partyId} disabled={!!composing} onChange={(e) => { setPartyId(e.target.value); setNotice(null); }}>
              {contacts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
        )
      )}
      {canWrite && !composing && reasons.length > 0 && <p id={reasonId} className="muted" style={{ fontSize: 13, margin: 0 }}>{reasons.join(" ")}</p>}
      <div role="status" aria-live="polite">
        {notice && <p className="form-message" style={{ margin: 0, fontSize: 13 }}>{notice}</p>}
      </div>
      {party && composing === "whatsapp" && party.whatsappTo && (
        <WhatsAppComposer key={party.id} target={recruiterTarget(party)} to={party.whatsappTo} onCancel={() => setComposing(null)}
          onRecorded={() => done(`WhatsApp to ${party.name} recorded.`)} />
      )}
      {party && composing === "email" && party.email && (
        <EmailComposer key={party.id} target={recruiterTarget(party)} onCancel={() => setComposing(null)} onSent={() => done(`Email to ${party.name} queued for sending.`)} />
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
          {data.items.map((message) => <MessageItem key={message.id} message={message} showTo={source.kind === "company"} />)}
        </ul>
      )}
      {data && data.total > data.items.length && <p className="muted" style={{ fontSize: 13 }}>Showing the latest {data.items.length} of {data.total} messages.</p>}
    </section>
  );
}
