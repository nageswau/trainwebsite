"use client";
import { type KeyboardEvent, useCallback, useEffect, useMemo, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import {
  type BdmAdminRow, type BdmPortfolio, bdmSearch, deactivateUrl, handoverUrl, hasOpenWork, portfolioText, portfolioUrl,
} from "@/lib/bdm";
import type { PickOption } from "@/lib/lookups";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Moved = Omit<BdmPortfolio, "trips">;
type Choice = "reassign" | "leave";

// bdm-025 (DEC-SCOPE-079): the inline group behind a BDM row's Deactivate (pick who takes over -- another BDM of the same module, or
// keep the work with them for a later handover, L3) and an inactive row's Hand over. The counts come from the server first, so the
// admin sees what moves; the server re-checks every rule and answers one message for an invalid target. Same inline-group
// conventions as BdmConfirm: the codebase has no dialog library, Escape cancels, an error takes focus.
export default function AdminBdmHandover({ row, mode, onDone, onCancel }: {
  row: BdmAdminRow; mode: "deactivate" | "handover"; onDone: (notice: string) => void; onCancel: () => void;
}) {
  const [counts, setCounts] = useState<BdmPortfolio | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [choice, setChoice] = useState<Choice | null>(mode === "handover" ? "reassign" : null);
  const [picked, setPicked] = useState<PickOption | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `bdm-${name}-${row.id}`;
  const search = useMemo(() => bdmSearch(row.bdm_type, row.id), [row.bdm_type, row.id]);
  const deactivating = mode === "deactivate";

  const load = useCallback(() => {
    setLoadFailed(false);
    setCounts(null);
    fetch(portfolioUrl(row.id))
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (!response.ok || typeof body?.organizations !== "number") throw new Error("not a portfolio");
        setCounts(body);
      })
      .catch(() => setLoadFailed(true));
  }, [row.id]);

  useEffect(load, [load]);
  // QA25-01: the trigger button unmounts when this opens, so the group takes focus -- Escape and Tab work from here.
  const groupId = id("handover-group");
  useEffect(() => focus(groupId), [focus, groupId]);

  const open = counts !== null && hasOpenWork(counts);
  // With nothing open there is nothing to choose: deactivation keeps (= moves) nothing.
  const effective: Choice | null = counts !== null && !open ? "leave" : choice;
  const ready = counts !== null && (effective === "leave" || (effective === "reassign" && picked !== null));

  async function submit() {
    if (!ready || busy) return;
    setBusy(true);
    setError(null);
    const outcome = deactivating
      ? await sendJson(deactivateUrl(row.id), "POST", effective === "reassign" ? { mode: "reassign", reassign_to: picked?.id } : { mode: "leave" })
      : await sendJson(handoverUrl(row.id), "POST", { reassign_to: picked?.id });
    setBusy(false);
    if (!outcome.ok) {
      // QA25-03: a 5xx in plain words (bdm-006 QA6-04); a 4xx keeps the server's own sentence.
      const failed = deactivating ? `We couldn't deactivate ${row.full_name}.` : `We couldn't hand over ${row.full_name}'s work.`;
      setError((outcome.status ?? 0) >= 500 ? `${failed} Please try again.` : outcome.message);
      focus(id("handover-error"));
      return;
    }
    const moved = outcome.data.moved as Moved | undefined;
    const handed = moved ? portfolioText(moved) : "";
    if (!deactivating) return onDone(`Handed over ${handed} from ${row.full_name} to ${picked?.label}.`);
    const cancelled = Number(outcome.data.trips_cancelled ?? 0);
    const detail = effective === "reassign" ? ` ${handed} handed over to ${picked?.label}.`
      : open ? " Their open work stays with them until you hand it over." : "";
    onDone(`Deactivated ${row.full_name}.${detail}${cancelled ? ` ${cancelled} not-started ${cancelled === 1 ? "trip was" : "trips were"} cancelled.` : ""}`);
  }

  const label = deactivating ? `Deactivate ${row.full_name}` : `Hand over ${row.full_name}'s open work`;
  return (
    <div id={groupId} tabIndex={-1} role="group" aria-label={label} className="form" style={{ marginTop: 6 }}
      onKeyDown={(e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); }}>
      {loadFailed ? (
        <>
          <p className="form-error" role="alert">Unable to load {row.full_name}&apos;s open work.</p>
          <div className="actions">
            <button type="button" className="btn secondary small" onClick={load}>Retry</button>
            <button type="button" className="btn secondary small" onClick={onCancel}>{deactivating ? "Keep active" : "Close"}</button>
          </div>
        </>
      ) : counts === null ? (
        <p className="muted" role="status">Loading open work…</p>
      ) : (
        <>
          <p style={{ margin: 0 }}>{open ? `Open work: ${portfolioText(counts)}.` : `${row.full_name} has no open work to hand over.`}</p>
          {deactivating && counts.trips > 0 && (
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>
              {counts.trips} {counts.trips === 1 ? "trip" : "trips"} not yet started will be cancelled.
            </p>
          )}
          {deactivating && open && (
            <fieldset className="form-section">
              <legend>Who takes over their open work?</legend>
              <label style={{ display: "block" }}>
                <input type="radio" name={id("choice")} checked={choice === "reassign"} onChange={() => setChoice("reassign")} disabled={busy} />{" "}
                Hand over to another BDM
              </label>
              <label style={{ display: "block" }}>
                <input type="radio" name={id("choice")} checked={choice === "leave"} onChange={() => setChoice("leave")} disabled={busy} />{" "}
                Keep with {row.full_name} for now (hand over later)
              </label>
            </fieldset>
          )}
          {open && effective === "reassign" && (
            <SearchableSelect id={id("handover-to")} label="Hand over to" noun="BDM" required search={search} disabled={busy} onChange={setPicked} />
          )}
          {deactivating && <p className="muted" style={{ margin: 0, fontSize: 13 }}>Their history stays with them; they can no longer sign in.</p>}
          <div className="actions">
            {(deactivating || open) && (
              <button type="button" className="btn small" disabled={!ready || busy} onClick={() => void submit()}>
                {busy ? (deactivating ? "Deactivating…" : "Handing over…") : deactivating ? "Confirm deactivate" : "Hand over"}
              </button>
            )}
            <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>{deactivating ? "Keep active" : open ? "Cancel" : "Close"}</button>
          </div>
        </>
      )}
      {error && <p id={id("handover-error")} tabIndex={-1} className="form-error" role="alert">{error}</p>}
    </div>
  );
}
