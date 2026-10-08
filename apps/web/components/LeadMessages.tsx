"use client";
import { useEffect, useId, useRef, useState } from "react";

import EmailComposer from "@/components/EmailComposer";
import WhatsAppComposer from "@/components/WhatsAppComposer";
import { sendRequest, type Page } from "@/lib/apiErrors";
import { SAVE_FAILED, writeFailure } from "@/lib/bdmTasks";
import { getPage } from "@/lib/telecallerCatalogue";
import { isPending, leadMessagesUrl, leadTarget, messageTitle, messageUrl, type LeadMessage } from "@/lib/telecallerMessages";

type Notice = { text: string; failed: boolean } | null;
type Channel = "whatsapp" | "email";
const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;
const POLL_MS = 5000; // tel-014: a queued email is usually sent within seconds

/** One send with Delete when the API says the viewer may (WA3: the sender, on its IST day; never an email, EM2). */
function MessageItem({ message, onDeleted, onRefused }: { message: LeadMessage; onDeleted: () => void; onRefused: (text: string) => void }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const id = useId();

  async function remove() {
    setBusy(true);
    setFailure(null);
    const result = await sendRequest(messageUrl(message.id), { method: "DELETE" });
    setBusy(false);
    if (result.ok) return onDeleted();
    const kind = writeFailure(result.status);
    if (kind === "changed") return onRefused(result.message);
    setFailure(kind === "retry" || kind === "offline" ? SAVE_FAILED : result.message);
  }

  return (
    <li className="action-card" style={{ listStyle: "none", gap: 6 }} aria-labelledby={`${id}-title`}>
      <strong id={`${id}-title`}>{messageTitle(message)}</strong>
      <p className="muted" style={{ margin: 0 }}>{message.template?.name ?? "Custom message"} · {message.sender.full_name}</p>
      {message.subject && <p style={{ ...TEXT, margin: 0 }}><strong>Subject:</strong> {message.subject}</p>}
      <p style={{ ...TEXT, margin: 0 }}>{message.body}</p>
      {message.delivery_status === "failed" && (
        <p className="form-error" style={{ margin: 0, fontSize: 13 }}>This email was not delivered. Check the lead&apos;s email address and send it again.</p>
      )}
      {message.delivery_status === "retrying" && (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>The mail server didn&apos;t accept it yet. It will be retried automatically.</p>
      )}
      {confirming ? (
        <div role="group" aria-label="Confirm delete" className="actions">
          <span>Delete this record? It does not unsend the WhatsApp message.</span>
          <button type="button" className="btn small" disabled={busy} onClick={() => void remove()}>{busy ? "Deleting…" : "Yes, delete"}</button>
          <button type="button" className="btn secondary small" disabled={busy} onClick={() => setConfirming(false)}>Keep it</button>
        </div>
      ) : message.can_delete && (
        <div className="actions"><button type="button" className="btn secondary small" onClick={() => setConfirming(true)}>Delete</button></div>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
    </li>
  );
}

/** tel-013 / tel-014 (spec §4 / §5): the lead page's messages, newest first. `canWrite` (the lead's telecaller, lead not handed over or
 *  closed) offers Send WhatsApp and Send email, each disabled with its reason when the lead has no usable number / address (AC3). A bump of
 *  `openSignal` / `emailSignal` (the page's WhatsApp / Email button) opens that composer. While an email is queued or sending, the list
 *  refreshes so its status moves on. */
export default function LeadMessages({ leadId, whatsappTo, email = null, canWrite, openSignal, emailSignal = 0, onChanged }: {
  leadId: string; whatsappTo: string | null; email?: string | null; canWrite: boolean; openSignal: number; emailSignal?: number;
  onChanged?: () => void; // tel-015: a send or delete -- the page's timeline re-reads
}) {
  const [data, setData] = useState<Page<LeadMessage> | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [composing, setComposing] = useState<Channel | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const reasonId = useId();
  const emailReasonId = useId();
  const whatsAppButton = useRef<HTMLButtonElement>(null);
  const emailButton = useRef<HTMLButtonElement>(null);
  const lastComposer = useRef<Channel | null>(null);
  const reload = () => setVersion((n) => n + 1);
  const canWhatsApp = canWrite && !!whatsappTo;
  const canEmail = canWrite && !!email;

  useEffect(() => {
    // QA-04: the closed composer took the focus with it -- give it back to the button that opened it
    if (lastComposer.current && !composing) (lastComposer.current === "email" ? emailButton : whatsAppButton).current?.focus();
    lastComposer.current = composing;
  }, [composing]);

  const open = (channel: Channel) => {
    setComposing(channel);
    setNotice(null);
  };
  useEffect(() => {
    if (openSignal > 0 && canWhatsApp) open("whatsapp");
  }, [openSignal, canWhatsApp]);
  useEffect(() => {
    if (emailSignal > 0 && canEmail) open("email");
  }, [emailSignal, canEmail]);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<LeadMessage>(leadMessagesUrl(leadId), controller.signal).then(setData).catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [leadId, version]);

  useEffect(() => {
    if (!data?.items.some(isPending)) return;
    const timer = setTimeout(reload, POLL_MS);
    return () => clearTimeout(timer);
  }, [data]);

  const done = (text: string) => {
    setNotice({ text, failed: false });
    reload();
    onChanged?.();
  };

  return (
    <section aria-labelledby="lead-messages-heading">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id="lead-messages-heading" style={{ margin: 0 }}>Messages</h3>
        {canWrite && !composing && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <button ref={whatsAppButton} type="button" className="btn secondary small" disabled={!whatsappTo}
              aria-describedby={whatsappTo ? undefined : reasonId} onClick={() => open("whatsapp")}>Send WhatsApp</button>
            <button ref={emailButton} type="button" className="btn secondary small" disabled={!email}
              aria-describedby={email ? undefined : emailReasonId} onClick={() => open("email")}>Send email</button>
          </div>
        )}
      </div>
      {canWrite && !whatsappTo && <p id={reasonId} className="muted" style={{ fontSize: 13, margin: "4px 0 0" }}>No WhatsApp or mobile number on this lead.</p>}
      {canWrite && !email && <p id={emailReasonId} className="muted" style={{ fontSize: 13, margin: "4px 0 0" }}>No email address on this lead.</p>}
      <div role="status" aria-live="polite">
        {notice && <p className={notice.failed ? "form-error" : "form-message"} style={{ margin: "6px 0 0", fontSize: 13 }}>{notice.text}</p>}
      </div>
      {composing === "whatsapp" && canWhatsApp && whatsappTo && (
        <WhatsAppComposer target={leadTarget(leadId)} to={whatsappTo} onCancel={() => setComposing(null)}
          onRecorded={() => { setComposing(null); done("WhatsApp send recorded."); }} />
      )}
      {composing === "email" && canEmail && (
        <EmailComposer target={leadTarget(leadId)} onCancel={() => setComposing(null)} onSent={() => { setComposing(null); done("Email queued for sending."); }} />
      )}
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the messages.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading messages…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ fontSize: 13 }}>No messages sent yet.</p>
      ) : (
        <ul aria-label="Messages" style={{ padding: 0, margin: "8px 0 0", display: "grid", gap: 8 }}>
          {data.items.map((message) => (
            <MessageItem key={message.id} message={message} onDeleted={() => done("Message deleted.")}
              onRefused={(text) => { setNotice({ text, failed: true }); reload(); }} />
          ))}
        </ul>
      )}
      {data && data.total > data.items.length && <p className="muted" style={{ fontSize: 13 }}>Showing the latest {data.items.length} of {data.total} messages.</p>}
    </section>
  );
}
