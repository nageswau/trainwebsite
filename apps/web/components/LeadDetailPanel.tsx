"use client";

import { type FormEvent, useEffect, useState } from "react";

import { LeadStageControl } from "@/components/AdminLeadStage";
import LeadAppointmentsSection from "@/components/LeadAppointmentsSection";
import LeadFollowUps from "@/components/LeadFollowUps";
import LeadQualificationForm from "@/components/LeadQualificationForm";
import ProductOptions from "@/components/TelecallerProductOptions";
import { isRequestBody, sendJson, type Page } from "@/lib/apiErrors";
import { formatDate } from "@/lib/formatDate";
import { isClosed, stageLabel } from "@/lib/leadStages";
import { SOURCE_LABEL, activeProducts, getPage, type Product } from "@/lib/telecallerCatalogue";
import { SCRIPTS_URL, type Script } from "@/lib/telecallerContent";
import {
  PRIORITIES, PRIORITY_LABEL, TIMELINE_LIMIT, leadUrl, moveStage, telHref, type Priority, type TelecallerLeadDetail, type TimelineRow,
} from "@/lib/telecallerLeads";

type Notice = { text: string; failed: boolean } | null;
// D2: the contact fields a lead edit may change; lengths are the `enquiries` columns' (the API enforces them).
const FIELDS = [
  { key: "name", label: "Student name", type: "text", max: 160, required: true },
  { key: "email", label: "Email", type: "email", max: 255, required: true },
  { key: "phone", label: "Mobile number", type: "tel", max: 40, required: false },
  { key: "whatsapp_number", label: "WhatsApp number", type: "tel", max: 40, required: false },
  { key: "city", label: "City", type: "text", max: 120, required: false },
  { key: "state", label: "State", type: "text", max: 120, required: false },
] as const;

function NoticeLine({ notice }: { notice: Notice }) {
  if (!notice) return null;
  return <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: "6px 0 0", fontSize: 13 }}>{notice.text}</p>;
}

const show = (value: string | number | null | undefined, empty = "—") => (value === null || value === undefined || value === "" ? <span className="muted">{empty}</span> : value);

/** tel-008 (spec §3, D2): the contact details form. Only changed values are sent (blank optional text clears it); the API validates. */
function DetailsForm({ lead, onSaved, onCancel }: { lead: TelecallerLeadDetail; onSaved: (lead: TelecallerLeadDetail) => void; onCancel: () => void }) {
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries([...FIELDS.map(({ key }) => [key, lead[key] ?? ""]), ["product_id", lead.product?.id ?? ""]]),
  );
  const [products, setProducts] = useState<Product[]>([]);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    activeProducts(controller.signal).then(setProducts).catch(() => undefined); // a failed picker keeps the current product only
    return () => controller.abort();
  }, []);

  async function save(event: FormEvent) {
    event.preventDefault();
    const changes: Record<string, string | null> = {};
    for (const { key, required } of FIELDS) {
      const text = values[key].trim();
      if (text !== (lead[key] ?? "")) changes[key] = text || (required ? "" : null);
    }
    if (values.product_id !== (lead.product?.id ?? "")) changes.product_id = values.product_id || null;
    if (Object.keys(changes).length === 0) return onCancel();
    setBusy(true);
    const outcome = await sendJson(leadUrl(lead.id), "PATCH", changes);
    setBusy(false);
    if (!outcome.ok) return setNotice({ text: outcome.message, failed: true });
    if (!isRequestBody(outcome.data)) return setNotice({ text: "Unable to save the details.", failed: true });
    onSaved(outcome.data as unknown as TelecallerLeadDetail);
  }

  // the lead's product stays choosable even when it is no longer active (deactivated products are not in the picker)
  const current = lead.product && !products.some((p) => p.id === lead.product?.id) ? lead.product : null;
  return (
    <form onSubmit={save} noValidate style={{ display: "grid", gap: 8, marginTop: 8 }}>
      <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))" }}>
        {FIELDS.map(({ key, label, type, max, required: always }) => {
          const required = always && (key !== "email" || !!lead.email); // tel-005 I1: a lead may have a mobile only
          return (
          <div className="field" key={key}>
            <label htmlFor={`lead-${key}`}>{label}</label>
            <input id={`lead-${key}`} type={type} maxLength={max} aria-required={required || undefined} value={values[key]} disabled={busy}
              onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))} />
          </div>
          );
        })}
        <div className="field">
          <label htmlFor="lead-product_id">Product interest</label>
          <select id="lead-product_id" value={values.product_id} disabled={busy} onChange={(e) => setValues((v) => ({ ...v, product_id: e.target.value }))}>
            <option value="">No product</option>
            {current && <option value={current.id}>{current.name}</option>}
            <ProductOptions products={products} />
          </select>
        </div>
      </div>
      <NoticeLine notice={notice} />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save details"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

