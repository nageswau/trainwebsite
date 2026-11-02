"use client";

import { useEffect, useId, useState, type FormEvent } from "react";

import { sendJson } from "@/lib/apiErrors";
import { RISK_THRESHOLDS_URL, riskThresholdUrl, thresholdSummary, type RiskThreshold } from "@/lib/itAtRisk";

type Draft = { min_attendance_percent: string; min_assessment_percent: string; max_consecutive_absences: string; min_sessions: string };

const toDraft = (t: RiskThreshold): Draft => ({
  min_attendance_percent: t.min_attendance_percent?.toString() ?? "",
  min_assessment_percent: t.min_assessment_percent?.toString() ?? "",
  max_consecutive_absences: t.max_consecutive_absences?.toString() ?? "",
  min_sessions: String(t.min_sessions),
});
const optional = (v: string) => (v.trim() === "" ? null : Number(v));

const FIELDS: { key: keyof Draft; label: string; hint: string; min: number; max: number }[] = [
  { key: "min_attendance_percent", label: "Minimum attendance %", hint: "Leave blank to switch off.", min: 0, max: 100 },
  { key: "min_sessions", label: "Sessions before attendance counts", hint: "Avoids flagging in the first week.", min: 1, max: 60 },
  { key: "min_assessment_percent", label: "Minimum assessment average %", hint: "Best attempt per assessment. Blank = off.", min: 0, max: 100 },
  { key: "max_consecutive_absences", label: "Absences in a row", hint: "Flag after this many. Blank = off.", min: 1, max: 60 },
];

/** itc-023 (DEC-SCOPE-352 R1): the IT Admin's at-risk thresholds, one set per programme. A programme with none switched on is not monitored. */
export default function ItRiskThresholdsPanel() {
  const [rows, setRows] = useState<RiskThreshold[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState<RiskThreshold | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const id = useId();

  useEffect(() => {
    let cancelled = false;
    fetch(RISK_THRESHOLDS_URL)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((data: RiskThreshold[]) => !cancelled && setRows(data))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, []);

  function edit(row: RiskThreshold) {
    setEditing(row);
    setDraft(toDraft(row));
    setError("");
    setMessage("");
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!editing || !draft || saving) return;
    setSaving(true);
    setError("");
    const outcome = await sendJson(riskThresholdUrl(editing.program_id), "PUT", {
      min_attendance_percent: optional(draft.min_attendance_percent),
      min_assessment_percent: optional(draft.min_assessment_percent),
      max_consecutive_absences: optional(draft.max_consecutive_absences),
      min_sessions: Number(draft.min_sessions),
    });
    setSaving(false);
    if (!outcome.ok) {
      setError(outcome.message || "The thresholds could not be saved.");
      return;
    }
    const saved = outcome.data as RiskThreshold;
    setRows((current) => current?.map((r) => (r.program_id === saved.program_id ? saved : r)) ?? null);
    setEditing(null);
    setDraft(null);
    setMessage(`Thresholds for ${saved.program} saved. The next daily check (07:00 IST) applies them.`);
  }

  return (
    <section className="card" aria-labelledby={`${id}-title`} style={{ marginBottom: 16, display: "grid", gap: 12 }}>
      <div>
        <h3 id={`${id}-title`} style={{ fontSize: 18, marginBottom: 6 }}>At-risk thresholds</h3>
        <p className="muted" style={{ margin: 0, fontSize: 14 }}>
          Each day at 07:00 IST, active students of a monitored programme are checked. A student who crosses a threshold is flagged, and they,
          their trainer and their counselor are told once; they are told again when they are back on track.
        </p>
      </div>
      {message && <p className="status" role="status" style={{ margin: 0, justifySelf: "start" }}>{message}</p>}
      {failed ? (
        <p className="form-error" role="alert" style={{ margin: 0 }}>Unable to load the thresholds. Refresh the page to try again.</p>
      ) : rows === null ? (
        <p className="muted" role="status" style={{ margin: 0 }}>Loading thresholds…</p>
      ) : rows.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No programmes yet. Add a programme first.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th scope="col">Programme</th><th scope="col">Flag a student when</th><th scope="col"><span className="sr-only">Actions</span></th></tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.program_id}>
                  <td>{row.program}{!row.active && <div className="muted" style={{ fontSize: 13 }}>Inactive programme</div>}</td>
                  <td className={row.monitored ? undefined : "muted"}>{thresholdSummary(row)}</td>
                  <td>
                    <button type="button" className="btn small secondary" onClick={() => edit(row)} aria-label={`Edit thresholds for ${row.program}`}>Edit</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && draft && (
        <form onSubmit={save} aria-labelledby={`${id}-form`} style={{ display: "grid", gap: 12, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
          <h4 id={`${id}-form`} style={{ margin: 0 }}>Thresholds for {editing.program}</h4>
          <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))" }}>
            {FIELDS.map((f) => (
              <div className="field" key={f.key} style={{ margin: 0 }}>
                <label htmlFor={`${id}-${f.key}`}>{f.label}</label>
                <input
                  id={`${id}-${f.key}`} type="number" inputMode="numeric" min={f.min} max={f.max} step={1} required={f.key === "min_sessions"}
                  value={draft[f.key]} aria-describedby={`${id}-${f.key}-hint`}
                  onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}
                />
                <span id={`${id}-${f.key}-hint`} className="muted" style={{ fontSize: 13 }}>{f.hint}</span>
              </div>
            ))}
          </div>
          {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
          <div className="actions">
            <button type="submit" className="btn small" disabled={saving}>{saving ? "Saving…" : "Save thresholds"}</button>
            <button type="button" className="btn small ghost" onClick={() => { setEditing(null); setDraft(null); setError(""); }} disabled={saving}>Cancel</button>
          </div>
        </form>
      )}
    </section>
  );
}
