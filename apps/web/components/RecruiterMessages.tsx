"use client";
import { useEffect, useState } from "react";

import MessagesSection from "@/components/MessagesSection";
import { contactsOf, type ContactList } from "@/lib/recruiterContacts";
import { candidateMessagesUrl, companyMessagesUrl, recruiterTarget, type Party } from "@/lib/recruiterMessages";

type Source = { kind: "company"; companyId: string } | { kind: "candidate"; party: Party };

/** rec-026 (spec §5): the Messages section of a company page (to one of its active contacts, chosen in the section) or a candidate page.
 *  `canWrite` is the API's `can_edit` on a party that is not archived. The section itself (upc-012 shares it) is `MessagesSection`; this
 *  loads the company's active contacts, again after each send. */
export default function RecruiterMessages({ source, canWrite, onChanged }: { source: Source; canWrite: boolean; onChanged?: () => void }) {
  const [contacts, setContacts] = useState<Party[] | null>(source.kind === "candidate" ? [source.party] : null);
  const [version, setVersion] = useState(0);
  const companyId = source.kind === "company" ? source.companyId : null;

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
      listUrl={source.kind === "company" ? companyMessagesUrl(source.companyId) : candidateMessagesUrl(source.party.id)}
      parties={contacts}
      picker={source.kind === "company"}
      targetFor={recruiterTarget}
      canWrite={canWrite}
      noParties="Add an active contact to send a message."
      onChanged={() => {
        setVersion((n) => n + 1);
        onChanged?.();
      }}
    />
  );
}
