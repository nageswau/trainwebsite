"use client";
import { useEffect, useState } from "react";

import MessagesSection, { type MessageLine } from "@/components/MessagesSection";
import { sendJson } from "@/lib/apiErrors";
import { contactsOf, type ContactList } from "@/lib/recruiterContacts";
import { candidateMessagesUrl, companyMessagesUrl, MESSAGES_URL, recruiterTarget, type Party } from "@/lib/recruiterMessages";

type Source = { kind: "company"; companyId: string } | { kind: "candidate"; party: Party };

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

/** rec-026 (spec §5): the Messages section of a company page (to one of its active contacts, chosen in the section) or a candidate page.
 *  `canWrite` is the API's `can_edit` on a party that is not archived. The section itself (upc-012 shares it) is `MessagesSection`; this
 *  loads the company's active contacts, again after each send. pob-005: a writer can log a contact's reply on a message. */
export default function RecruiterMessages({ source, canWrite, onChanged }: { source: Source; canWrite: boolean; onChanged?: () => void }) {
  const [contacts, setContacts] = useState<Party[] | null>(source.kind === "candidate" ? [source.party] : null);
  const [version, setVersion] = useState(0);
  const companyId = source.kind === "company" ? source.companyId : null;

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
      listUrl={source.kind === "company" ? companyMessagesUrl(source.companyId) : candidateMessagesUrl(source.party.id)}
      parties={contacts}
      picker={source.kind === "company"}
      targetFor={recruiterTarget}
      canWrite={canWrite}
      noParties="Add an active contact to send a message."
      itemAction={(message, done) =>
        canWrite && message.contact && !message.replied_at ? <LogReply message={message} done={done} /> : null
      }
      onChanged={() => {
        setVersion((n) => n + 1);
        onChanged?.();
      }}
    />
  );
}
