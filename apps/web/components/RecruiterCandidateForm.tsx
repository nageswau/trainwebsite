"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useRef, useState } from "react";

import CandidateRowsEditor from "@/components/CandidateRowsEditor";
import StaleRecordNotice from "@/components/StaleRecordNotice";
import { sendJson } from "@/lib/apiErrors";
import { activeValues, type CatalogueValue } from "@/lib/recruiterCatalogue";
import {
  AMOUNTS, CANDIDATES_PATH, CANDIDATES_URL, CHOICES, COMPENSATION_LABELS, COMPENSATION_VIEW, CONTACT_METHODS, DUPLICATE_CHECK_URL, EMPTY_FORM, FIELDS,
  NEGOTIABLE, PERIOD_LABEL, STATUSES, STATUS_LABEL, candidateBody, candidateUrl, displayValue, formFromDetail, missingRequired, shownFields,
  type CandidateDetail, type CandidateForm, type CandidateMatch,
} from "@/lib/recruiterCandidates";
import { EXCHANGE_RATES_URL, type ExchangeRate } from "@/lib/recruiterCatalogue";
import { useStaleGuard } from "@/lib/staleGuard";
import { usePermissions } from "@/lib/usePermissions";

// rec-009 (spec §6; AC1-AC3, Q-07): the candidate form -- create (then open the new candidate) or edit (in the detail page). Name, source
// and a mobile or an email are required; the API decides everything else. A known person is shown in the duplicate panel, above the
// form so it is seen next to the mobile and email even on a phone (the tel-005 QA-05 placement).
type Notice = { text: string; failed: boolean } | null;
const LABELS: Record<string, string> = {
  source_id: "Source", source_detail: "Source detail", status: "Status", archive: "Archived", restore: "Restored", resume_upload: "Resume", resume_extract: "Resume details",
  // hrc-010
  preferred_contact: "Preferred contact", willing_to_relocate: "Willing to relocate", work_modes: "Work modes", employment_types: "Employment types", shifts: "Shifts",
  education: "Education", employment: "Employment history", certifications: "Certifications",
};
const CHOICE_LABEL: Record<keyof typeof CHOICES, string> = { work_modes: "Work modes", employment_types: "Employment types", shifts: "Shifts" };
const GRID = { display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))", alignItems: "start" } as const;
const FIELDSET = { ...GRID, border: "1px solid var(--border, #e5e7eb)", borderRadius: 8, padding: 12, margin: 0 } as const;
const LEGEND = { fontWeight: 600, padding: "0 4px" } as const;
type Props = {
  initial?: CandidateDetail; onSaved?: (c: CandidateDetail) => void; onCancel?: () => void;
  /** hrc-003: the latest candidate after a stale save was reloaded or reviewed, for the page behind the form. */
  onLatest?: (c: CandidateDetail) => void;
};

