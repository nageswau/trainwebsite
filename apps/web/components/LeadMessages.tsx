"use client";
import { useEffect, useId, useState } from "react";

import WhatsAppComposer from "@/components/WhatsAppComposer";
import { sendRequest, type Page } from "@/lib/apiErrors";
import { SAVE_FAILED, writeFailure } from "@/lib/bdmTasks";
import { getPage } from "@/lib/telecallerCatalogue";
import { leadMessagesUrl, messageUrl, sentLabel, type LeadMessage } from "@/lib/telecallerMessages";

type Notice = { text: string; failed: boolean } | null;
const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;

/** One send with Delete when the API says the viewer may (WA3: the sender, on its IST day). */
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
      <strong id={`${id}-title`}>{sentLabel(message.sent_at)}</strong>
      <p className="muted" style={{ margin: 0 }}>{message.template?.name ?? "Custom message"} · {message.sender.full_name}</p>
      <p style={{ ...TEXT, margin: 0 }}>{message.body}</p>
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

/** tel-013 (spec §4): the lead page's messages, newest first. `canWrite` (the lead's telecaller, lead not handed over or closed) offers Send
 *  WhatsApp, disabled with its reason when the lead has no usable number (AC3). A bump of `openSignal` (the page's WhatsApp button) opens it. */
export default function LeadMessages({ leadId, whatsappTo, canWrite, openSignal }: {
  leadId: string; whatsappTo: string | null; canWrite: boolean; openSignal: number;
}) {
  const [data, setData] = useState<Page<LeadMessage> | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [composing, setComposing] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const reasonId = useId();
  const reload = () => setVersion((n) => n + 1);
  const canSend = canWrite && !!whatsappTo;

  useEffect(() => {
    if (openSignal > 0 && canSend) {
      setComposing(true);
      setNotice(null);
    }
  }, [openSignal, canSend]);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<LeadMessage>(leadMessagesUrl(leadId), controller.signal).then(setData).catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [leadId, version]);

  const done = (text: string) => {
    setNotice({ text, failed: false });
    reload();
  };

  return (
    <section aria-labelledby="lead-messages-heading">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id="lead-messages-heading" style={{ margin: 0 }}>Messages</h3>
        {canWrite && !composing && (
          <button type="button" className="btn secondary small" disabled={!whatsappTo} aria-describedby={whatsappTo ? undefined : reasonId}
            onClick={() => { setComposing(true); setNotice(null); }}>Send WhatsApp</button>
        )}
      </div>
      {canWrite && !whatsappTo && <p id={reasonId} className="muted" style={{ fontSize: 13, margin: "4px 0 0" }}>No WhatsApp or mobile number on this lead.</p>}
      <div role="status" aria-live="polite">
        {notice && <p className={notice.failed ? "form-error" : "form-message"} style={{ margin: "6px 0 0", fontSize: 13 }}>{notice.text}</p>}
      </div>
      {composing && canSend && whatsappTo && (
        <WhatsAppComposer leadId={leadId} to={whatsappTo} onCancel={() => setComposing(false)}
          onRecorded={() => { setComposing(false); done("WhatsApp send recorded."); }} />
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
