"use client";
import { type FormEvent, useEffect, useId, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { contactsOf, isContactList, type Contact } from "@/lib/recruiterContacts";
import { REQUIREMENTS_URL } from "@/lib/recruiterRequirements";
import { CHANNELS, duplicatesOf, type Duplicate, isShareBody, needsContact, NOTE_MAX, type Share, type ShareChannel, SHARE_LIMIT, SHARES_URL } from "@/lib/recruiterShares";

export type ShareCandidate = { id: string; name: string; code: string };
type Done = { share: Share; whatsappUrl: string | null };

/** rec-019 (spec §5; S1-S5): share the selected candidates with the requirement's company -- channel, contact (only the company's active
 *  ones), an internal note. A repeat share comes back as a 409 listing who was already shared; "Share again" resends with `repeat`. A
 *  WhatsApp share is recorded first (its resume links only exist then) and the result offers wa.me. The API decides every rule. */
export default function RecruiterShareDialog({ requirement, companyId, candidates, onShared, onClose }: {
  requirement: { id: string; label: string }; companyId?: string; candidates: ShareCandidate[]; onShared: (share: Share) => void; onClose: () => void;
}) {
  const [company, setCompany] = useState<string | null>(companyId ?? null);
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [contactsFailed, setContactsFailed] = useState(false);
  const [channel, setChannel] = useState<ShareChannel>("email");
  const [contactId, setContactId] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [repeats, setRepeats] = useState<{ message: string; duplicates: Duplicate[] } | null>(null);
  const [done, setDone] = useState<Done | null>(null);
  const id = useId();

  useEffect(() => { // Find Candidates knows only the requirement: its company decides the contacts
    if (company) return;
    const controller = new AbortController();
    fetch(`${REQUIREMENTS_URL}/${encodeURIComponent(requirement.id)}`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => (body?.requirement?.company?.id ? setCompany(body.requirement.company.id) : setContactsFailed(true)))
      .catch(() => controller.signal.aborted || setContactsFailed(true));
    return () => controller.abort();
  }, [company, requirement.id]);

  useEffect(() => {
    if (!company) return;
    const controller = new AbortController();
    fetch(contactsOf(company), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => {
        if (!isContactList(body)) return setContactsFailed(true);
        const active = body.items.filter((c) => c.active);
        setContacts(active);
        const primary = active.find((c) => c.is_primary) ?? active[0];
        if (primary) setContactId((current) => current || primary.id);
      })
      .catch(() => controller.signal.aborted || setContactsFailed(true));
    return () => controller.abort();
  }, [company]);

  const contact = contacts?.find((c) => c.id === contactId) ?? null;
  const missing = needsContact(channel) && contact
    ? channel === "email" && !contact.email ? "This contact has no email address." : channel === "whatsapp" && !contact.mobile ? "This contact has no mobile number." : null
    : null;
  const tooMany = candidates.length > SHARE_LIMIT;
  const ready = candidates.length > 0 && !tooMany && (!needsContact(channel) || (!!contact && !missing));

  async function submit(event: FormEvent | null, repeat = false) {
    event?.preventDefault();
    if (!ready || busy) return;
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(SHARES_URL, "POST", {
      requirement_id: requirement.id, candidate_ids: candidates.map((c) => c.id), channel,
      ...(contactId ? { contact_id: contactId } : {}),
      ...(note.trim() ? { note: note.trim() } : {}), ...(repeat ? { repeat: true } : {}),
    });
    setBusy(false);
    if (outcome.ok && isShareBody(outcome.data)) {
      setRepeats(null);
      setDone({ share: outcome.data.share, whatsappUrl: outcome.data.whatsapp_url });
      onShared(outcome.data.share);
      if (outcome.data.whatsapp_url) window.open(outcome.data.whatsapp_url, "_blank", "noopener,noreferrer");
      return;
    }
    const duplicate = !outcome.ok && outcome.status === 409 ? duplicatesOf(outcome.detail) : null;
    if (duplicate) setRepeats(duplicate);
    else setFailure(outcome.ok ? "Unable to share the profiles." : outcome.message);
  }

  const count = `${candidates.length} profile${candidates.length === 1 ? "" : "s"}`;
  if (done) {
    const items = done.share.items.length;
    return (
      <div className="action-card" role="region" aria-label="Profiles shared" style={{ gap: 8 }}>
        <p className="form-message" role="status" style={{ margin: 0 }}>
          Shared {items} profile{items === 1 ? "" : "s"} for {requirement.label} by {done.share.channel_label}
          {done.share.contact ? ` with ${done.share.contact.name}` : ""}.
          {done.share.channel === "email" && " The email is queued."}
        </p>
        <div className="actions">
          {done.whatsappUrl && <a className="btn small" href={done.whatsappUrl} target="_blank" rel="noopener noreferrer">Open WhatsApp<span className="visually-hidden"> (opens in a new tab)</span></a>}
          <button type="button" className="btn secondary small" onClick={onClose}>Close</button>
        </div>
      </div>
    );
  }
  return (
    <form onSubmit={(e) => void submit(e)} className="action-card" style={{ gap: 10 }} aria-label={`Share ${count}`}>
      <h4 style={{ margin: 0 }}>Share {count} for {requirement.label}</h4>
      <p className="muted" style={{ margin: 0, fontSize: 13, overflowWrap: "anywhere" }}>
        {candidates.map((c) => `${c.name} (${c.code})`).join(", ")}
      </p>
      {tooMany && <p className="form-error" role="alert" style={{ margin: 0 }}>Share at most {SHARE_LIMIT} candidates at a time.</p>}
      <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 4 }}>
        <legend style={{ fontWeight: 600, marginBottom: 4 }}>Share via</legend>
        {CHANNELS.map((c) => (
          <label key={c.key} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <input type="radio" name={`${id}-channel`} value={c.key} checked={channel === c.key} onChange={() => { setChannel(c.key); setRepeats(null); }} />
            <span>{c.label} <span className="muted" style={{ fontSize: 13 }}>— {c.hint}</span></span>
          </label>
        ))}
      </fieldset>
      <label htmlFor={`${id}-contact`} style={{ display: "grid", gap: 4 }}>
        Contact{needsContact(channel) ? "" : " (optional)"}
        <select id={`${id}-contact`} value={contactId} required={needsContact(channel)} disabled={contacts === null} onChange={(e) => setContactId(e.target.value)}
          aria-describedby={missing ? `${id}-missing` : undefined}>
          <option value="">{contacts === null ? (contactsFailed ? "Contacts unavailable" : "Loading contacts…") : contacts.length ? "Choose a contact" : "No active contacts"}</option>
          {contacts?.map((c) => <option key={c.id} value={c.id}>{c.name}{c.designation ? ` — ${c.designation}` : ""}</option>)}
        </select>
      </label>
      {missing && <p id={`${id}-missing`} className="form-error" style={{ margin: 0, fontSize: 13 }}>{missing}</p>}
      {contactsFailed && <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>Unable to load the company&apos;s contacts.</p>}
      <label htmlFor={`${id}-note`} style={{ display: "grid", gap: 4 }}>
        Internal note (optional, never sent)
        <textarea id={`${id}-note`} rows={2} maxLength={NOTE_MAX} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>The company sees each candidate&apos;s profile summary and resume — never their phone number, email or salary.</p>
      {failure && <p className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
      {repeats && (
        <div role="alert" className="form-error" style={{ margin: 0, display: "grid", gap: 6 }}>
          <span>{repeats.message}</span>
          <span style={{ overflowWrap: "anywhere" }}>{repeats.duplicates.map((d) => `${d.name} (${d.code})`).join(", ")}</span>
          <span><button type="button" className="btn small" disabled={busy} onClick={() => void submit(null, true)}>Share again</button></span>
        </div>
      )}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy || !ready}>
          {busy ? "Sharing…" : channel === "whatsapp" ? "Record and open WhatsApp" : `Share ${count}`}
        </button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onClose}>Cancel</button>
      </div>
    </form>
  );
}
