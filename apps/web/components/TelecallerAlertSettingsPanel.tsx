"use client";
import { useCallback, useEffect, useRef, useState } from "react";

import { NOT_COMPLETED, detailMessage, sendJson } from "@/lib/apiErrors";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

// tel-020 (DEC-SCOPE-107 AL1, AL11; API §12AA): each team's alert thresholds. The API checks every rule (whole hours 1-168, who may save);
// the inputs only mirror the range. The beat reads the values on its next run (AC4).
export const SETTINGS_URL = "/api/v1/telecaller/settings";
const FIELDS = [
  { key: "not_contacted_hours", label: "Lead not contacted after (hours)", hint: "Alert when a lead is still waiting for its first connected call." },
  { key: "hot_pending_hours", label: "Hot lead pending after (hours)", hint: "Alert when a hot lead has had no call for this long." },
] as const;
type Key = (typeof FIELDS)[number]["key"];
type TeamSettings = Record<Key, number> & { team: string; team_label: string; updated_at: string; updated_by: { id: string; full_name: string } | null };

const changedText = (row: TeamSettings) =>
  row.updated_by
    ? `Last changed by ${row.updated_by.full_name} on ${new Date(row.updated_at).toLocaleString("en-GB", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" })} IST.`
    : "Default thresholds (never changed).";

function TeamCard({ initial }: { initial: TeamSettings }) {
  const [row, setRow] = useState(initial);
  const [values, setValues] = useState<Record<Key, string>>({ not_contacted_hours: String(initial.not_contacted_hours), hot_pending_hours: String(initial.hot_pending_hours) });
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const inFlight = useRef(false);
  const id = `alerts-${row.team}`;

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setFeedback(null);
    const body = Object.fromEntries(FIELDS.map((f) => [f.key, Number(values[f.key])]));
    const outcome = await sendJson(`${SETTINGS_URL}/${row.team}`, "PUT", body);
    inFlight.current = false;
    setBusy(false);
    if (outcome.ok) {
      setRow(outcome.data as TeamSettings);
      setFeedback({ text: "Saved. Alerts use the new thresholds from the next check (within 15 minutes).", tone: "success" });
    } else {
      setFeedback({ text: outcome.message, tone: "error" });
    }
  }

  return (
    <section className="action-card" aria-labelledby={`${id}-title`}>
      <form className="form" onSubmit={save} aria-describedby={`${id}-feedback`}>
        <h3 id={`${id}-title`}>{row.team_label} team</h3>
        {FIELDS.map((f) => (
          <div className="field" key={f.key}>
            <label htmlFor={`${id}-${f.key}`}>{f.label}</label>
            <input id={`${id}-${f.key}`} type="number" inputMode="numeric" min={1} max={168} step={1} required disabled={busy}
                   aria-describedby={`${id}-${f.key}-hint`} value={values[f.key]} onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))} />
            <p id={`${id}-${f.key}-hint`} className="muted">{f.hint} 1–168.</p>
          </div>
        ))}
        <p className="muted">{changedText(row)}</p>
        <button className="btn" disabled={busy} aria-label={`Save ${row.team_label} thresholds`}>{busy ? "Saving…" : "Save"}</button>
        <div id={`${id}-feedback`} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
          {feedback?.text}
        </div>
      </form>
    </section>
  );
}

export default function TelecallerAlertSettingsPanel() {
  const [rows, setRows] = useState<TeamSettings[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    setRows(null);
    try {
      const response = await fetch(SETTINGS_URL);
      const data = await response.json().catch(() => null);
      if (!response.ok || !Array.isArray(data?.items)) throw new Error(detailMessage(data?.detail, "Could not load the alert settings."));
      setRows(data.items);
    } catch (e) {
      setError(e instanceof TypeError ? NOT_COMPLETED : (e as Error).message);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  if (error) {
    return (
      <div className="action-card">
        <p className="form-error" role="alert">{error}</p>
        <button className="btn secondary" onClick={() => void load()}>Try again</button>
      </div>
    );
  }
  if (!rows) return <p className="muted" role="status">Loading alert settings…</p>;
  return <>{rows.map((row) => <TeamCard key={row.team} initial={row} />)}</>;
}
