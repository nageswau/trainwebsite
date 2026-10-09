"use client";
import { useRouter } from "next/navigation";
import { useMemo } from "react";

import MessagesSection from "@/components/MessagesSection";
import { contactTarget, universityMessagesUrl } from "@/lib/partnershipComms";
import type { Party } from "@/lib/recruiterMessages";

type ContactRef = { id: string; name: string; email: string | null; whatsapp_to?: string | null };

/** upc-012 (UC5-UC9; AC1, AC2): the Messages section of a university -- rec-026's section with the university's contacts as recipients.
 *  `canWrite` is the API's `can_edit_contacts`. Each send re-reads the page, so the contacts' last interaction moves. */
export default function UniversityMessages({ universityId, contacts, canWrite }: { universityId: string; contacts: ContactRef[]; canWrite: boolean }) {
  const router = useRouter();
  const parties = useMemo(
    () => contacts.map((c): Party => ({ kind: "contact", id: c.id, name: c.name, whatsappTo: c.whatsapp_to ?? null, email: c.email })),
    [contacts],
  );
  return (
    <MessagesSection listUrl={universityMessagesUrl(universityId)} parties={parties} picker targetFor={(party) => contactTarget(party.id)}
      canWrite={canWrite} noParties="Add a contact to send a message." onChanged={() => router.refresh()} wide />
  );
}
