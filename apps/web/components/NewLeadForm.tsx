"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import ProductOptions from "@/components/TelecallerProductOptions";
import { isRequestBody, sendJson } from "@/lib/apiErrors";
import { formatDate } from "@/lib/formatDate";
import { SOURCES, SOURCE_LABEL, activeCampaigns, activeProducts, type Campaign, type Product } from "@/lib/telecallerCatalogue";
import { DUPLICATE_CHECK_URL, LEADS_URL, PRIORITIES, leadUrl, type DuplicateMatch } from "@/lib/telecallerLeads";

// tel-005 (spec §4; I1, I2, I5, R2, R5, R6): a telecaller or manager enters a lead. The mobile is required, email optional; the API
// decides the owner, the stage and every rule. A known person (same mobile or email, any lead) is shown in the §18 duplicate panel,
// where the new enquiry can be added to that lead instead.
type Notice = { text: string; failed: boolean } | null;
const TEXT_FIELDS = [
  { key: "name", label: "Student name", type: "text", max: 160, required: true },
  { key: "phone", label: "Mobile number", type: "tel", max: 40, required: true },
  { key: "email", label: "Email", type: "email", max: 255, required: false },
  { key: "whatsapp_number", label: "WhatsApp number", type: "tel", max: 40, required: false },
  { key: "city", label: "City", type: "text", max: 120, required: false },
  { key: "state", label: "State", type: "text", max: 120, required: false },
  { key: "qualification", label: "Qualification", type: "text", max: 120, required: false },
  { key: "passing_year", label: "Passing year", type: "number", max: 4, required: false },
  { key: "institution", label: "College/University", type: "text", max: 200, required: false },
] as const;
const EMPTY: Record<string, string> = {
  ...Object.fromEntries(TEXT_FIELDS.map(({ key }) => [key, ""])),
  product_id: "", campaign_id: "", source: "", priority: "warm", division: "", subject: "", message: "",
};

function NoticeLine({ notice }: { notice: Notice }) {
  if (!notice) return null;
  return <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: "6px 0 0", fontSize: 13 }}>{notice.text}</p>;
}

/** EVID-019 §18: who has the existing lead and where it stands, with "Add enquiry to this lead" (I5) and, when the caller may open it,
 *  a link to it. */
function DuplicatePanel({ matches, basePath, enquiry }: { matches: DuplicateMatch[]; basePath: string; enquiry: () => Record<string, string> | string }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [notices, setNotices] = useState<Record<string, Notice>>({});

  async function addEnquiry(match: DuplicateMatch) {
    const payload = enquiry();
    if (typeof payload === "string") return setNotices((n) => ({ ...n, [match.id]: { text: payload, failed: true } }));
    setBusy(match.id);
    const outcome = await sendJson(leadUrl(match.id, "/enquiries"), "POST", payload);
    setBusy(null);
    const notice = outcome.ok && isRequestBody(outcome.data)
      ? { text: `Enquiry added to ${match.lead_code}.`, failed: false }
      : { text: outcome.ok ? "Unable to add the enquiry." : outcome.message, failed: true };
    setNotices((n) => ({ ...n, [match.id]: notice }));
  }

  return (
    <section aria-labelledby="duplicate-heading" className="action-card" style={{ borderColor: "#d97706", display: "grid", gap: 12 }}>
      <div>
        <h3 id="duplicate-heading" style={{ margin: 0 }}>⚠️ Lead already exists.</h3>
        <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
          A lead with this mobile number or email is already in the CRM. Add this enquiry to it instead of creating another lead.
        </p>
      </div>
      {matches.map((m) => (
        <div key={m.id} style={{ borderTop: "1px solid var(--border, #e5e7eb)", paddingTop: 8 }}>
          <p style={{ margin: 0 }}><strong>{m.lead_code}</strong> · {m.name} <span className="muted" style={{ fontSize: 13 }}>(same {m.matched_on.join(" and ")})</span></p>
          <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(10rem, 1fr))", gap: "4px 16px", margin: "6px 0 0" }}>
            {([
              ["Existing telecaller", m.telecaller?.full_name ?? "Unassigned"], ["Counselor", m.counselor?.full_name ?? "Not assigned"],
              ["Last contact", m.last_contact_at ? formatDate(m.last_contact_at, true) : "No contact logged yet"], ["Current status", m.status_label],
            ] as const).map(([term, value]) => (
              <div key={term}>
                <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
                <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>
              </div>
            ))}
          </dl>
          <p className="muted" style={{ margin: "6px 0 0", fontSize: 13 }}>Previous enquiries</p>
          <ul style={{ margin: "2px 0 0", paddingLeft: 18, fontSize: 13 }}>
            {m.enquiries.map((e, i) => (
              <li key={i} style={{ overflowWrap: "anywhere" }}>{e.subject} · {SOURCE_LABEL[e.source] ?? e.source} · {formatDate(e.at)}</li>
            ))}
          </ul>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
            <button type="button" className="btn small" disabled={busy !== null} aria-label={`Add enquiry to ${m.lead_code}`} onClick={() => void addEnquiry(m)}>
              {busy === m.id ? "Adding…" : "Add enquiry to this lead"}
            </button>
            {m.in_scope && <Link className="btn secondary small" href={`${basePath}/${encodeURIComponent(m.id)}`} aria-label={`Open ${m.lead_code}`}>Open lead</Link>}
          </div>
          <NoticeLine notice={notices[m.id] ?? null} />
        </div>
      ))}
    </section>
  );
}

