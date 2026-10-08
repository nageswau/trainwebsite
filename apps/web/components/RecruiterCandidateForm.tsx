"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { activeValues, type CatalogueValue } from "@/lib/recruiterCatalogue";
import {
  CANDIDATES_PATH, CANDIDATES_URL, DUPLICATE_CHECK_URL, EMPTY_FORM, FIELDS, STATUSES, STATUS_LABEL, candidateBody, candidateUrl, formFromDetail,
  missingRequired, type CandidateDetail, type CandidateForm, type CandidateMatch,
} from "@/lib/recruiterCandidates";

// rec-009 (spec §6; AC1-AC3, Q-07): the candidate form -- create (then open the new candidate) or edit (in the detail page). Name, source
// and a mobile or an email are required; the API decides everything else. A known person is shown in the duplicate panel, above the
// form so it is seen next to the mobile and email even on a phone (the tel-005 QA-05 placement).
type Notice = { text: string; failed: boolean } | null;
type Props = { initial?: CandidateDetail; onSaved?: (c: CandidateDetail) => void; onCancel?: () => void };

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

export default function RecruiterCandidateForm({ initial, onSaved, onCancel }: Props) {
  const router = useRouter();
  const editing = !!initial;
  const [values, setValues] = useState<CandidateForm>(initial ? formFromDetail(initial) : EMPTY_FORM);
  const [sources, setSources] = useState<CatalogueValue[]>([]);
  const [sourcesFailed, setSourcesFailed] = useState(false);
  const [matches, setMatches] = useState<CandidateMatch[]>([]);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);
  const [focusRequest, setFocusRequest] = useState(0);
  const sending = useRef(false); // a double click sends one request (state only updates after the handler)

  useEffect(() => {
    const controller = new AbortController();
    activeValues("candidate-sources", controller.signal).then(setSources).catch(() => controller.signal.aborted || setSourcesFailed(true));
    return () => controller.abort();
  }, []);

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
    const outcome = await sendJson(initial ? candidateUrl(initial.id) : CANDIDATES_URL, initial ? "PATCH" : "POST", candidateBody(values, initial ? "edit" : "create"));
    sending.current = false;
    setBusy(false);
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
        min={min} max={numMax} step={key.endsWith("salary") ? "0.01" : type === "number" ? 1 : undefined} inputMode={type === "number" ? "numeric" : undefined}
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
        <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))", alignItems: "start" }}>
          {FIELDS.map(input)}
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
        {sourcesFailed && <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>Unable to load the candidate sources. Reload the page to try again.</p>}
        {notice && <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: 0, fontSize: 13 }}>{notice.text}</p>}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : editing ? "Save changes" : "Add candidate"}</button>
          {onCancel ? <button type="button" className="btn secondary" onClick={onCancel} disabled={busy}>Cancel</button> : <Link className="btn secondary" href={CANDIDATES_PATH}>Cancel</Link>}
        </div>
      </form>
    </div>
  );
}