function DuplicatePanel({ matches, focusRequest }: { matches: CandidateMatch[]; focusRequest: number }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (focusRequest > 0) heading.current?.focus(); // a refused save takes the user to the panel
  }, [focusRequest]);
  return (
    <section aria-labelledby="candidate-duplicate-heading" className="action-card" style={{ borderColor: "#d97706", display: "grid", gap: 8 }}>
      <div>
        <h3 id="candidate-duplicate-heading" ref={heading} tabIndex={-1} style={{ margin: 0 }}>⚠️ This person is already a candidate</h3>
        <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>A candidate with this mobile number or email exists. Open them instead of adding the person again.</p>
      </div>
      {matches.map((m) => (
        <div key={m.id} style={{ borderTop: "1px solid var(--border, #e5e7eb)", paddingTop: 8, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <p style={{ margin: 0, flex: "1 1 16rem", overflowWrap: "anywhere" }}>
            <strong>{m.candidate_code}</strong> · {m.name} <span className="muted" style={{ fontSize: 13 }}>(same {m.matched_on.join(" and ")})</span>
            <br />
            <span className="muted" style={{ fontSize: 13 }}>Source: {m.source_name} · {STATUS_LABEL[m.status] ?? m.status}{m.archived ? " · Archived" : ""}</span>
          </p>
          <Link className="btn secondary small" href={`${CANDIDATES_PATH}/${encodeURIComponent(m.id)}`} aria-label={`Open ${m.candidate_code}`}>Open candidate</Link>
        </div>
      ))}
    </section>
  );
}

export default function RecruiterCandidateForm({ initial, onSaved, onLatest, onCancel }: Props) {
  const router = useRouter();
  const editing = !!initial;
  // hrc-003: an edit keeps the values and `updated_at` it opened with; a save refused as stale re-bases them (Reload / Review).
  const guard = useStaleGuard<CandidateDetail, CandidateForm>(initial, (c) => (c ? formFromDetail(c) : EMPTY_FORM), (c) => c?.updated_at ?? null, onLatest);
  const { values, setValues } = guard;
  const [sources, setSources] = useState<CatalogueValue[]>([]);
  const [sourcesFailed, setSourcesFailed] = useState(false);
  const [matches, setMatches] = useState<CandidateMatch[]>([]);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);
  const [focusRequest, setFocusRequest] = useState(0);
  const sending = useRef(false); // a double click sends one request (state only updates after the handler)
  // hrc-001 H2: an edit follows what the API sent; a new candidate follows the grant (no salary inputs until it is known).
  const permissions = usePermissions(!editing);
  const compensation = initial ? "expected_salary" in initial : !!permissions?.includes(COMPENSATION_VIEW);

  useEffect(() => {
    const controller = new AbortController();
    activeValues("candidate-sources", controller.signal).then(setSources).catch(() => controller.signal.aborted || setSourcesFailed(true));
    return () => controller.abort();
  }, []);

  // hrc-011: INR plus every currency with a rate (and a stored one, so an edit never loses it). A failed read leaves INR only.
  const [currencies, setCurrencies] = useState<string[]>([]);
  useEffect(() => {
    if (!compensation) return;
    const controller = new AbortController();
    fetch(EXCHANGE_RATES_URL, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: { items?: ExchangeRate[] } | null) => setCurrencies((data?.items ?? []).map((r) => r.currency)))
      .catch(() => undefined);
    return () => controller.abort();
  }, [compensation]);
  const currencyOptions = (selected: string) => [...new Set(["INR", ...currencies, selected].filter(Boolean))];

  const set = (key: keyof CandidateForm, value: string) => setValues((v) => ({ ...v, [key]: value }));
  // An edit keeps a source deactivated since it was chosen (the API allows keeping it); it is offered alongside the active ones.
  const kept = initial && !sources.some((s) => s.id === initial.source.id) ? [{ ...initial.source, sort_order: -1 }] : [];

  /** Warn as soon as the mobile or email is entered; the save re-checks (409). A failed check just shows nothing. */
  async function checkDuplicates() {
    const query = new URLSearchParams(Object.entries({ mobile: values.mobile.trim(), email: values.email.trim(), exclude_id: initial?.id ?? "" }).filter(([, v]) => v));
    if (!values.mobile.trim() && !values.email.trim()) return setMatches([]);
    const response = await fetch(`${DUPLICATE_CHECK_URL}?${query}`).catch(() => null);
    const data = response?.ok ? await response.json().catch(() => null) : null;
    setMatches(Array.isArray(data?.matches) ? data.matches : []);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setNotice(null);
    const missing = missingRequired(values);
    if (missing) return setNotice({ text: missing, failed: true });
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    const body = initial ? { ...candidateBody(values, "edit", compensation), expected_updated_at: guard.token } : candidateBody(values, "create", compensation);
    const outcome = await sendJson(initial ? candidateUrl(initial.id) : CANDIDATES_URL, initial ? "PATCH" : "POST", body);
    sending.current = false;
    setBusy(false);
    if (guard.caught(outcome)) return;
    if (outcome.ok && typeof outcome.data.id === "string") {
      setMatches([]);
      if (onSaved) return onSaved(outcome.data as unknown as CandidateDetail);
      return router.replace(`${CANDIDATES_PATH}/${encodeURIComponent(outcome.data.id)}`); // QA-05: Back goes to the list, not a stale form
    }
    const detail = outcome.ok ? null : (outcome.detail as { code?: string; message?: string; matches?: CandidateMatch[] } | undefined);
    if (detail?.code === "duplicate_candidate" && Array.isArray(detail.matches)) {
      setMatches(detail.matches);
      setFocusRequest((n) => n + 1);
      return setNotice({ text: "This person is already a candidate. Open the existing candidate instead.", failed: true });
    }
    setNotice({ text: outcome.ok ? "Unable to save the candidate." : outcome.message, failed: true });
  }

  const input = ({ key, label, type, max, min, numMax, hint }: (typeof FIELDS)[number]) => (
    <div className="field" key={key}>
      <label htmlFor={`cand-${key}`}>{label}{key === "name" && " *"}</label>
      <input id={`cand-${key}`} type={type} value={values[key]} disabled={busy} maxLength={type === "number" ? undefined : max}
        min={min} max={numMax} step={type === "number" ? 1 : undefined} inputMode={type === "number" ? "numeric" : undefined}
        aria-required={key === "name" || undefined} aria-describedby={hint ? `cand-${key}-hint` : undefined}
        onChange={(e) => set(key, e.target.value)} onBlur={key === "mobile" || key === "email" ? () => void checkDuplicates() : undefined} />
      {/* QA-04: the hint sits under the input, so the inputs of one row line up */}
      {hint && <span id={`cand-${key}-hint`} className="muted" style={{ fontSize: 13 }}>{hint}</span>}
    </div>
  );

  return (
    <div style={{ display: "grid", gap: 16 }}>
      {matches.length > 0 && <DuplicatePanel matches={matches} focusRequest={focusRequest} />}
      <form onSubmit={submit} noValidate className="action-card" style={{ display: "grid", gap: 12 }}>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>* Required. Enter a mobile number or an email (or both).</p>
        <div className="form-grid" style={GRID}>
          {shownFields(values, "basic").map(input)}
          <div className="field">
            <label htmlFor="cand-source_id">Source *</label>
            <select id="cand-source_id" aria-required value={values.source_id} disabled={busy} onChange={(e) => set("source_id", e.target.value)}>
              <option value="">Choose a source</option>
              {[...kept, ...sources].map((s) => <option key={s.id} value={s.id}>{s.name}{s.active ? "" : " (inactive)"}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="cand-source_detail">Source detail</label>
            <input id="cand-source_detail" maxLength={200} aria-describedby="cand-source_detail-hint" value={values.source_detail} disabled={busy}
              onChange={(e) => set("source_detail", e.target.value)} />
            <span id="cand-source_detail-hint" className="muted" style={{ fontSize: 13 }}>e.g. the course, college or referrer</span>
          </div>
          <div className="field">
            <label htmlFor="cand-status">Status</label>
            <select id="cand-status" value={values.status} disabled={busy} onChange={(e) => set("status", e.target.value)}>
              {STATUSES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </div>
        </div>
        {/* hrc-010 (DEC-SCOPE-382): the §5 sections */}
        <fieldset className="form-grid" style={FIELDSET}>
          <legend style={LEGEND}>Location and contact</legend>
          {shownFields(values, "location").map(input)}
          <div className="field">
            <label htmlFor="cand-preferred_contact">Preferred contact</label>
            <select id="cand-preferred_contact" value={values.preferred_contact} disabled={busy} aria-describedby="cand-preferred_contact-hint" onChange={(e) => set("preferred_contact", e.target.value)}>
              <option value="">Not stated</option>
              {CONTACT_METHODS.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
            <span id="cand-preferred_contact-hint" className="muted" style={{ fontSize: 13 }}>
              {initial?.email_verified_at ? "Email verified" : "Email not verified yet"}
            </span>
          </div>
        </fieldset>
        <CandidateRowsEditor kind="education" value={values.education} disabled={busy} onChange={(v) => set("education", v)} />
        <CandidateRowsEditor kind="employment" value={values.employment} disabled={busy} onChange={(v) => set("employment", v)}>
          <div className="form-grid" style={GRID}>{shownFields(values, "experience").map(input)}</div>
          {!shownFields(values, "experience").some((f) => f.key === "experience_months") && (
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>Total experience and the current company are worked out from the jobs below (an overlap counts once).</p>
          )}
        </CandidateRowsEditor>
        <CandidateRowsEditor kind="certifications" value={values.certifications} disabled={busy} onChange={(v) => set("certifications", v)}>
          <div className="form-grid" style={GRID}>{shownFields(values, "skills").map(input)}</div>
        </CandidateRowsEditor>
        <fieldset className="form-grid" style={FIELDSET}>
          <legend style={LEGEND}>Preferences</legend>
          {shownFields(values, "preferences").map(input)}
          <div className="field">
            <label htmlFor="cand-willing_to_relocate">Willing to relocate</label>
            <select id="cand-willing_to_relocate" value={values.willing_to_relocate} disabled={busy} onChange={(e) => set("willing_to_relocate", e.target.value)}>
              {NEGOTIABLE.map((n) => <option key={n.key} value={n.key}>{n.label}</option>)}
            </select>
          </div>
          {(Object.entries(CHOICES) as [keyof typeof CHOICES, readonly { key: string; label: string }[]][]).map(([key, options]) => (
            <fieldset key={key} style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 4 }}>
              <legend style={{ padding: 0, marginBottom: 4 }}>{CHOICE_LABEL[key]}</legend>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px" }}>
                {options.map((o) => {
                  const chosen = values[key].split(",").filter(Boolean);
                  return (
                    <label key={o.key} style={{ display: "inline-flex", gap: 4, alignItems: "center", fontWeight: 400 }}>
                      <input type="checkbox" checked={chosen.includes(o.key)} disabled={busy}
                        onChange={(e) => set(key, options.map((x) => x.key).filter((k) => (k === o.key ? e.target.checked : chosen.includes(k))).join(","))} />
                      {o.label}
                    </label>
                  );
                })}
              </div>
            </fieldset>
          ))}
        </fieldset>
        {compensation && (
          <fieldset className="form-grid" style={FIELDSET}>
            <legend style={LEGEND}>Compensation</legend>
            <p className="muted" style={{ margin: 0, fontSize: 13, gridColumn: "1 / -1" }}>Enter each amount as the candidate states it. Leave it blank if not provided. Search compares the yearly rupee figure.</p>
            {AMOUNTS.map(({ key, label }) => (
              <div className="field" key={key}>
                <label htmlFor={`cand-${key}_salary`}>{label}</label>
                <input id={`cand-${key}_salary`} type="number" min={0} step="0.01" inputMode="decimal" value={values[`${key}_salary`]} disabled={busy}
                  onChange={(e) => set(`${key}_salary`, e.target.value)} />
                <div style={{ display: "flex", gap: 8 }}>
                  <select aria-label={`${label} currency`} value={values[`${key}_salary_currency`]} disabled={busy} onChange={(e) => set(`${key}_salary_currency`, e.target.value)} style={{ flex: "0 0 6rem" }}>
                    {currencyOptions(values[`${key}_salary_currency`]).map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                  <select aria-label={`${label} pay period`} value={values[`${key}_salary_period`]} disabled={busy} onChange={(e) => set(`${key}_salary_period`, e.target.value)} style={{ flex: 1 }}>
                    {Object.entries(PERIOD_LABEL).map(([k, text]) => <option key={k} value={k}>{text}</option>)}
                  </select>
                </div>
              </div>
            ))}
            <div className="field">
              <label htmlFor="cand-salary_negotiable">Negotiable</label>
              <select id="cand-salary_negotiable" value={values.salary_negotiable} disabled={busy} onChange={(e) => set("salary_negotiable", e.target.value)}>
                {NEGOTIABLE.map((n) => <option key={n.key} value={n.key}>{n.label}</option>)}
              </select>
            </div>
          </fieldset>
        )}
        {sourcesFailed && <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>Unable to load the candidate sources. Reload the page to try again.</p>}
        <StaleRecordNotice
          guard={guard}
          labelOf={(key) => FIELDS.find((f) => f.key === key)?.label ?? COMPENSATION_LABELS[key] ?? LABELS[key] ?? key.replace(/_/g, " ")}
          display={(key, value) => (key === "source_id" ? ([...kept, ...sources].find((s) => s.id === value)?.name ?? value) : key === "status" ? (STATUS_LABEL[value] ?? value) : displayValue(key, value))}
          onReload={guard.reload}
          onReview={guard.reviewMine}
        />
        {notice && <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: 0, fontSize: 13 }}>{notice.text}</p>}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : editing ? "Save changes" : "Add candidate"}</button>
          {onCancel ? <button type="button" className="btn secondary" onClick={onCancel} disabled={busy}>Cancel</button> : <Link className="btn secondary" href={CANDIDATES_PATH}>Cancel</Link>}
        </div>
      </form>
    </div>
  );
}
