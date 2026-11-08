"use client";

import { type KeyboardEvent, useState } from "react";

import LocalTime from "@/components/LocalTime";
import SearchableSelect from "@/components/SearchableSelect";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import {
  OUTREACH_STATUSES, PERMISSION_METHODS, istToday, labelFor, referrerSearch, vendorSearch, type CandidateSourcing, type OutreachStatus,
} from "@/lib/candidateSourcing";
import type { PickOption } from "@/lib/lookups";
import { candidateUrl, type CandidateDetail, type SourceRef } from "@/lib/recruiterCandidates";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Props = {
  candidate: { id: string; source: SourceRef; source_detail: string | null; sourcing?: CandidateSourcing };
  canEdit: boolean;
  onSaved: (detail: CandidateDetail) => void;
};
type Mode = "outreach" | "source" | null;
const GRID = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))", gap: "8px 16px" } as const;

// pob-018 (DEC-SCOPE-428 A12): where the candidate came from and when, who referred or supplied them, when the details were last checked,
// how far outreach has got and how they agreed to be represented -- a profile is shared only with that permission (AC3). The Ownership
// card's conventions: one open editor at a time, the group takes focus, Escape cancels, an error takes focus. The API re-checks every rule.
export default function RecruiterCandidateSourcing({ candidate, canEdit, onSaved }: Props) {
  const s = candidate.sourcing;
  const [mode, setMode] = useState<Mode>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // outreach editor
  const [status, setStatus] = useState<OutreachStatus>("not_contacted");
  const [method, setMethod] = useState("");
  const [givenOn, setGivenOn] = useState("");
  const [note, setNote] = useState("");
  // source editor
  const [sourceDate, setSourceDate] = useState("");
  const [referrerName, setReferrerName] = useState("");
  const [portalRef, setPortalRef] = useState("");
  const [referrer, setReferrer] = useState<PickOption | null>(null);
  const [vendor, setVendor] = useState<PickOption | null>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `cand-src-${name}`;
  if (!s) return null;

  function open(next: Mode) {
    if (!s) return;
    setNotice(null);
    setError(null);
    if (next === "outreach") {
      setStatus(s.outreach_status);
      setMethod(s.permission?.method ?? "");
      setGivenOn(s.permission?.given_on ?? istToday());
      setNote(s.permission?.note ?? "");
    } else {
      setSourceDate(s.source_date);
      setReferrerName(s.referrer_name ?? "");
      setPortalRef(s.portal_import_reference ?? "");
      setReferrer(s.referrer?.id ? { id: s.referrer.id, label: s.referrer.name, detail: s.referrer.candidate_code } : null);
      setVendor(s.vendor ? { id: s.vendor.id, label: s.vendor.name } : null);
    }
    setMode(next);
    focus(id("group"));
  }

  function close() {
    const was = mode;
    setMode(null);
    setError(null);
    focus(id(was === "outreach" ? "outreach" : "edit"));
  }

  function fail(message: string) {
    setError(message);
    focus(id("error"));
  }

  async function send(request: Promise<Awaited<ReturnType<typeof sendJson>>>, done: string) {
    setBusy(true);
    setError(null);
    const outcome = await request;
    setBusy(false);
    if (!outcome.ok) return fail((outcome.status ?? 0) >= 500 ? "We couldn't save this. Please try again." : outcome.message);
    onSaved(outcome.data as unknown as CandidateDetail);
    setNotice(done);
    if (mode) close();
  }

  function verify() {
    if (busy) return;
    void send(sendRequest(candidateUrl(candidate.id, "/verify"), { method: "POST" }), "Details verified.");
  }

  function saveOutreach() {
    if (busy) return;
    const consented = status === "consented";
    if (consented && !method) return fail("Choose how the candidate agreed to be represented.");
    if (consented && !givenOn) return fail("Enter the date the candidate agreed.");
    const body = consented ? { status, method, given_on: givenOn, ...(note.trim() ? { note: note.trim() } : {}) } : { status };
    void send(sendJson(candidateUrl(candidate.id, "/outreach"), "PUT", body), "Outreach updated.");
  }

  function saveSource() {
    if (busy || !s) return;
    const text = (value: string) => value.trim() || null;
    const changes: Record<string, unknown> = {};
    if (sourceDate !== s.source_date) changes.source_date = sourceDate || null;
    if (text(referrerName) !== s.referrer_name) changes.referrer_name = text(referrerName);
    if (text(portalRef) !== s.portal_import_reference) changes.portal_import_reference = text(portalRef);
    if ((referrer?.id ?? null) !== (s.referrer?.id ?? null)) changes.referrer_candidate_id = referrer?.id ?? null; // a restricted referrer (id null) stays as it is
    if ((vendor?.id ?? null) !== (s.vendor?.id ?? null)) changes.vendor_id = vendor?.id ?? null;
    if (Object.keys(changes).length === 0) return close();
    void send(sendJson(candidateUrl(candidate.id), "PATCH", changes), "Source details saved.");
  }

  const permission = s.permission;
  const rows: [string, React.ReactNode][] = [
    ["Source", `${candidate.source.name}${candidate.source.active ? "" : " (inactive)"}`],
    ["Source detail", candidate.source_detail],
    ["Source date", <LocalTime key="d" value={s.source_date} />],
    ["Referred by", [s.referrer_name, s.referrer && `${s.referrer.name}${s.referrer.candidate_code ? ` (${s.referrer.candidate_code})` : ""}`].filter(Boolean).join(" · ") || null],
    ["Vendor", s.vendor?.name ?? null],
    ["Institution", s.institution?.name ?? null],
    ["Portal import reference", s.portal_import_reference],
    ["Last verified", s.last_verified_on
      ? <><LocalTime value={s.last_verified_on} />{s.last_verified_by ? ` by ${s.last_verified_by.full_name}` : ""}</>
      : <span className="muted">Not verified yet</span>],
    ["Outreach status", labelFor(OUTREACH_STATUSES, s.outreach_status)],
    ["Permission to represent", permission
      ? <>{labelFor(PERMISSION_METHODS, permission.method)} on <LocalTime value={permission.given_on} />
        {permission.note ? ` — ${permission.note}` : ""}{permission.recorded_by ? ` (recorded by ${permission.recorded_by.full_name})` : ""}</>
      : s.permitted ? "Given by the candidate (opt-in or institution agreement)" : <span className="muted">No permission recorded — cannot be shared with a client yet</span>],
  ];

  return (
    <section aria-labelledby="cand-src-heading" className="action-card">
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <h3 id="cand-src-heading" style={{ margin: 0 }}>Source and outreach</h3>
        {canEdit && !mode && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <button type="button" className="btn secondary small" disabled={busy} onClick={verify}>{busy ? "Saving…" : "Verify details"}</button>
            <button id={id("outreach")} type="button" className="btn secondary small" onClick={() => open("outreach")}>Update outreach</button>
            <button id={id("edit")} type="button" className="btn secondary small" onClick={() => open("source")}>Edit source details</button>
          </div>
        )}
      </div>
      <dl style={{ ...GRID, margin: "12px 0 0" }}>
        {rows.map(([term, value]) => (
          <div key={term}>
            <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
            <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value === null || value === "" ? <span className="muted">—</span> : value}</dd>
          </div>
        ))}
      </dl>
      {notice && <p role="status" className="form-message" style={{ margin: "8px 0 0" }}>{notice}</p>}
      {mode && (
        <div id={id("group")} tabIndex={-1} role="group" aria-label={mode === "outreach" ? "Update outreach" : "Edit source details"} className="form"
          style={{ marginTop: 12 }} onKeyDown={(e: KeyboardEvent) => { if (e.key === "Escape") close(); }}>
          {mode === "outreach" ? (
            <div style={GRID}>
              <div className="field">
                <label htmlFor={id("status")}>Outreach status</label>
                <select id={id("status")} value={status} disabled={busy} onChange={(e) => setStatus(e.target.value as OutreachStatus)}>
                  {OUTREACH_STATUSES.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
                </select>
              </div>
              {status === "consented" && (
                <>
                  <div className="field">
                    <label htmlFor={id("method")}>How they agreed</label>
                    <select id={id("method")} value={method} disabled={busy} aria-required onChange={(e) => setMethod(e.target.value)}>
                      <option value="">Choose…</option>
                      {PERMISSION_METHODS.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor={id("given_on")}>Date they agreed</label>
                    <input id={id("given_on")} type="date" value={givenOn} max={istToday()} disabled={busy} aria-required onChange={(e) => setGivenOn(e.target.value)} />
                  </div>
                  <div className="field" style={{ gridColumn: "1 / -1" }}>
                    <label htmlFor={id("note")}>Note (optional)</label>
                    <input id={id("note")} value={note} maxLength={500} disabled={busy} onChange={(e) => setNote(e.target.value)} />
                  </div>
                </>
              )}
              {s.outreach_status === "consented" && status !== "consented" && (
                <p className="muted" style={{ margin: 0, fontSize: 13, gridColumn: "1 / -1" }}>Saving withdraws the recorded permission: the candidate can no longer be shared.</p>
              )}
            </div>
          ) : (
            <div style={GRID}>
              <div className="field">
                <label htmlFor={id("date")}>Source date</label>
                <input id={id("date")} type="date" value={sourceDate} max={istToday()} disabled={busy} onChange={(e) => setSourceDate(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor={id("referrer_name")}>Referrer name</label>
                <input id={id("referrer_name")} value={referrerName} maxLength={160} disabled={busy} onChange={(e) => setReferrerName(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor={id("portal")}>Portal import reference</label>
                <input id={id("portal")} value={portalRef} maxLength={120} disabled={busy} aria-describedby={id("portal-hint")} onChange={(e) => setPortalRef(e.target.value)} />
                <span id={id("portal-hint")} className="muted" style={{ fontSize: 13 }}>The licensed export or file it came from</span>
              </div>
              {referrer ? (
                <div className="field">
                  <span className="muted" style={{ fontSize: 13 }}>Referrer candidate</span>
                  <span>{referrer.label}{referrer.detail ? ` (${referrer.detail})` : ""}</span>
                  <button type="button" className="btn secondary small" disabled={busy} onClick={() => setReferrer(null)}>Remove referrer candidate</button>
                </div>
              ) : (
                <SearchableSelect id={id("referrer")} label="Referrer candidate" noun="candidate" search={referrerSearch(candidate.id)} disabled={busy} onChange={setReferrer} />
              )}
              {vendor ? (
                <div className="field">
                  <span className="muted" style={{ fontSize: 13 }}>Vendor</span>
                  <span>{vendor.label}</span>
                  <button type="button" className="btn secondary small" disabled={busy} onClick={() => setVendor(null)}>Remove vendor</button>
                </div>
              ) : (
                <SearchableSelect id={id("vendor")} label="Vendor" noun="company" search={vendorSearch} disabled={busy} onChange={setVendor} />
              )}
            </div>
          )}
          <div className="actions">
            <button type="button" className="btn small" disabled={busy} onClick={mode === "outreach" ? saveOutreach : saveSource}>
              {busy ? "Saving…" : mode === "outreach" ? "Save outreach" : "Save source details"}
            </button>
            <button type="button" className="btn secondary small" disabled={busy} onClick={close}>Cancel</button>
          </div>
        </div>
      )}
      {error && <p id={id("error")} tabIndex={-1} className="form-error" role="alert" style={{ margin: "8px 0 0" }}>{error}</p>}
    </section>
  );
}
