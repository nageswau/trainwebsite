"use client";

import { FormEvent, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";

export const STAFF_URL = "/api/v1/workflows/overseas/agent/team/staff";

// Browser QA-05/QA-06: how the staff screens word a failed request. A server error (5xx) carries no useful detail, so it says to
// retry; a dropped connection only promises a kept entry where something was typed (add / edit), not for a button action.
export function staffFailure(outcome: { message: string; status?: number }, keepsEntry: boolean): string {
  if (outcome.status === undefined) return keepsEntry ? outcome.message : "Couldn't reach the server. Check your connection and try again.";
  if (outcome.status >= 500) return "The server couldn't complete this. Please try again in a moment.";
  return outcome.message;
}

type Created = { member: { code: string; email: string }; email_status: string };

// AGN-002 (DEC-SCOPE-040 S3/S4): a Master adds a staff login. The staff member sets their own password from the emailed link;
// the Master never sees it. The entry is kept on any failure so it can be corrected and re-sent.
export default function AgentStaffCreateForm({ onCreated }: { onCreated: () => void }) {
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const inFlight = useRef(false);
  const messageRef = useRef<HTMLDivElement>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setSending(true);
    setMessage(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    const phone = String(data.get("phone") ?? "").trim();
    const outcome = await sendJson(STAFF_URL, "POST", { full_name: String(data.get("full_name") ?? ""), email: String(data.get("email") ?? ""), phone: phone || null });
    inFlight.current = false;
    setSending(false);
    if (!outcome.ok) {
      setMessage({ text: staffFailure(outcome, true), failed: true });
    } else {
      const { member, email_status } = outcome.data as unknown as Created;
      setMessage({
        text: email_status === "sent" ? `${member.code} created. A set-password link was emailed to ${member.email}.` : `${member.code} created, but the email was not delivered. Use Reset to send a new link.`,
        failed: false,
      });
      form.reset();
      onCreated();
    }
    messageRef.current?.focus();
  }

  return (
    <form className="form" onSubmit={submit} aria-label="Add a staff member">
      <h4>Add staff</h4>
      <div className="field"><label htmlFor="staff-full-name">Full name</label><input id="staff-full-name" name="full_name" maxLength={160} required autoComplete="off" /></div>
      <div className="field"><label htmlFor="staff-email">Email</label><input id="staff-email" name="email" type="email" maxLength={320} required autoComplete="off" /></div>
      <div className="field"><label htmlFor="staff-phone">Phone (optional)</label><input id="staff-phone" name="phone" type="tel" maxLength={40} autoComplete="off" /></div>
      <button className="btn" disabled={sending}>{sending ? "Adding…" : "Add staff"}</button>
      <div ref={messageRef} tabIndex={-1} className={message ? (message.failed ? "form-error" : "form-message") : undefined} role="status" aria-live="polite" style={message ? { marginTop: 8, overflowWrap: "anywhere" } : undefined}>
        {message?.text}
      </div>
    </form>
  );
}
