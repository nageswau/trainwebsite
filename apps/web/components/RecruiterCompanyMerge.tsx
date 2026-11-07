"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useId, useRef, useState, type ReactNode } from "react";

import { sendJson, sendRequest } from "@/lib/apiErrors";
import { COMPANIES_PATH } from "@/lib/recruiterCompanies";
import {
  FIELD_LABEL, companyMergePath, companyMergeUrl, contactMergeUrl, movedText,
  type CompanyPreview, type ContactPreview, type MergeValues,
} from "@/lib/recruiterCompanyImport";
import { STATUS_LABEL, contactsOf, type Contact, type ContactList } from "@/lib/recruiterContacts";

// pob-006 (DEC-SCOPE-418 M5, C3): the merge screens, hrc-014's side-by-side comparison. Where both have a different value the user picks one; an empty value here is
// always filled from the duplicate. The server re-checks every rule.
const blank = (value: unknown) => value === null || value === undefined || value === "";
const shown = (value: unknown) => (blank(value) ? <span className="muted">—</span> : String(value));

function Compare({ caption, stays, merges, fields, a, b, useVictim, onPick, busy, extra }: {
  caption: string; stays: string; merges: string; fields: string[]; a: MergeValues; b: MergeValues; useVictim: string[]; onPick: (field: string, fromVictim: boolean) => void; busy: boolean; extra?: ReactNode;
}) {
  const id = useId();
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="table compact stack">
        <caption style={{ textAlign: "left", fontWeight: 600 }}>{caption}</caption>
        <thead>
          <tr><th scope="col">Field</th><th scope="col">{stays}</th><th scope="col">{merges}</th></tr>
        </thead>
        <tbody>
          {fields.filter((key) => !blank(a[key]) || !blank(b[key])).map((key) => {
            const label = FIELD_LABEL[key] ?? key;
            const choice = !blank(a[key]) && !blank(b[key]) && String(a[key]) !== String(b[key]);
            const fromVictim = useVictim.includes(key);
            const cell = (value: unknown, isVictim: boolean) => choice ? (
              <label style={{ display: "flex", gap: 6, alignItems: "baseline", overflowWrap: "anywhere" }}>
                <input type="radio" name={`${id}-${key}`} checked={fromVictim === isVictim} disabled={busy} aria-label={`Keep ${String(value)} for ${label}`} onChange={() => onPick(key, isVictim)} />
                {String(value)}
              </label>
            ) : <span style={{ overflowWrap: "anywhere" }}>{shown(value)}</span>;
            return (
              <tr key={key}>
                <th scope="row">{label}</th>
                <td data-label={stays}>{cell(a[key], false)}{!choice && blank(a[key]) && !blank(b[key]) && <span className="muted" style={{ fontSize: 12 }}> (filled from the duplicate)</span>}</td>
                <td data-label={merges}>{cell(b[key], true)}</td>
              </tr>
            );
          })}
          {extra}
        </tbody>
      </table>
    </div>
  );
}

function usePicks() {
  const [useVictim, setUseVictim] = useState<string[]>([]);
  const pick = (field: string, fromVictim: boolean) => setUseVictim((fields) => (fromVictim ? [...fields.filter((f) => f !== field), field] : fields.filter((f) => f !== field)));
  return { useVictim, pick, clear: () => setUseVictim([]) };
}

