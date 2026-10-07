"use client";
import { type FormEvent, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { achievedText, isTargetSheet, parseTarget, percentText, TARGET_MAX, TEAM_TARGETS_URL, teamTargetUrl, type TargetSheet } from "@/lib/bdmTargets";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const inputValue = (target: number | null) => (target === null ? "" : String(target));

// bdm-016 (spec §6): one BDM's month -- each KPI's target (an input when the month is editable), achieved (computed by the API; an
// untracked KPI says so, never 0) and achievement %. Save sends only the targets that changed (a blank input clears one), then re-reads
// the sheet. The API decides every rule; a refusal is shown as its own sentence.
export default function BdmTargetsEditor({ initial }: { initial: TargetSheet }) {
  const [sheet, setSheet] = useState(initial);
  const [drafts, setDrafts] = useState<Record<string, string>>(() => Object.fromEntries(initial.kpis.map((k) => [k.key, inputValue(k.target)])));
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false); // `busy` disables Save only after a re-render; a double click must not PUT twice
  const focus = useFocusAfterRender();

  function fail(message: string) {
    setNotice(null);
    setError(message);
    focus("targets-error");
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (inFlight.current) return;
    const items = [];
    for (const kpi of sheet.kpis) {
      const parsed = parseTarget(drafts[kpi.key] ?? "");
      if (!parsed.ok) return fail(`${kpi.label} target must be a whole number from 0 to ${TARGET_MAX}.`);
      if (parsed.value !== kpi.target) items.push({ bdm_user_id: sheet.bdm.id, kpi_key: kpi.key, target: parsed.value });
    }
    setError(null);
    if (items.length === 0) {
      setNotice("No target changed.");
      focus("targets-status");
      return;
    }
    inFlight.current = true;
    setBusy(true);
    const outcome = await sendJson(TEAM_TARGETS_URL, "PUT", { month: sheet.month, items });
    if (!outcome.ok) {
      inFlight.current = false;
      setBusy(false);
      return fail(outcome.message);
    }
    const changed = Number((outcome.data as { changed?: number }).changed ?? items.length);
    try {
      const response = await fetch(teamTargetUrl(sheet.bdm.id, sheet.month));
      const fresh = response.ok ? await response.json() : null;
      if (isTargetSheet(fresh)) {
        setSheet(fresh);
        setDrafts(Object.fromEntries(fresh.kpis.map((k) => [k.key, inputValue(k.target)])));
      }
    } catch {
      // saved; the figures refresh on the next load
    }
    inFlight.current = false;
    setBusy(false);
    setNotice(`Saved ${changed} ${changed === 1 ? "target" : "targets"}.`);
    focus("targets-status");
  }

  return (
    <form onSubmit={(e) => void save(e)} noValidate aria-describedby="targets-status">
      <div className="table-scroll" role="region" aria-labelledby="targets-caption" tabIndex={0}>
        <table className="table">
          <caption id="targets-caption" className="visually-hidden">Targets, achieved and achievement by KPI</caption>
          <thead>
            <tr><th scope="col">KPI</th><th scope="col">Target</th><th scope="col">Achieved</th><th scope="col">Achievement</th></tr>
          </thead>
          <tbody>
            {sheet.kpis.map((kpi) => (
              <tr key={kpi.key}>
                <th scope="row">{kpi.label}<span className="kpi-note muted">{kpi.definition}</span></th>
                <td>
                  {sheet.editable ? (
                    <input type="number" inputMode="numeric" min={0} max={TARGET_MAX} step={1} aria-label={`${kpi.label} target`} placeholder="Not set"
                      value={drafts[kpi.key] ?? ""} disabled={busy} style={{ maxWidth: 120 }}
                      onChange={(e) => setDrafts((d) => ({ ...d, [kpi.key]: e.target.value }))} />
                  ) : (kpi.target ?? "Not set")}
                </td>
                <td>{achievedText(kpi, sheet.month_status)}</td>
                <td>{percentText(kpi)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div id="targets-status" tabIndex={-1} role="status" aria-live="polite" className={notice ? "form-message" : undefined}>{notice}</div>
      {error && <p id="targets-error" tabIndex={-1} className="form-error" role="alert">{error}</p>}
      {sheet.editable && (
        <div className="actions">
          <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : "Save targets"}</button>
          <span className="muted" style={{ fontSize: 13 }}>Leave a target blank to clear it.</span>
        </div>
      )}
    </form>
  );
}
