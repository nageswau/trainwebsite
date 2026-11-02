"use client";
import { useCallback, useEffect, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { STRATEGY_LABEL, STRATEGY_URL, type Strategy, type TeamStrategy } from "@/lib/telecallerDistribution";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

// itc-006 (DEC-SCOPE-337 D3/D6): each team's "When no rule matches" setting -- round robin or the fewest open leads. Every manager sees
// both teams; only a manager with telecallers on a team (or a super admin) may change it -- the API decides and `editable` mirrors it.
function TeamCard({ initial }: { initial: TeamStrategy }) {
  const [saved, setSaved] = useState(initial.strategy);
  const [value, setValue] = useState<Strategy>(initial.strategy);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const inFlight = useRef(false); // `busy` disables the button only after a re-render; a double click must not PUT twice
  const id = `strategy-${initial.team}`;

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setFeedback(null);
    const outcome = await sendJson(`${STRATEGY_URL}/${initial.team}`, "PUT", { strategy: value });
    inFlight.current = false;
    setBusy(false);
    if (outcome.ok) {
      const next = (outcome.data as TeamStrategy).strategy;
      setSaved(next);
      setValue(next);
      setFeedback({ text: `Saved. New ${initial.team_label} leads that no rule matches go to ${STRATEGY_LABEL[next].charAt(0).toLowerCase()}${STRATEGY_LABEL[next].slice(1)}.`, tone: "success" });
    } else {
      setFeedback({ text: outcome.message, tone: "error" });
    }
  }

  return (
    <section className="action-card telecaller-strategy" aria-labelledby={`${id}-title`}>
      <form className="form" onSubmit={save} aria-describedby={`${id}-feedback`}>
        <h3 id={`${id}-title`}>{initial.team_label} team</h3>
        <div className="field">
          <label htmlFor={`${id}-select`}>When no rule matches</label>
          <select id={`${id}-select`} value={value} disabled={busy || !initial.editable} aria-describedby={`${id}-hint`}
                  onChange={(e) => { setValue(e.target.value as Strategy); setFeedback(null); }}>
            {(Object.keys(STRATEGY_LABEL) as Strategy[]).map((s) => <option key={s} value={s}>{STRATEGY_LABEL[s]}</option>)}
          </select>
          <p id={`${id}-hint`} className="muted">
            {initial.editable
              ? "Open leads are every lead a telecaller holds that is not closed or converted. Inactive telecallers are never chosen."
              : `Only a manager with telecallers on the ${initial.team_label} team can change this.`}
          </p>
        </div>
        {initial.editable && (
          <button className="btn" disabled={busy || value === saved} aria-label={`Save ${initial.team_label} strategy`}>{busy ? "Saving…" : "Save"}</button>
        )}
        <div id={`${id}-feedback`} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
          {feedback?.text}
        </div>
      </form>
    </section>
  );
}

export default function TelecallerStrategyPanel() {
  const [rows, setRows] = useState<TeamStrategy[] | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setFailed(false);
    setRows(null);
    try {
      const response = await fetch(STRATEGY_URL);
      const data = await response.json().catch(() => null);
      if (!response.ok || !Array.isArray(data?.items)) throw new Error();
      setRows(data.items);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  if (failed) {
    return (
      <div className="action-card">
        <p className="form-error" role="alert">Unable to load the team strategies.</p>
        <button type="button" className="btn secondary small" aria-label="Retry loading strategies" onClick={() => void load()}>Retry</button>
      </div>
    );
  }
  if (!rows) return <p className="muted" role="status">Loading team strategies…</p>;
  return <>{rows.map((row) => <TeamCard key={row.team} initial={row} />)}</>;
}
