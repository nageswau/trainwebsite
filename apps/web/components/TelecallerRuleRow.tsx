"use client";
import { useState } from "react";

import { sendJson, sendRequest } from "@/lib/apiErrors";
import { TEAM_LABEL, statusLabel, type TelecallerTeamRow } from "@/lib/telecaller";
import { RULES_URL, assignTargets, ruleMatch, type Rule } from "@/lib/telecallerDistribution";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// tel-007 (DI3, D6): one rule -- its match, team and telecaller; for a rule whose telecaller reports to me, Change telecaller (inline
// select, Save / Cancel, Esc cancels) and Delete with an inline confirm. A rule for another manager's report is read-only.
export default function TelecallerRuleRow({ rule, reports, onChanged }: { rule: Rule; reports: TelecallerTeamRow[]; onChanged: (notice: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `rule-${name}-${rule.id}`;
  const match = ruleMatch(rule);
  const targets = assignTargets(reports, rule.team);

  function close() {
    setEditing(false);
    setError(null);
    focus(id("change"));
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const telecaller = String(new FormData(event.currentTarget).get("telecaller_user_id") ?? "");
    setBusy(true);
    const outcome = await sendJson(`${RULES_URL}/${rule.id}`, "PATCH", { telecaller_user_id: telecaller });
    setBusy(false);
    if (!outcome.ok) {
      setError(outcome.message);
      return focus(id("error"));
    }
    setEditing(false);
    onChanged(`${match} now goes to ${targets.find((t) => t.id === telecaller)?.full_name ?? "the chosen telecaller"}.`);
  }

  async function remove() {
    setBusy(true);
    const outcome = await sendRequest(`${RULES_URL}/${rule.id}`, { method: "DELETE" });
    setBusy(false);
    setConfirming(false);
    if (!outcome.ok) {
      setError(outcome.message);
      return focus(id("error"));
    }
    onChanged(`Deleted ${match}.`);
  }

  return (
    <tr>
      <td data-label="Rule">{match}</td>
      <td data-label="Team">{TEAM_LABEL[rule.team]}</td>
      <td data-label="Telecaller">
        {rule.telecaller.full_name}{!rule.telecaller.active && <> <span className="badge">{statusLabel(false)} — skipped</span></>}
      </td>
      <td data-label="Actions">
        {!rule.editable ? (
          <span className="muted" style={{ fontSize: 13 }}>Another manager&apos;s report</span>
        ) : editing ? (
          <form className="form" onSubmit={save} onKeyDown={(e) => { if (e.key === "Escape") close(); }} aria-describedby={id("error")}>
            <div className="field">
              <label htmlFor={id("select")}>New telecaller for {match}</label>
              <select id={id("select")} name="telecaller_user_id" defaultValue={rule.telecaller.id} required autoFocus disabled={busy}>
                {!targets.some((t) => t.id === rule.telecaller.id) && <option value={rule.telecaller.id}>{rule.telecaller.full_name} (inactive)</option>}
                {targets.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}
              </select>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className="btn small" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
              <button type="button" className="btn secondary small" onClick={close} disabled={busy}>Cancel</button>
            </div>
          </form>
        ) : (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button id={id("change")} type="button" className="btn secondary small" aria-label={`Change telecaller for ${match}`} onClick={() => { setError(null); setEditing(true); }} disabled={busy}>Change telecaller</button>
            {!confirming && <button id={id("delete")} type="button" className="btn secondary small" aria-label={`Delete ${match}`} onClick={() => { setError(null); setConfirming(true); focus(id("confirm")); }} disabled={busy}>Delete</button>}
          </div>
        )}
        {confirming && (
          <div role="group" aria-label={`Confirm deleting ${match}`} style={{ marginTop: 6 }}>
            <p className="muted" style={{ fontSize: 13 }}>New leads stop following this rule; leads already assigned keep their telecaller.</p>
            <button id={id("confirm")} type="button" className="btn small" onClick={remove} disabled={busy}>{busy ? "Deleting…" : "Confirm delete"}</button>{" "}
            <button type="button" className="btn secondary small" onClick={() => { setConfirming(false); focus(id("delete")); }} disabled={busy}>Keep rule</button>
          </div>
        )}
        <div id={id("error")} tabIndex={-1} className={error ? "form-error" : undefined} role="alert">{error}</div>
      </td>
    </tr>
  );
}