export default function NewLeadForm({ basePath }: { basePath: string }) {
  const router = useRouter();
  const [values, setValues] = useState(EMPTY);
  const [products, setProducts] = useState<Product[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [pickersFailed, setPickersFailed] = useState(false);
  const [matches, setMatches] = useState<DuplicateMatch[]>([]);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([activeProducts(controller.signal), activeCampaigns(controller.signal)])
      .then(([p, c]) => { setProducts(p); setCampaigns(c); })
      .catch(() => controller.signal.aborted || setPickersFailed(true));
    return () => controller.abort();
  }, []);

  const product = products.find((p) => p.id === values.product_id) ?? null;
  const productCampaigns = campaigns.filter((c) => c.product.id === values.product_id);
  const set = (key: string, value: string) => setValues((v) => ({ ...v, [key]: value }));

  function chooseProduct(id: string) {
    setValues((v) => ({ ...v, product_id: id, campaign_id: "", division: "" }));
  }

  function chooseCampaign(id: string) {
    const campaign = campaigns.find((c) => c.id === id);
    setValues((v) => ({ ...v, campaign_id: id, source: campaign ? campaign.source : v.source }));
  }

  /** R2: warn as soon as the mobile or email is entered; the create still re-checks (409). A failed check just shows nothing. */
  async function checkDuplicates() {
    const query = new URLSearchParams(Object.entries({ phone: values.phone.trim(), email: values.email.trim() }).filter(([, v]) => v));
    if (!query.size) return setMatches([]);
    const response = await fetch(`${DUPLICATE_CHECK_URL}?${query}`).catch(() => null);
    const data = response?.ok ? await response.json().catch(() => null) : null;
    if (Array.isArray(data?.matches)) setMatches(data.matches);
  }

  /** The new enquiry, for "Add enquiry to this lead": the form's subject (else the product), notes, source and campaign. */
  function enquiryPayload(): Record<string, string> | string {
    if (!values.source) return "Choose the lead source first.";
    const subject = values.subject.trim() || product?.name || "";
    if (!subject) return "Enter the enquiry subject or choose a product first.";
    const payload: Record<string, string> = { subject, source: values.source };
    if (values.message.trim()) payload.message = values.message.trim();
    if (values.campaign_id) payload.campaign_id = values.campaign_id;
    return payload;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setNotice(null);
    const payload: Record<string, string | number> = { priority: values.priority };
    for (const [key, value] of Object.entries(values)) {
      const text = value.trim();
      if (text && key !== "priority") payload[key] = key === "passing_year" ? Number(text) : text;
    }
    setBusy(true);
    const outcome = await sendJson(LEADS_URL, "POST", payload);
    setBusy(false);
    if (outcome.ok && isRequestBody(outcome.data)) return router.push(`${basePath}/${encodeURIComponent(outcome.data.id)}`);
    const detail = outcome.ok ? null : (outcome.detail as { code?: string; matches?: DuplicateMatch[] } | undefined);
    if (detail?.code === "duplicate_lead" && Array.isArray(detail.matches)) {
      setMatches(detail.matches);
      return setNotice({ text: "This person is already a lead -- see below.", failed: true });
    }
    setNotice({ text: outcome.ok ? "Unable to create the lead." : outcome.message, failed: true });
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <form onSubmit={submit} noValidate className="action-card" style={{ display: "grid", gap: 12 }}>
        <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))" }}>
          {TEXT_FIELDS.map(({ key, label, type, max, required }) => (
            <div className="field" key={key}>
              <label htmlFor={`new-${key}`}>{label}{required && " *"}</label>
              <input id={`new-${key}`} type={type} maxLength={type === "number" ? undefined : max} min={type === "number" ? 1950 : undefined}
                max={type === "number" ? 2100 : undefined} aria-required={required || undefined} value={values[key]} disabled={busy}
                onChange={(e) => set(key, e.target.value)} onBlur={key === "phone" || key === "email" ? () => void checkDuplicates() : undefined} />
            </div>
          ))}
          <div className="field">
            <label htmlFor="new-product_id">Product interest *</label>
            <select id="new-product_id" aria-required value={values.product_id} disabled={busy} onChange={(e) => chooseProduct(e.target.value)}>
              <option value="">Choose a product</option>
              <ProductOptions products={products} />
            </select>
          </div>
          {product && !product.team && (
            <div className="field">
              <label htmlFor="new-division">Division *</label>
              <select id="new-division" aria-required value={values.division} disabled={busy} onChange={(e) => set("division", e.target.value)}>
                <option value="">Choose the team</option>
                <option value="it">IT</option>
                <option value="overseas">Overseas</option>
              </select>
            </div>
          )}
          <div className="field">
            <label htmlFor="new-campaign_id">Campaign</label>
            <select id="new-campaign_id" value={values.campaign_id} disabled={busy || !values.product_id} onChange={(e) => chooseCampaign(e.target.value)}>
              <option value="">{values.product_id ? "No campaign" : "Choose a product first"}</option>
              {productCampaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="new-source">Lead source *</label>
            <select id="new-source" aria-required value={values.source} disabled={busy} onChange={(e) => set("source", e.target.value)}>
              <option value="">Choose a source</option>
              {SOURCES.map((s) => <option key={s} value={s}>{SOURCE_LABEL[s]}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="new-priority">Priority</label>
            <select id="new-priority" value={values.priority} disabled={busy} onChange={(e) => set("priority", e.target.value)}>
              {PRIORITIES.map((p) => <option key={p.key} value={p.key}>{p.label} – {p.help}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="new-subject">Enquiry subject</label>
            <input id="new-subject" maxLength={180} placeholder={product?.name ?? "Defaults to the product"} value={values.subject} disabled={busy}
              onChange={(e) => set("subject", e.target.value)} />
          </div>
        </div>
        <div className="field">
          <label htmlFor="new-message">Notes</label>
          <textarea id="new-message" maxLength={5000} rows={3} value={values.message} disabled={busy} onChange={(e) => set("message", e.target.value)} />
        </div>
        {pickersFailed && <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>Unable to load the products and campaigns. Reload the page to try again.</p>}
        <NoticeLine notice={notice} />
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          <button type="submit" className="btn" disabled={busy}>{busy ? "Creating…" : "Create lead"}</button>
          <Link className="btn secondary" href={basePath}>Cancel</Link>
        </div>
      </form>
      {matches.length > 0 && <DuplicatePanel matches={matches} basePath={basePath} enquiry={enquiryPayload} />}
    </div>
  );
}
