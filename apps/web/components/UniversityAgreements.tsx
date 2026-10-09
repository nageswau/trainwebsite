"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, type ReactNode, useRef, useState } from "react";

import AgreementForm from "@/components/AgreementForm";
import LocalTime from "@/components/LocalTime";
import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import { type Agreement, type AgreementOptions, agreementUrl, dateText, EXCLUSIVITY, expiryText, statusLabel } from "@/lib/universityAgreements";
import { documentFileUrl } from "@/lib/universityDocuments";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// upc-014 (§13): the university page's Agreements section. One card per agreement (number, type, status -- Expiring/Expired come from
// the API, AG4), its 17 fields and history in <details>, and only the moves the API offers (`moves`, `permissions`). Every success
// re-reads the page (router.refresh). Texts are data only.
const SAVE_FAILED = "The change could not be saved. Try again.";

function plusDays(value: string, days: number): string {
  const d = new Date(`${value}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function Facts({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl style={{ display: "grid", gridTemplateColumns: "minmax(120px, max-content) 1fr", gap: "6px 16px", margin: "8px 0 0" }}>
      {rows.map(([term, value]) => [
        <dt key={`${term}-t`} className="muted">{term}</dt>,
        <dd key={`${term}-d`} style={{ margin: 0, overflowWrap: "anywhere", whiteSpace: "pre-line" }}>{value || "—"}</dd>,
      ])}
    </dl>
  );
}

function Details({ a }: { a: Agreement }) {
  const signed = (who: ReactNode, on: string | null) => (who ? <>{who}{on ? `, ${dateText(on)}` : ""}</> : null);
  return (
    <Facts rows={[
      ["MoU number", a.mou_number],
      ["University", `${a.university.name} (${a.university.university_code})`],
      ["Agreement type", a.type_label],
      ["Start date", dateText(a.start_date)],
      ["Expiry date", dateText(a.expiry_date)],
      ["Renewal date", a.renewal_date && dateText(a.renewal_date)],
      ["Commercial terms", a.commercial_terms],
      ["Exclusivity", EXCLUSIVITY[a.exclusivity] ?? a.exclusivity],
      ["Territory", a.territory],
      ["Student recruitment rights", a.recruitment_rights],
      ["Courses covered", a.all_courses ? "All courses" : a.courses.map((c) => `${c.title} (${c.level})`).join(", ")],
      ["Countries covered", a.countries.map((c) => c.name).join(", ")],
      ["Payment terms", a.payment_terms],
      ["Marketing rights", a.marketing_rights],
      ["Agreement document", a.document && (
        <a href={documentFileUrl({ id: a.document.id, university: a.university }, a.document.current_version)} download>
          {a.document.title} (version {a.document.current_version})
        </a>
      )],
      ["Signed by EduSphere", signed(a.edusphere_signatory?.full_name, a.edusphere_signed_on)],
      ["Signed by the university", signed(a.university_signatory_name, a.university_signed_on)],
    ]} />
  );
}

function History({ a }: { a: Agreement }) {
  const events = a.events ?? [];
  return (
    <details>
      <summary>History ({events.length})</summary>
      <ol className="list-clean" style={{ marginTop: 6, display: "grid", gap: 4 }}>
        {[...events].reverse().map((e, i) => (
          <li key={`${e.created_at}-${i}`} style={{ overflowWrap: "anywhere" }}>
            <LocalTime value={e.created_at} /> · {e.actor.full_name}:{" "}
            {e.kind === "create" ? "created the draft" : e.kind === "renew" ? "started this renewal"
              : e.kind === "update" ? `edited ${e.changed.join(", ").replaceAll("_", " ")}`
              : `${statusLabel(e.from_status ?? "")} → ${statusLabel(e.to_status)}`}
            {e.note && <span className="muted"> — {e.note}</span>}
          </li>
        ))}
      </ol>
    </details>
  );
}

function MoveForm({ a, label, busy, onSend, onCancel }: { a: Agreement; label: string; busy: boolean; onSend: (note: string | null) => void; onCancel: () => void }) {
  const [note, setNote] = useState("");
  const id = `ag-${a.id}-note`;
  return (
    <form onSubmit={(e: FormEvent) => { e.preventDefault(); onSend(note.trim() || null); }} aria-label={`Move ${a.mou_number} to ${label}`} aria-busy={busy}
      style={{ display: "grid", gap: 8, marginTop: 8 }}>
      <div className="field" style={{ marginBottom: 0 }}>
        <label htmlFor={id}>Note (optional)</label>
        <textarea id={id} rows={2} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} autoFocus />
      </div>
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : `Move to ${label}`}</button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}

function RenewForm({ a, busy, onSend, onCancel }: { a: Agreement; busy: boolean; onSend: (body: Record<string, string>) => void; onCancel: () => void }) {
  const length = Math.round((Date.parse(a.expiry_date) - Date.parse(a.start_date)) / 86_400_000);
  const [start, setStart] = useState(() => plusDays(a.expiry_date, 1));
  const [expiry, setExpiry] = useState(() => plusDays(plusDays(a.expiry_date, 1), length));
  const [error, setError] = useState<string | null>(null);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!start || !expiry) return setError("Enter the start and expiry dates.");
    if (expiry <= start) return setError("The expiry date must be after the start date.");
    setError(null);
    onSend({ start_date: start, expiry_date: expiry });
  };
  return (
    <form onSubmit={submit} aria-label={`Renew ${a.mou_number}`} aria-busy={busy} style={{ display: "grid", gap: 8, marginTop: 8 }}>
      <p className="muted" style={{ margin: 0 }}>The renewal starts as a draft with these terms copied; {a.mou_number} becomes Renewed when the renewal is signed.</p>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor={`ag-${a.id}-renew-start`}>New start date</label>
          <input id={`ag-${a.id}-renew-start`} type="date" value={start} onChange={(e) => setStart(e.target.value)} autoFocus />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor={`ag-${a.id}-renew-expiry`}>New expiry date</label>
          <input id={`ag-${a.id}-renew-expiry`} type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} />
        </div>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Start renewal"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}

export default function UniversityAgreements({ universityId, agreements, options, canManage }: {
  universityId: string; agreements: Agreement[]; options: AgreementOptions | null; canManage: boolean;
}) {
  const router = useRouter();
  const sending = useRef(false);
  const [open, setOpen] = useState<string | null>(null); // "new", "<id>:edit", "<id>:renew", "<id>:move:<status>", or null
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const addId = `uni-${universityId}-add-agreement`;

  const done = (message: string) => {
    setOpen(null);
    setFailure(null);
    setNotice(message);
    focus(addId, "uni-agreements"); // the control that had focus is gone
    router.refresh();
  };
  async function run(request: () => Promise<SendOutcome>, message: string) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setFailure(null);
    setNotice(null);
    const outcome = await request();
    sending.current = false;
    setBusy(false);
    if (outcome.ok) return done(message);
    // A response without a readable detail (e.g. a 500) gets a plain sentence; a dropped request keeps the shared NOT_COMPLETED text.
    setFailure(outcome.status !== undefined && outcome.detail === undefined ? SAVE_FAILED : outcome.message);
  }
  const show = (key: string | null) => {
    setOpen(key);
    setFailure(null);
    setNotice(null);
  };

  return (
    <section className="action-card wide" aria-labelledby="uni-agreements">
      <h3 id="uni-agreements" tabIndex={-1}>Agreements</h3>
      {agreements.length === 0 && open !== "new" && <p className="muted">No agreements recorded yet.</p>}
      {agreements.length > 0 && (
        <ul aria-label="Agreements" style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12 }}>
          {agreements.map((a) => {
            const expiry = expiryText(a);
            const editable = a.permissions.can_edit_terms || a.permissions.can_edit_signing;
            return (
              <li key={a.id} className="card" style={{ padding: 14, display: "grid", gap: 6 }}>
                <p style={{ margin: 0, fontWeight: 800, display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                  {a.mou_number}
                  <span className="badge">{a.type_label}</span>
                  <span className="badge">{a.status_label}</span>
                  {expiry && <span className="badge">{expiry}</span>}
                </p>
                <p className="muted" style={{ margin: 0, overflowWrap: "anywhere" }}>
                  {dateText(a.start_date)} – {dateText(a.expiry_date)} · {EXCLUSIVITY[a.exclusivity] ?? a.exclusivity}{a.territory ? ` · ${a.territory}` : ""}
                </p>
                {(a.previous || a.renewed_by) && (
                  <p style={{ margin: 0 }}>
                    {a.previous && <>Renewal of {a.previous.mou_number} ({statusLabel(a.previous.effective_status)}). </>}
                    {a.renewed_by && <>Renewed by {a.renewed_by.mou_number} ({statusLabel(a.renewed_by.effective_status)}).</>}
                  </p>
                )}
                <details>
                  <summary>Agreement details<span className="visually-hidden"> of {a.mou_number}</span></summary>
                  <Details a={a} />
                </details>
                <History a={a} />
                {(a.moves.length > 0 || editable || a.permissions.can_renew) && (
                  <div className="actions" style={{ marginTop: 4 }}>
                    {a.moves.map((m) => (
                      <button key={m.to_status} type="button" className="btn secondary small" onClick={() => show(`${a.id}:move:${m.to_status}`)} disabled={busy}>
                        Move to {m.label}<span className="visually-hidden"> ({a.mou_number})</span>
                      </button>
                    ))}
                    {editable && options && (
                      <button type="button" className="btn secondary small" onClick={() => show(`${a.id}:edit`)} disabled={busy}>
                        Edit<span className="visually-hidden"> {a.mou_number}</span>
                      </button>
                    )}
                    {a.permissions.can_renew && (
                      <button type="button" className="btn secondary small" onClick={() => show(`${a.id}:renew`)} disabled={busy}>
                        Renew<span className="visually-hidden"> {a.mou_number}</span>
                      </button>
                    )}
                  </div>
                )}
                {a.moves.map((m) => open === `${a.id}:move:${m.to_status}` && (
                  <MoveForm key={m.to_status} a={a} label={m.label} busy={busy} onCancel={() => show(null)}
                    onSend={(note) => void run(() => sendJson(agreementUrl(a.id, "/status"), "POST", { from_status: a.status, to_status: m.to_status, note }), `${a.mou_number} moved to ${m.label}.`)} />
                ))}
                {open === `${a.id}:edit` && options && (
                  <div style={{ marginTop: 8 }}>
                    <AgreementForm universityId={universityId} options={options} agreement={a} canTerms={a.permissions.can_edit_terms}
                      canSigning={a.permissions.can_edit_signing} onSaved={done} onCancel={() => show(null)} />
                  </div>
                )}
                {open === `${a.id}:renew` && (
                  <RenewForm a={a} busy={busy} onCancel={() => show(null)}
                    onSend={(body) => void run(() => sendJson(agreementUrl(a.id, "/renew"), "POST", body), `Renewal of ${a.mou_number} started as a draft.`)} />
                )}
              </li>
            );
          })}
        </ul>
      )}
      {canManage && options && (open === "new" ? (
        <div style={{ marginTop: 12 }}>
          <AgreementForm universityId={universityId} options={options} onSaved={done} onCancel={() => show(null)} />
        </div>
      ) : (
        <div style={{ marginTop: 12 }}>
          <button id={addId} type="button" className="btn secondary small" onClick={() => show("new")} disabled={busy}>New agreement</button>
        </div>
      ))}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {notice && <p className="muted" role="status">{notice}</p>}
    </section>
  );
}