function Reason({ value, onChange, busy }: { value: string; onChange: (text: string) => void; busy: boolean }) {
  const id = useId();
  return (
    <div className="field" style={{ margin: 0, maxWidth: 640 }}>
      <label htmlFor={id}>Reason (optional)</label>
      <textarea id={id} rows={2} maxLength={500} value={value} disabled={busy} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

/** The company merge: `victimCode` from the link or the code form, then the comparison. */
export default function RecruiterCompanyMerge({ survivorId, victimCode }: { survivorId: string; victimCode?: string }) {
  const router = useRouter();
  const [code, setCode] = useState(victimCode ?? "");
  const [preview, setPreview] = useState<CompanyPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);
  const { useVictim, pick, clear } = usePicks();

  useEffect(() => {
    if (!victimCode) {
      setPreview(null);
      setLoadError("");
      return;
    }
    let live = true;
    setLoading(true);
    setLoadError("");
    setPreview(null);
    clear();
    void sendRequest(companyMergeUrl(survivorId, victimCode), { method: "GET" }).then((outcome) => {
      if (!live) return;
      setLoading(false);
      if (outcome.ok) setPreview(outcome.data as CompanyPreview);
      else setLoadError(outcome.message);
    });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `clear` is rebuilt each render and only resets the picks
  }, [survivorId, victimCode]);

  function compare(event: FormEvent) {
    event.preventDefault();
    const text = code.trim().toUpperCase();
    if (!text) return setLoadError("Enter the duplicate company's code, such as CMP-000123.");
    if (text === victimCode) return;
    router.push(companyMergePath(survivorId, text));
  }

  async function merge() {
    if (sending.current || !preview) return;
    const { survivor, victim } = preview;
    if (!window.confirm(`Merge ${victim.code} into ${survivor.code}? ${victim.code} is archived for good and cannot be restored.`)) return;
    sending.current = true;
    setBusy(true);
    setError("");
    const text = reason.trim();
    const outcome = await sendJson(companyMergeUrl(survivor.id), "POST", { victim_code: victim.code, use_victim: useVictim, ...(text ? { reason: text } : {}) });
    sending.current = false;
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    router.push(`${COMPANIES_PATH}/${encodeURIComponent(survivor.id)}?${new URLSearchParams({ merged: victim.code })}`);
  }

  const moved = preview ? movedText(preview.moved) : "";
  return (
    <section style={{ display: "grid", gap: 12 }}>
      <div className="portal-title">
        <div>
          <div className="eyebrow">Companies</div>
          <h2>{preview ? `Merge ${preview.victim.code} into ${preview.survivor.code}` : "Merge a duplicate company"}</h2>
          <p className="muted" style={{ margin: 0 }}>
            The company you came from stays. Everything recorded on the duplicate moves to it, and the duplicate is archived as merged for good.
          </p>
        </div>
      </div>
      <form className="form" onSubmit={compare} noValidate style={{ maxWidth: 420 }}>
        <div className="field">
          <label htmlFor="merge-code">Duplicate company&apos;s code</label>
          <input id="merge-code" value={code} maxLength={20} placeholder="CMP-000123" disabled={busy} onChange={(e) => setCode(e.target.value)} />
        </div>
        <button className="btn secondary" disabled={busy || loading}>{loading ? "Comparing…" : "Compare"}</button>
      </form>
      {loading && <p className="muted" role="status">Loading the comparison…</p>}
      {loadError && <p className="form-error" role="alert" style={{ margin: 0 }}>{loadError}</p>}
      {preview && (
        <>
          <p style={{ margin: 0 }}><strong>{preview.survivor.name}</strong> stays. <strong>{preview.victim.name}</strong> merges in.</p>
          <Compare
            caption="Compare the two companies" stays={`Stays (${preview.survivor.code})`} merges={`Merges in (${preview.victim.code})`} fields={preview.fields}
            a={preview.survivor.values} b={preview.victim.values} useVictim={useVictim} onPick={pick} busy={busy}
            extra={(
              <tr>
                <th scope="row">Recruiter</th>
                <td data-label="Stays">{shown(preview.survivor.assigned_recruiter)}</td>
                <td data-label="Merges in">{shown(preview.victim.assigned_recruiter)}</td>
              </tr>
            )}
          />
          <p style={{ margin: 0 }}>{moved ? `Moves to ${preview.survivor.code}: ${moved}.` : `${preview.victim.code} has no records to move.`}</p>
          {preview.survivor.assigned_recruiter && preview.victim.assigned_recruiter && preview.survivor.assigned_recruiter !== preview.victim.assigned_recruiter && (
            <p className="form-warning" style={{ margin: 0 }}>{preview.victim.assigned_recruiter} loses access to what moves unless they also handle {preview.survivor.code}.</p>
          )}
          {preview.blocked.map((text) => <p key={text} className="form-error" role="alert" style={{ margin: 0 }}>{text}</p>)}
          <Reason value={reason} onChange={setReason} busy={busy} />
          {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
        </>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }} aria-live="polite">
        {preview && (
          <button type="button" className="btn" disabled={busy || preview.blocked.length > 0} onClick={() => void merge()}>{busy ? "Merging…" : `Merge ${preview.victim.code}`}</button>
        )}
        <Link className="btn secondary" href={`${COMPANIES_PATH}/${encodeURIComponent(survivorId)}`}>Cancel</Link>
      </div>
    </section>
  );
}

/** The contact merge: choose which other contact of this company is the same person, then compare. */
export function RecruiterContactMerge({ companyId, survivorId }: { companyId: string; survivorId: string }) {
  const router = useRouter();
  const [others, setOthers] = useState<Contact[] | null>(null);
  const [victimId, setVictimId] = useState("");
  const [preview, setPreview] = useState<ContactPreview | null>(null);
  const [loadError, setLoadError] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);
  const { useVictim, pick, clear } = usePicks();
  const back = `${COMPANIES_PATH}/${encodeURIComponent(companyId)}`;

  useEffect(() => {
    let live = true;
    void sendRequest(contactsOf(encodeURIComponent(companyId)), { method: "GET" }).then((outcome) => {
      if (!live) return;
      if (outcome.ok) setOthers((outcome.data as ContactList).items.filter((c) => c.id !== survivorId));
      else setLoadError(outcome.message);
    });
    return () => { live = false; };
  }, [companyId, survivorId]);

  useEffect(() => {
    setPreview(null);
    setError("");
    clear();
    if (!victimId) return;
    let live = true;
    setLoadError("");
    void sendRequest(contactMergeUrl(survivorId, victimId), { method: "GET" }).then((outcome) => {
      if (!live) return;
      if (outcome.ok) setPreview(outcome.data as ContactPreview);
      else setLoadError(outcome.message);
    });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `clear` is rebuilt each render and only resets the picks
  }, [survivorId, victimId]);

  async function merge() {
    if (sending.current || !preview) return;
    if (!window.confirm(`Merge ${preview.victim.name} into ${preview.survivor.name}? This cannot be undone.`)) return;
    sending.current = true;
    setBusy(true);
    setError("");
    const text = reason.trim();
    const outcome = await sendJson(contactMergeUrl(survivorId), "POST", { victim_id: victimId, use_victim: useVictim, ...(text ? { reason: text } : {}) });
    sending.current = false;
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    router.push(`${back}?merged=contact`); // never the person's name in a URL
  }

  const moved = preview ? movedText(preview.moved) : "";
  return (
    <section style={{ display: "grid", gap: 12 }}>
      <div className="portal-title">
        <div>
          <div className="eyebrow">Contacts</div>
          <h2>{preview ? `Merge ${preview.victim.name} into ${preview.survivor.name}` : "Merge a duplicate contact"}</h2>
          <p className="muted" style={{ margin: 0 }}>The contact you came from stays. The duplicate&apos;s calls, messages, meetings and follow-ups move to them.</p>
        </div>
      </div>
      {loadError && <p className="form-error" role="alert" style={{ margin: 0 }}>{loadError}</p>}
      {!others && !loadError && <p className="muted" role="status">Loading the contacts…</p>}
      {others && others.length === 0 && <p className="muted">This company has no other contact to merge.</p>}
      {others && others.length > 0 && (
        <div className="field" style={{ margin: 0, maxWidth: 420 }}>
          <label htmlFor="merge-contact">Duplicate contact</label>
          <select id="merge-contact" value={victimId} disabled={busy} onChange={(e) => setVictimId(e.target.value)}>
            <option value="">Choose a contact</option>
            {others.map((c) => <option key={c.id} value={c.id}>{c.name}{c.mobile || c.email ? ` (${c.mobile ?? c.email})` : ""}</option>)}
          </select>
        </div>
      )}
      {preview && (
        <>
          <Compare
            caption="Compare the two contacts" stays={`Stays (${preview.survivor.name})`} merges={`Merges in (${preview.victim.name})`} fields={preview.fields}
            a={preview.survivor.values} b={preview.victim.values} useVictim={useVictim} onPick={pick} busy={busy}
            extra={(
              <tr>
                <th scope="row">Status</th>
                <td data-label="Stays">{STATUS_LABEL[preview.survivor.status as keyof typeof STATUS_LABEL] ?? preview.survivor.status}</td>
                <td data-label="Merges in">{STATUS_LABEL[preview.victim.status as keyof typeof STATUS_LABEL] ?? preview.victim.status}</td>
              </tr>
            )}
          />
          {preview.victim.status === "do_not_contact" && preview.survivor.status !== "do_not_contact" && (
            <p className="form-warning" style={{ margin: 0 }}>{preview.victim.name} asked not to be contacted, so {preview.survivor.name} becomes Do not contact too.</p>
          )}
          <p style={{ margin: 0 }}>{moved ? `Moves to ${preview.survivor.name}: ${moved}.` : `${preview.victim.name} has no records to move.`}</p>
          <Reason value={reason} onChange={setReason} busy={busy} />
          {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
        </>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }} aria-live="polite">
        {preview && <button type="button" className="btn" disabled={busy} onClick={() => void merge()}>{busy ? "Merging…" : "Merge contact"}</button>}
        <Link className="btn secondary" href={back}>Cancel</Link>
      </div>
    </section>
  );
}
