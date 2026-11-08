"use client";
import { type FormEvent, useEffect, useId, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { contactsOf, isContactList, type Contact } from "@/lib/recruiterContacts";
import { REQUIREMENTS_URL, type VendorRef } from "@/lib/recruiterRequirements";
import {
  CHANNELS, CONSENT_MAX, duplicatesOf, type Duplicate, isShareBody, needsContact, NOTE_MAX, type Share, type ShareChannel, SHARE_LIMIT, type ShareRecipient,
  SHARES_URL, VENDOR_DETAILS,
} from "@/lib/recruiterShares";

export type ShareCandidate = { id: string; name: string; code: string };
type Done = { share: Share; whatsappUrl: string | null };
type VendorDetail = "anonymised" | "full";

/** rec-019 (spec §5; S1-S5): share the selected candidates with the requirement's company -- channel, contact (only the company's active
 *  ones), an internal note. A repeat share comes back as a 409 listing who was already shared; "Share again" resends with `repeat`. A
 *  WhatsApp share is recorded first (its resume links only exist then) and the result offers wa.me. The API decides every rule.
 *  pob-011 (DEC-SCOPE-427 V4-V7): a requirement that came through a vendor can be shared with that vendor instead -- its own contacts, no
 *  Portal, anonymised by default; full details only with the candidates' consent (the API also checks the vendor's status, agreement and
 *  NDA). Without `companyId` and `vendor`, the requirement is read to find them. */
export default function RecruiterShareDialog({ requirement, companyId, vendor, candidates, onShared, onClose }: {
  requirement: { id: string; label: string }; companyId?: string; vendor?: VendorRef | null; candidates: ShareCandidate[];
  onShared: (share: Share) => void; onClose: () => void;
}) {
  const [company, setCompany] = useState<string | null>(companyId ?? null);
  const [vendorRef, setVendorRef] = useState<VendorRef | null | undefined>(vendor);
  const [recipient, setRecipient] = useState<ShareRecipient>("client");
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [contactsFailed, setContactsFailed] = useState(false);
  const [channel, setChannel] = useState<ShareChannel>("email");
  const [contactId, setContactId] = useState("");
  const [detail, setDetail] = useState<VendorDetail>("anonymised");
  const [consent, setConsent] = useState(false);
  const [consentReference, setConsentReference] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [repeats, setRepeats] = useState<{ message: string; duplicates: Duplicate[] } | null>(null);
  const [done, setDone] = useState<Done | null>(null);
  const id = useId();

  useEffect(() => { // Find Candidates knows only the requirement: it names the company (the contacts) and any vendor
    if (company && vendorRef !== undefined) return;
    const controller = new AbortController();
    fetch(`${REQUIREMENTS_URL}/${encodeURIComponent(requirement.id)}`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => {
        if (!body?.requirement?.company?.id) return setContactsFailed(true);
        setCompany(body.requirement.company.id);
        setVendorRef(body.requirement.via_vendor ?? null);
      })
      .catch(() => controller.signal.aborted || setContactsFailed(true));
    return () => controller.abort();
  }, [company, vendorRef, requirement.id]);

  const toVendor = recipient === "vendor";
  const target = toVendor ? vendorRef?.id ?? null : company;
  useEffect(() => {
    if (!target) return;
    const controller = new AbortController();
    setContacts(null);
    setContactsFailed(false);
    setContactId("");
    fetch(contactsOf(target), { signal: controller.signal })
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
  }, [target]);

  function chooseRecipient(next: ShareRecipient) {
    setRecipient(next);
    setRepeats(null);
    setFailure(null);
    if (next === "vendor" && channel === "portal") setChannel("email"); // a vendor has no employer portal
  }

  const channels = toVendor ? CHANNELS.filter((c) => c.key !== "portal") : CHANNELS;
  const contact = contacts?.find((c) => c.id === contactId) ?? null;
  const missing = needsContact(channel) && contact
    ? channel === "email" && !contact.email ? "This contact has no email address." : channel === "whatsapp" && !contact.mobile ? "This contact has no mobile number." : null
    : null;
  const tooMany = candidates.length > SHARE_LIMIT;
  const consentReady = !toVendor || detail === "anonymised" || (consent && consentReference.trim() !== "");
  const ready = candidates.length > 0 && !tooMany && (!needsContact(channel) || (!!contact && !missing)) && consentReady;

  async function submit(event: FormEvent | null, repeat = false) {
    event?.preventDefault();
    if (!ready || busy) return;
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(SHARES_URL, "POST", {
      requirement_id: requirement.id, candidate_ids: candidates.map((c) => c.id), channel,
      ...(contactId ? { contact_id: contactId } : {}),
      ...(note.trim() ? { note: note.trim() } : {}), ...(repeat ? { repeat: true } : {}),
      ...(toVendor ? { recipient: "vendor", detail } : {}),
      ...(toVendor && detail === "full" ? { consent_confirmed: true, consent_reference: consentReference.trim() } : {}),
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
          {done.share.contact ? ` with ${done.share.contact.name}` : ""}
          {done.share.recipient === "vendor" ? ` (vendor, ${(done.share.detail_label ?? done.share.detail ?? "").toLowerCase()})` : ""}.
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
      {vendorRef && (
        <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 4 }}>
          <legend style={{ fontWeight: 600, marginBottom: 4 }}>Share with</legend>
          <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <input type="radio" name={`${id}-recipient`} value="client" checked={!toVendor} onChange={() => chooseRecipient("client")} />
            <span>End client <span className="muted" style={{ fontSize: 13 }}>— the requirement&apos;s company</span></span>
          </label>
          <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <input type="radio" name={`${id}-recipient`} value="vendor" checked={toVendor} onChange={() => chooseRecipient("vendor")} />
            <span>Vendor: {vendorRef.name} <span className="muted" style={{ fontSize: 13 }}>— the requirement came through this vendor</span></span>
          </label>
        </fieldset>
      )}
      <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 4 }}>
        <legend style={{ fontWeight: 600, marginBottom: 4 }}>Share via</legend>
        {channels.map((c) => (
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
      {contactsFailed && <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>Unable to load the {toVendor ? "vendor" : "company"}&apos;s contacts.</p>}
      {toVendor && (
        <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 4 }}>
          <legend style={{ fontWeight: 600, marginBottom: 4 }}>What the vendor sees</legend>
          {VENDOR_DETAILS.map((d) => (
            <label key={d.key} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
              <input type="radio" name={`${id}-detail`} value={d.key} checked={detail === d.key} onChange={() => setDetail(d.key)} />
              <span>{d.label} <span className="muted" style={{ fontSize: 13 }}>— {d.hint}</span></span>
            </label>
          ))}
        </fieldset>
      )}
      {toVendor && detail === "full" && (
        <div style={{ display: "grid", gap: 6 }}>
          <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span>The candidates agreed to share their full details with this vendor</span>
          </label>
          <label htmlFor={`${id}-consent`} style={{ display: "grid", gap: 4 }}>
            How and when they agreed (required)
            <input id={`${id}-consent`} type="text" maxLength={CONSENT_MAX} value={consentReference} autoComplete="off" onChange={(e) => setConsentReference(e.target.value)}
              placeholder="For example: phone call on 8 Nov" />
          </label>
        </div>
      )}
      <label htmlFor={`${id}-note`} style={{ display: "grid", gap: 4 }}>
        Internal note (optional, never sent)
        <textarea id={`${id}-note`} rows={2} maxLength={NOTE_MAX} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        {!toVendor
          ? <>The company sees each candidate&apos;s profile summary and resume — never their phone number, email or salary.</>
          : detail === "anonymised"
            ? "The vendor sees each candidate's code and profile summary — no name, current company, contact details or resume."
            : "The vendor sees each candidate's name, email, mobile, profile summary and resume. The vendor's NDA must be on file."}
      </p>
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
