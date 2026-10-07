"use client";
import { type KeyboardEvent, useCallback, useEffect, useMemo, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import type { PickOption } from "@/lib/lookups";
import {
  type OpenWork, type TelecallerAdminRow, TEAM_LABEL, lifecycleUrl, managerSearch, openWorkText, openWorkUrl, otherTeam, plural, telecallerSearch,
} from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Mode = "deactivate" | "handover" | "move";
type Choice = "telecaller" | "queue";

const COPY: Record<Mode, { label: (name: string) => string; confirm: string; busy: string; cancel: string; failed: (name: string) => string }> = {
  deactivate: { label: (n) => `Deactivate ${n}`, confirm: "Confirm deactivate", busy: "Deactivating…", cancel: "Keep active", failed: (n) => `We couldn't deactivate ${n}.` },
  handover: { label: (n) => `Reassign ${n}'s open leads`, confirm: "Reassign", busy: "Reassigning…", cancel: "Cancel", failed: (n) => `We couldn't reassign ${n}'s open leads.` },
  move: { label: (n) => `Move ${n} to another team`, confirm: "Move team", busy: "Moving…", cancel: "Cancel", failed: (n) => `We couldn't move ${n}.` },
};

// tel-025 (DEC-SCOPE-104): the inline group behind a telecaller row's Deactivate, Move team and (inactive rows) Reassign open work. The
// open-work counts come from the server first, so the admin sees what moves; open leads go to another telecaller of the SAME team or to
// that team's unassigned queue (LC3). The server re-checks every rule and answers one message for an invalid target. The AdminBdmHandover
// conventions: no dialog library, the group takes focus, Escape cancels, an error takes focus.
export default function AdminTelecallerLifecycle({ row, mode, onDone, onCancel }: {
  row: TelecallerAdminRow; mode: Mode; onDone: (notice: string) => void; onCancel: () => void;
}) {
  const [counts, setCounts] = useState<OpenWork | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [choice, setChoice] = useState<Choice | null>(null);
  const [picked, setPicked] = useState<PickOption | null>(null);
  const [manager, setManager] = useState<PickOption | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `tel-${name}-${row.id}`;
  const team = TEAM_LABEL[row.team];
  const newTeam = otherTeam(row.team);
  const search = useMemo(() => telecallerSearch(row.team, row.id), [row.team, row.id]);
  const copy = COPY[mode];

  const load = useCallback(() => {
    setLoadFailed(false);
    setCounts(null);
    fetch(openWorkUrl(row.id))
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (!response.ok || typeof body?.leads !== "number") throw new Error("not open work");
        setCounts(body);
      })
      .catch(() => setLoadFailed(true));
  }, [row.id]);

  useEffect(load, [load]);
  const groupId = id("lifecycle-group");
  useEffect(() => focus(groupId), [focus, groupId]);

  const open = counts !== null && counts.leads > 0;
  const ready = counts !== null && (!open || choice === "queue" || (choice === "telecaller" && picked !== null));

  function leadsTo(moved: OpenWork): string {
    if (!moved.leads) return "";
    return choice === "telecaller" ? `now with ${picked?.label}` : `moved to the ${team} unassigned queue`;
  }

  async function submit() {
    if (!ready || busy) return;
    setBusy(true);
    setError(null);
    const body: Record<string, string> = open && choice ? { target: choice, ...(choice === "telecaller" && picked ? { reassign_to: picked.id } : {}) } : {};
    if (mode === "move") {
      body.team = newTeam;
      if (manager && manager.id !== row.reporting_manager.id) body.reporting_manager_user_id = manager.id;
    }
    const outcome = await sendJson(lifecycleUrl(row.id, mode === "move" ? "move-team" : mode), "POST", body);
    setBusy(false);
    if (!outcome.ok) {
      // A 5xx in plain words (bdm-025 QA25-03); a 4xx keeps the server's own sentence.
      setError((outcome.status ?? 0) >= 500 ? `${copy.failed(row.full_name)} Please try again.` : outcome.message);
      focus(id("lifecycle-error"));
      return;
    }
    const moved = (outcome.data.moved as OpenWork | undefined) ?? { leads: 0, follow_ups: 0, appointments: 0 };
    const leads = moved.leads ? ` ${plural(moved.leads, "open lead")} ${leadsTo(moved)}.` : "";
    if (mode === "handover") return onDone(`${plural(moved.leads, "open lead")} from ${row.full_name} ${leadsTo(moved)}.`);
    if (mode === "move") return onDone(`Moved ${row.full_name} to the ${TEAM_LABEL[newTeam]} team; they sign in again there.${leads}`);
    onDone(`Deactivated ${row.full_name}.${leads}`);
  }

  const canSubmit = mode !== "handover" || open;
  return (
    <div id={groupId} tabIndex={-1} role="group" aria-label={copy.label(row.full_name)} className="form" style={{ marginTop: 6 }}
      onKeyDown={(e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); }}>
      {loadFailed ? (
        <>
          <p className="form-error" role="alert">Unable to load {row.full_name}&apos;s open work.</p>
          <div className="actions">
            <button type="button" className="btn secondary small" onClick={load}>Retry</button>
            <button type="button" className="btn secondary small" onClick={onCancel}>{copy.cancel}</button>
          </div>
        </>
      ) : counts === null ? (
        <p className="muted" role="status">Loading open work…</p>
      ) : (
        <>
          {mode === "move" && (
            <p style={{ margin: 0 }}>Move {row.full_name} from the {team} team to the {TEAM_LABEL[newTeam]} team. Their open leads stay on the {team} team.</p>
          )}
          <p style={{ margin: 0 }}>{open ? `Open work: ${openWorkText(counts)}.` : `${row.full_name} has no open leads.`}</p>
          {open && (
            <fieldset className="form-section">
              <legend>Who takes over their open leads?</legend>
              <label style={{ display: "block" }}>
                <input type="radio" name={id("choice")} checked={choice === "telecaller"} onChange={() => setChoice("telecaller")} disabled={busy} />{" "}
                Another {team} telecaller
              </label>
              <label style={{ display: "block" }}>
                <input type="radio" name={id("choice")} checked={choice === "queue"} onChange={() => setChoice("queue")} disabled={busy} />{" "}
                {team} unassigned queue
              </label>
            </fieldset>
          )}
          {open && choice === "telecaller" && (
            <SearchableSelect id={id("reassign-to")} label="Hand the leads to" noun="telecaller" required search={search} disabled={busy} onChange={setPicked} />
          )}
          {mode === "move" && (
            <SearchableSelect id={id("move-manager")} label="Reporting manager" noun="manager" search={managerSearch} disabled={busy} onChange={setManager}
              initial={{ id: row.reporting_manager.id, label: row.reporting_manager.full_name }} />
          )}
          {mode !== "handover" && (
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>
              {mode === "deactivate" ? "Their call history stays with them; they are signed out and can no longer sign in."
                : `They are signed out and sign in again at the ${TEAM_LABEL[newTeam]} portal.`}
            </p>
          )}
          <div className="actions">
            {canSubmit && (
              <button type="button" className="btn small" disabled={!ready || busy} onClick={() => void submit()}>{busy ? copy.busy : copy.confirm}</button>
            )}
            <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>{canSubmit ? copy.cancel : "Close"}</button>
          </div>
        </>
      )}
      {error && <p id={id("lifecycle-error")} tabIndex={-1} className="form-error" role="alert">{error}</p>}
    </div>
  );
}
