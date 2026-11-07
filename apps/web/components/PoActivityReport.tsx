"use client";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { formatDateTimeIn } from "@/lib/formatDate";
import { type Contacts, contactsUrl, rateText, type Report, reportUrl } from "@/lib/recruiterPoWork";

const NOTE_MAX = 2000;

// pob-009 T7/T8: one daily or weekly report -- the auto-computed counts (live while a draft, frozen once submitted), the response rate with
// the contacts behind it (AC1), the plan for a day, and the PO's note. `canSubmit` only for the PO's own draft; the API decides the rules.
export default function PoActivityReport({ report, canSubmit, recruiterId }: { report: Report; canSubmit: boolean; recruiterId?: string }) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [contacts, setContacts] = useState<Contacts | null>(null);
  const [drillError, setDrillError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const c = report.counts;

  async function submit() {
    if (inFlight.current) return;
    if (note.length > NOTE_MAX) return setError(`The note can be at most ${NOTE_MAX} characters.`);
    inFlight.current = true;
    setBusy(true);
    setError(null);
    const outcome = await sendJson(`${reportUrl(report.period, report.period_start)}/submit`, "POST", { note: note.trim() || null });
    inFlight.current = false;
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    router.refresh();
  }

  async function drill() {
    setDrillError(null);
    try {
      const response = await fetch(contactsUrl(report.period, report.period_start, recruiterId));
      if (!response.ok) throw new Error();
      setContacts(await response.json());
    } catch {
      setDrillError("Unable to load the contacts right now.");
    }
  }

  return (
    <div>
      <p>
        <span className={`badge ${report.status === "submitted" ? "success" : ""}`}>{report.status === "submitted" ? "Submitted" : "Draft — not submitted"}</span>
        {report.submitted_at && <span className="muted"> on {formatDateTimeIn(report.submitted_at, "Asia/Kolkata")}</span>}
        {report.status === "draft" && <span className="muted"> · figures are live until you submit</span>}
      </p>
      <div className="table-scroll" role="region" aria-label="Report figures" tabIndex={0}>
        <table className="table compact stack">
          <thead><tr><th scope="col">Figure</th><th scope="col">Count</th></tr></thead>
          <tbody>
            {report.kpis.map((k) => <tr key={k.key}><th scope="row">{k.label}</th><td>{c[k.key] ?? 0}</td></tr>)}
            <tr><th scope="row">Contacts reached</th><td>{c.contacts_reached ?? 0}</td></tr>
            <tr><th scope="row">Response rate</th><td>{rateText(c.response_rate)}</td></tr>
            {report.plan && <tr><th scope="row">Plan items done</th><td>{report.plan.done} of {report.plan.planned}</td></tr>}
          </tbody>
        </table>
      </div>
      <p className="muted" style={{ fontSize: 13 }}>Response rate = contacts reached in the period with a reply logged ÷ contacts reached.</p>
      <button className="btn secondary small" type="button" onClick={() => void drill()}>Show contacts reached</button>
      {drillError && <p className="form-error" role="alert">{drillError}</p>}
      {contacts && (contacts.items.length === 0 ? <p className="muted">No contact was reached in this period.</p> : (
        <div className="table-scroll" role="region" aria-label="Contacts reached" tabIndex={0} style={{ marginTop: 8 }}>
          <table className="table compact stack">
            <caption className="muted" style={{ textAlign: "left" }}>{contacts.responses} of {contacts.total} replied ({rateText(contacts.response_rate)})</caption>
            <thead><tr><th scope="col">Contact</th><th scope="col">Company</th><th scope="col">Outreach</th><th scope="col">Replied</th></tr></thead>
            <tbody>
              {contacts.items.map((row) => (
                <tr key={row.contact.id}>
                  <th scope="row">{row.contact.name}</th>
                  <td><a href={`/recruiter/companies/${row.company.id}`}>{row.company.name}</a></td>
                  <td>{row.outreach}</td>
                  <td>{row.replied ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      <section style={{ marginTop: 24 }} aria-labelledby="report-note">
        <h3 id="report-note">Notes</h3>
        {report.status === "submitted" || !canSubmit ? (
          <p style={{ whiteSpace: "pre-wrap" }}>{report.note ?? <span className="muted">{report.status === "submitted" ? "No note." : "Not submitted yet."}</span>}</p>
        ) : (
          <>
            <label htmlFor="report-note-text" className="visually-hidden">Notes for your Team Lead</label>
            <textarea id="report-note-text" rows={4} value={note} maxLength={NOTE_MAX} disabled={busy} placeholder="What went well, blockers, plans"
              onChange={(e) => setNote(e.target.value)} style={{ width: "100%" }} />
            <div className="actions">
              <button className="btn" type="button" disabled={busy} onClick={() => void submit()}>{busy ? "Submitting…" : "Submit to Team Lead"}</button>
              <span className="muted" style={{ fontSize: 13 }}>Submitting freezes these figures.</span>
            </div>
          </>
        )}
        {error && <p className="form-error" role="alert">{error}</p>}
      </section>
    </div>
  );
}
