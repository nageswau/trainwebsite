"use client";

import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import { sendJson, sendRequest } from "@/lib/apiErrors";
import { MERGE_FIELDS, MERGE_MOVED, type MergeField, type MergePreview } from "@/lib/telecallerLeads";

const empty = (value: unknown) => value === null || value === undefined || value === "";
const shown = (value: unknown) => (empty(value) ? <span className="muted">—</span> : String(value));

/** itc-007 (DEC-SCOPE-339): "Merge a duplicate" -- a manager (or admin) enters the duplicate's Lead ID, compares the two leads side by
 *  side, picks which values to keep where both have one (an empty value here is always filled from the duplicate), and merges it into
 *  this lead. `url` is this lead's API path (telecaller or admin); the API decides scope and every rule and its refusals are shown. */
export default function LeadMergeForm({ url, leadCode, onMerged }: { url: string; leadCode: string; onMerged: (victimCode: string) => void }) {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [preview, setPreview] = useState<MergePreview | null>(null);
  const [useVictim, setUseVictim] = useState<MergeField[]>([]);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const id = useId();
  const opener = useRef<HTMLButtonElement>(null);
  const refocus = useRef(false);
  useEffect(() => {
    if (!open && refocus.current) {
      refocus.current = false;
      opener.current?.focus();
    }
  }, [open]);

  function close() {
    refocus.current = true;
    setOpen(false);
    setCode("");
    setPreview(null);
    setUseVictim([]);
    setReason("");
    setError("");
  }

  async function compare(event: FormEvent) {
    event.preventDefault();
    const victim = code.trim().toUpperCase();
    if (!victim) return setError("Enter the Lead ID of the duplicate lead.");
    setError("");
    setPreview(null);
    setUseVictim([]);
    setBusy(true);
    const outcome = await sendRequest(`${url}/merge-preview?${new URLSearchParams({ victim })}`, { method: "GET" });
    setBusy(false);
    const data = outcome.ok ? (outcome.data as MergePreview) : null;
    if (!data?.victim || !data.survivor) return setError(outcome.ok ? "Unable to compare the leads." : outcome.message);
    setPreview(data);
  }

  async function merge() {
    if (!preview) return;
    setError("");
    setBusy(true);
    const text = reason.trim();
    const outcome = await sendJson(`${url}/merge`, "POST", { victim: preview.victim.lead_code, use_victim: useVictim, ...(text ? { reason: text } : {}) });
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    const victimCode = preview.victim.lead_code;
    close();
    onMerged(victimCode);
  }

  if (!open) {
    return (
      <button ref={opener} type="button" className="btn secondary small" aria-label={`Merge a duplicate into ${leadCode}`} onClick={() => setOpen(true)}>
        Merge a duplicate
      </button>
    );
  }
  const moved = preview ? MERGE_MOVED.filter(([key]) => preview.moved[key] > 0).map(([key, label]) => `${preview.moved[key]} ${label.toLowerCase()}`) : [];
  const pick = (field: MergeField, fromVictim: boolean) =>
    setUseVictim((fields) => (fromVictim ? [...fields.filter((f) => f !== field), field] : fields.filter((f) => f !== field)));

  return (
    <section aria-labelledby={`${id}-heading`} className="action-card" style={{ display: "grid", gap: 10, width: "100%" }}>
      <h3 id={`${id}-heading`} style={{ margin: 0 }}>Merge a duplicate into {leadCode}</h3>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        Its calls, follow-ups, notes, messages and appointments move to this lead. The duplicate is closed and can no longer be changed.
      </p>
      <form onSubmit={compare} noValidate style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor={`${id}-code`}>Lead ID of the duplicate</label>
          <input id={`${id}-code`} value={code} maxLength={20} placeholder="LD-000123" autoComplete="off" autoFocus disabled={busy}
            onChange={(e) => { setCode(e.target.value); setPreview(null); }} />
        </div>
        <button type="submit" className="btn secondary small" disabled={busy}>{busy && !preview ? "Comparing…" : "Compare"}</button>
      </form>

      {preview && (
        <>
          <div style={{ overflowX: "auto" }}>
            <table className="table compact">
              <caption style={{ textAlign: "left", fontWeight: 600 }}>Compare the two leads</caption>
              <thead>
                <tr>
                  <th scope="col">Field</th>
                  <th scope="col">This lead ({preview.survivor.lead_code})</th>
                  <th scope="col">Duplicate ({preview.victim.lead_code})</th>
                </tr>
              </thead>
              <tbody>
                {MERGE_FIELDS.map(({ key, label }) => {
                  const mine = preview.survivor[key];
                  const theirs = preview.victim[key];
                  const choice = !empty(mine) && !empty(theirs) && String(mine) !== String(theirs);
                  const fromVictim = useVictim.includes(key);
                  const cell = (value: unknown, victim: boolean) => choice ? (
                    <label style={{ display: "flex", gap: 6, alignItems: "baseline", overflowWrap: "anywhere" }}>
                      <input type="radio" name={`${id}-${key}`} checked={fromVictim === victim} disabled={busy}
                        aria-label={`Keep ${String(value)} for ${label}`} onChange={() => pick(key, victim)} />
                      {String(value)}
                    </label>
                  ) : <span style={{ overflowWrap: "anywhere" }}>{shown(value)}</span>;
                  return (
                    <tr key={key}>
                      <th scope="row">{label}</th>
                      <td>{cell(mine, false)}{!choice && empty(mine) && !empty(theirs) && <span className="muted" style={{ fontSize: 12 }}> (filled from the duplicate)</span>}</td>
                      <td>{cell(theirs, true)}</td>
                    </tr>
                  );
                })}
                <tr>
                  <th scope="row">Stage</th>
                  <td>{preview.survivor.status_label}</td>
                  <td>{preview.victim.status_label} → Duplicate</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p style={{ margin: 0 }}>{moved.length ? `Moves to this lead: ${moved.join(", ")}.` : "The duplicate has no activity to move."}</p>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor={`${id}-reason`}>Reason (optional)</label>
            <textarea id={`${id}-reason`} rows={2} maxLength={500} value={reason} disabled={busy} onChange={(e) => setReason(e.target.value)} />
          </div>
        </>
      )}
      {error && <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>{error}</p>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }} aria-live="polite">
        {preview && <button type="button" className="btn small" disabled={busy} onClick={() => void merge()}>{busy ? "Merging…" : "Merge into this lead"}</button>}
        <button type="button" className="btn secondary small" disabled={busy} onClick={close}>Cancel</button>
      </div>
    </section>
  );
}
