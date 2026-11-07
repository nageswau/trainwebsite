"use client";
import { type FormEvent, useState } from "react";

import { DetailList } from "@/components/BdmOrganizationProfileDetails";
import LocalTime from "@/components/LocalTime";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import { type Company, COMPANIES_URL, isCompanyBody, splitList, type VendorNext, VENDOR_STATUSES } from "@/lib/recruiterCompanies";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Draft = { specialisations: string; categories: string; locations: string };
const NONE = "None recorded";
const onFile = (yes: boolean) => (yes ? "On file" : "Not on file");

// pob-010 (DEC-SCOPE-420 V3/V5/V6): a vendor's onboarding -- status as text on a step list (never colour alone), what is on file, the moves
// this caller may try (`next_statuses`; the server re-checks each step's needs and its refusal shows here), its details and history.
export default function RecruiterCompanyVendor({ company, onChanged }: { company: Company; onChanged: (c: Company, text: string) => void }) {
  const vendor = company.vendor;
  const [picked, setPicked] = useState<VendorNext | null>(null);
  const [reason, setReason] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const focus = useFocusAfterRender();
  const prefix = `vendor-${company.id}`;
  if (!vendor) return null;
  const at = VENDOR_STATUSES.findIndex((s) => s.key === company.vendor_status);

  async function send(url: string, body: Record<string, unknown>, text: string, after: () => void) {
    if (busy) return;
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(url, url.endsWith("vendor-status") ? "POST" : "PATCH", body);
    setBusy(false);
    if (outcome.ok && isCompanyBody(outcome.data)) {
      after();
      onChanged(outcome.data.company, text);
      focus(`${prefix}-title`);
      return;
    }
    // QA-01: someone else moved this vendor -- say so and show where it is now, instead of offering steps that no longer apply.
    const stale = !outcome.ok && (outcome.detail as { code?: string; message?: string } | null)?.code === "vendor_status_changed" ? (outcome.detail as { message: string }).message : null;
    if (stale) {
      setPicked(null);
      const latest = await sendRequest(`${COMPANIES_URL}/${company.id}`, { method: "GET" });
      if (latest.ok && isCompanyBody(latest.data)) return onChanged(latest.data.company, `${stale}.`);
    }
    setFailure(stale ? `${stale}. Reload the page.` : outcome.ok ? "Unable to update this vendor." : outcome.message);
  }

  function move(next: VendorNext, why: string | null) {
    const body = { status: next.status, from_status: company.vendor_status, ...(why ? { reason: why } : {}) };
    void send(`${COMPANIES_URL}/${company.id}/vendor-status`, body, `Vendor moved to ${next.label}.`, () => {
      setPicked(null);
      setReason("");
    });
  }

  function save(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    const body = { vendor_specialisations: splitList(draft.specialisations), vendor_service_categories: splitList(draft.categories), vendor_locations: splitList(draft.locations) };
    void send(`${COMPANIES_URL}/${company.id}`, body, "Vendor details saved.", () => setDraft(null));
  }

  const field = (key: keyof Draft, label: string) => (
    <div className="field">
      <label htmlFor={`${prefix}-${key}`}>{label}</label>
      <input id={`${prefix}-${key}`} value={draft?.[key] ?? ""} onChange={(e) => setDraft((d) => (d ? { ...d, [key]: e.target.value } : d))} aria-describedby={`${prefix}-list-hint`} />
    </div>
  );

  return (
    <section className="action-card wide" aria-labelledby={`${prefix}-title`}>
      <h3 id={`${prefix}-title`} tabIndex={-1}>Vendor onboarding</h3>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      <p>Status: <span className="badge">{company.vendor_status_label}</span></p>
      <ol className="jny-steps" aria-label="Vendor onboarding statuses">
        {VENDOR_STATUSES.map((s, i) => {
          const state = i < at ? "done" : i === at ? "current" : "upcoming";
          return (
            <li key={s.key} className={`jny-step jny-${state}`} aria-current={i === at ? "step" : undefined}>
              <span className="jny-glyph" aria-hidden="true">{state === "done" ? "✓" : state === "current" ? "•" : "–"}</span>
              <span className="jny-name">{s.label}</span>
              <span className="jny-state">{state === "done" ? "Done" : state === "current" ? "Current" : "Upcoming"}</span>
            </li>
          );
        })}
      </ol>
      {!company.archived && vendor.next_statuses.length > 0 && !picked && (
        <div className="actions">
          {vendor.next_statuses.map((next) => (
            <button key={next.status} type="button" className="btn secondary small" disabled={busy} onClick={() => (next.needs_reason ? setPicked(next) : move(next, null))}>
              Move to {next.label}
            </button>
          ))}
        </div>
      )}
      {picked && (
        <form onSubmit={(e) => { e.preventDefault(); move(picked, reason.trim()); }}>
          <div className="field">
            <label htmlFor={`${prefix}-reason`}>Reason for moving to {picked.label} (required)</label>
            <textarea id={`${prefix}-reason`} rows={2} maxLength={500} required value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
          <div className="actions">
            <button type="submit" className="btn small" disabled={busy || !reason.trim()}>{busy ? "Saving…" : `Move to ${picked.label}`}</button>
            <button type="button" className="btn secondary small" disabled={busy} onClick={() => { setPicked(null); setReason(""); }}>Cancel</button>
          </div>
        </form>
      )}
      {draft ? (
        <form className="form-grid" onSubmit={save} aria-label="Edit vendor details">
          {field("specialisations", "Specialisations")}
          {field("categories", "Service categories")}
          {field("locations", "Locations")}
          <p id={`${prefix}-list-hint`} className="muted">Separate entries with commas.</p>
          <div className="actions">
            <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save vendor details"}</button>
            <button type="button" className="btn secondary small" disabled={busy} onClick={() => setDraft(null)}>Cancel</button>
          </div>
        </form>
      ) : (
        <>
          <DetailList
            rows={[
              ["Specialisations", vendor.specialisations.join(", ") || NONE],
              ["Service categories", vendor.service_categories.join(", ") || NONE],
              ["Locations", vendor.locations.join(", ") || NONE],
              ["Onboarding form", onFile(vendor.onboarding_form_on_file)],
              ["NDA", onFile(vendor.nda_on_file)],
              ["Vendor agreement", vendor.agreement ? vendor.agreement.status_label : "No agreement yet"],
            ]}
          />
          {company.permissions.can_edit && (
            <div className="actions">
              <button type="button" className="btn secondary small"
                onClick={() => setDraft({ specialisations: vendor.specialisations.join(", "), categories: vendor.service_categories.join(", "), locations: vendor.locations.join(", ") })}>
                Edit vendor details
              </button>
            </div>
          )}
        </>
      )}
      {vendor.history.length > 0 && (
        <details>
          <summary>Onboarding history ({vendor.history.length})</summary>
          <ul style={{ margin: 0, paddingLeft: 18 }} aria-label="Onboarding history">
            {vendor.history.map((h) => (
              <li key={`${h.created_at}-${h.to_status}`}>
                {h.to_label} · {h.actor.full_name} · <LocalTime value={h.created_at} />
                {h.reason && <> · {h.reason}</>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