/** tel-012 C2 (inherited): the active call script of the lead's product -- at most one per product (tel-012 C3). Re-read whenever the
 *  product changes; a failed read is said in place and never blocks the rest of the page. */
function LeadScriptPanel({ product }: { product: { id: string; name: string } | null }) {
  // the read's product travels with its result, so a result for an earlier product is never shown as the current one's
  const [state, setState] = useState<{ productId: string; script: Script | null | "failed" } | null>(null);
  const productId = product?.id ?? null;
  useEffect(() => {
    if (!productId) return;
    const controller = new AbortController();
    getPage<Script>(`${SCRIPTS_URL}?${new URLSearchParams({ product_id: productId, active: "true", limit: "1" })}`, controller.signal)
      .then((page) => setState({ productId, script: page.items[0] ?? null }))
      .catch(() => controller.signal.aborted || setState({ productId, script: "failed" }));
    return () => controller.abort();
  }, [productId]);

  let body: React.ReactNode;
  if (!product) body = <p className="muted" style={{ fontSize: 13 }}>Set the lead&apos;s product interest to see its call script.</p>;
  else if (state === null || state.productId !== product.id) body = <p className="muted" role="status" style={{ fontSize: 13 }}>Loading the call script…</p>;
  else if (state.script === "failed") body = <p className="form-error" style={{ fontSize: 13 }}>Unable to load the call script.</p>;
  else if (!state.script) body = <p className="muted" style={{ fontSize: 13 }}>No active call script for {product.name} yet.</p>;
  else body = (
    <>
      <p style={{ margin: "6px 0 0" }}><strong>{state.script.name}</strong></p>
      <ol aria-label="Call script steps" style={{ margin: "6px 0 0", paddingLeft: 18, display: "grid", gap: 4 }}>
        {state.script.steps.map((step, i) => (
          <li key={i}>
            <strong>{step.title}</strong>
            {step.notes && <div className="muted" style={{ fontSize: 13, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{step.notes}</div>}
          </li>
        ))}
      </ol>
    </>
  );
  return (
    <section aria-labelledby="lead-script-heading">
      <h3 id="lead-script-heading" style={{ margin: 0 }}>Call script</h3>
      {body}
    </section>
  );
}

/** tel-008 (spec §3; AC3, AC4; D1, D4): one lead -- the EVID-019 §2 fields, Call, the stage control, the priority (§8) and the activity
 *  list (stage + priority changes, W1). `read_only` (handed over to a counselor) shows the lead without any control. */
export default function LeadDetailPanel({ initial, timeline, canReopen }: { initial: TelecallerLeadDetail; timeline: Page<TimelineRow> | null; canReopen: boolean }) {
  const [lead, setLead] = useState(initial);
  const [activity, setActivity] = useState(timeline);
  const [priority, setPriority] = useState<Priority>(initial.priority);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [priorityNotice, setPriorityNotice] = useState<Notice>(null);
  const [detailsNotice, setDetailsNotice] = useState<Notice>(null);
  const [stageNotice, setStageNotice] = useState<Notice>(null);
  const call = telHref(lead.phone);

  const reloadActivity = () =>
    getPage<TimelineRow>(leadUrl(lead.id, `/timeline?limit=${TIMELINE_LIMIT}`)).then(setActivity, () => setActivity(null));

  async function savePriority(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    const outcome = await sendJson(leadUrl(lead.id), "PATCH", { priority });
    setBusy(false);
    if (!outcome.ok || !isRequestBody(outcome.data)) return setPriorityNotice({ text: outcome.ok ? "Unable to save the priority." : outcome.message, failed: true });
    setLead(outcome.data as unknown as TelecallerLeadDetail);
    setPriorityNotice({ text: "Priority updated.", failed: false });
    void reloadActivity();
  }

  const fields: [string, React.ReactNode][] = [
    ["Lead ID", lead.lead_code], ["Mobile number", show(lead.phone)], ["WhatsApp number", show(lead.whatsapp_number)], ["Email", show(lead.email)],
    ["City", show(lead.city)], ["State", show(lead.state)], ["Qualification", show(lead.qualification)], ["Passing year", show(lead.passing_year)],
    ["College/University", show(lead.institution)], ["Lead source", SOURCE_LABEL[lead.source] ?? lead.source], ["Campaign", show(lead.campaign?.name)],
    ["Product interest", show(lead.product?.name)], ["Assigned telecaller", show(lead.telecaller?.full_name, "Unassigned")],
    ["Assigned counselor", show(lead.counselor?.full_name, "Not assigned")], ["Lead date", formatDate(lead.created_at)],
  ];

  return (
    <div className="action-card" style={{ display: "grid", gap: 16 }}>
      <div>
        <div className="eyebrow">{lead.lead_code}</div>
        <h2 style={{ margin: "4px 0" }}>{lead.name}</h2>
        <p className="muted" style={{ margin: 0 }}>Stage: <strong>{lead.status_label}</strong> · Priority: <strong>{PRIORITY_LABEL[lead.priority] ?? lead.priority}</strong></p>
        {/* D1 / QA-05: a manager still acts on a handed-over lead, but sees that the counselor has it */}
        {(lead.read_only || lead.counselor) && (
          <p className="form-message" role="note" style={{ marginTop: 8 }}>
            {`This lead is with the counselor${lead.counselor ? `, ${lead.counselor.full_name}` : ""}.`}
            {lead.read_only && " You can view it but not change it."}
          </p>
        )}
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-start" }}>
        {call && <a className="btn small" href={call} aria-label={`Call ${lead.name}`}>Call</a>}
        {!lead.read_only && (
          <div>
            <LeadStageControl lead={lead} canReopen={canReopen} move={moveStage} onMessage={(m) => setStageNotice({ text: m.text, failed: m.failed })}
              onChanged={(status) => { setLead((l) => ({ ...l, status, status_label: stageLabel(status) })); void reloadActivity(); }} />
            <NoticeLine notice={stageNotice} />
          </div>
        )}
      </div>

      {!lead.read_only && (
        <form onSubmit={savePriority}>
          <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
            <legend style={{ fontWeight: 600 }}>Priority</legend>
            <div style={{ display: "grid", gap: 6, marginTop: 6 }}>
              {PRIORITIES.map((p) => (
                <label key={p.key} style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                  <input type="radio" name="priority" value={p.key} checked={priority === p.key} disabled={busy}
                    onChange={() => { setPriority(p.key); setPriorityNotice(null); }} />
                  <span><strong>{p.label}</strong> <span className="muted">{p.help}</span></span>
                </label>
              ))}
            </div>
          </fieldset>
          <button type="submit" className="btn secondary small" style={{ marginTop: 8 }} disabled={busy || priority === lead.priority}>
            {busy ? "Saving…" : "Save priority"}
          </button>
          <NoticeLine notice={priorityNotice} />
        </form>
      )}

      {/* tel-011 (F2, F4): only the lead's telecaller adds follow-ups (a manager reads); never on a closed lead */}
      <LeadFollowUps leadId={lead.id} leadStage={lead.status} canWrite={!canReopen && !lead.read_only && !isClosed(lead.status)}
        onStageChanged={(status) => { setLead((l) => ({ ...l, status, status_label: stageLabel(status) })); void reloadActivity(); }} />

      <LeadScriptPanel product={lead.product} />

      <section aria-labelledby="lead-details-heading">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
          <h3 id="lead-details-heading" style={{ margin: 0 }}>Lead details</h3>
          {!lead.read_only && !editing && (
            <button type="button" className="btn secondary small" onClick={() => { setEditing(true); setDetailsNotice(null); }}>Edit details</button>
          )}
        </div>
        {editing ? (
          <DetailsForm lead={lead} onCancel={() => setEditing(false)}
            onSaved={(next) => { setLead(next); setEditing(false); setDetailsNotice({ text: "Details saved.", failed: false }); }} />
        ) : (
          <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(12rem, 1fr))", gap: "8px 16px", margin: "8px 0 0" }}>
            {fields.map(([term, value]) => (
              <div key={term}>
                <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
                <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>
              </div>
            ))}
          </dl>
        )}
        <NoticeLine notice={detailsNotice} />
      </section>

      {/* tel-009: QD1 -- a save writes the shared answers to the lead, so Lead details shows them at once */}
      <LeadQualificationForm leadId={lead.id} productId={lead.product?.id ?? null} readOnly={lead.read_only}
        onSaved={(q) => setLead((l) => ({ ...l, qualification: q.qualification, passing_year: q.passing_year, city: q.city, state: q.state }))} />

      {/* tel-016: only the lead's telecaller books (`canReopen` marks the manager's page); the API is the gate either way */}
      <LeadAppointmentsSection leadId={lead.id} stage={lead.status} canBook={!canReopen && !lead.read_only}
        onStage={(status, label) => {
          if (status === lead.status) return;
          setLead((l) => ({ ...l, status, status_label: label }));
          void reloadActivity();
        }} />

      <section aria-labelledby="lead-enquiry-heading">
        <h3 id="lead-enquiry-heading" style={{ margin: 0 }}>Enquiry</h3>
        <p style={{ margin: "6px 0 0" }}><strong>{lead.subject}</strong></p>
        <p style={{ margin: "4px 0 0", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{lead.message}</p>
      </section>

      <section aria-labelledby="lead-activity-heading">
        <h3 id="lead-activity-heading" style={{ margin: 0 }}>Activity</h3>
        {activity === null ? (
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the activity.</p>
        ) : activity.items.length === 0 ? (
          <p className="muted" style={{ fontSize: 13 }}>No activity yet.</p>
        ) : (
          <ol aria-label="Lead activity" style={{ margin: "6px 0 0", paddingLeft: 18, display: "grid", gap: 6 }}>
            {activity.items.map((row) => (
              <li key={`${row.kind}-${row.id}`}>
                {row.kind === "enquiry" ? (
                  <strong style={{ overflowWrap: "anywhere" }}>New enquiry: {row.to_label}</strong>
                ) : (
                  <strong>{row.kind === "priority" ? "Priority" : "Stage"}: {row.from_label} → {row.to_label}</strong>
                )}
                <div className="muted" style={{ fontSize: 13 }}>
                  {row.actor ? row.actor.full_name : row.kind === "enquiry" ? "Website form" : "System"}
                  {row.kind === "enquiry" && ` · ${SOURCE_LABEL[row.from_value] ?? row.from_value}`} · {formatDate(row.at, true)}
                </div>
                {row.reason && <div style={{ fontSize: 13, overflowWrap: "anywhere", whiteSpace: "pre-wrap" }}>{row.reason}</div>}
              </li>
            ))}
          </ol>
        )}
        {activity && activity.total > activity.items.length && (
          <p className="muted" style={{ fontSize: 13 }}>Showing the latest {activity.items.length} of {activity.total} entries.</p>
        )}
      </section>
    </div>
  );
}
