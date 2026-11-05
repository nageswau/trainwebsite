"use client";
import { useEffect, useState } from "react";

import MessagesSection from "@/components/MessagesSection";
import { contactsOf, type ContactList } from "@/lib/recruiterContacts";
import { candidateMessagesUrl, companyMessagesUrl, recruiterTarget, type MessageContext, type Party } from "@/lib/recruiterMessages";

/** pob-023 (G12): a requirement page writes to its company's contacts with the requirement as context; an interview writes to its
 *  candidate with the interview as context. */
type Source =
  | { kind: "company"; companyId: string }
  | { kind: "requirement"; companyId: string; jobId: string }
  | { kind: "candidate"; party: Party; context?: MessageContext };

/** rec-026 (spec §5): the Messages section of a company page (to one of its active contacts, chosen in the section) or a candidate page.
 *  `canWrite` is the API's `can_edit` on a party that is not archived. The section itself (upc-012 shares it) is `MessagesSection`; this
 *  loads the company's active contacts, again after each send. pob-023: LinkedIn and calling copy mode, and a context record. */
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
      .then((list: ContactList) => setContacts(list.items.filter((c) => c.active).map((c): Party => ({ kind: "contact", id: c.id, name: c.name, whatsappTo: c.whatsapp_to ?? null, email: c.email }))))
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
      onChanged={() => {
        setVersion((n) => n + 1);
        onChanged?.();
      }}
    />
  );
}
