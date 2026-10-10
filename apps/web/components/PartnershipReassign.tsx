"use client";
import { useRouter } from "next/navigation";
import { type KeyboardEvent, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import type { PickOption } from "@/lib/lookups";
import { REASSIGN_URL, type PartnershipTeamMember, type PartnershipWork } from "@/lib/partnership";
import { plural } from "@/lib/telecaller";
import { managerSearch } from "@/lib/universities";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

export function workText(work: PartnershipWork): string {
  return `primary on ${plural(work.primary, "university", "universities")}, backup on ${work.backup}, ${plural(work.tasks, "open task")}`;
}

// upc-032 (DEC-SCOPE-171): a Team row's Reassign -- every university slot and open task of this manager moves to another active manager
// of the head's team in one server transaction (RA5). The tel-025 AdminTelecallerLifecycle conventions: no dialog library, the group takes
// focus, Escape cancels, an error takes focus; the server re-checks every rule. The cell stays mounted after the refresh, so the notice
// survives the row losing its work.
export default function PartnershipReassign({ row }: { row: PartnershipTeamMember }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<PickOption | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `pm-reassign-${name}-${row.id}`;
  // The picker lists the caller's active managers; the source itself is never a choice.
  const search = async (q: string, signal: AbortSignal) => {
    const page = await managerSearch(q, signal);
    return { ...page, items: page.items.filter((option) => option.id !== row.id) };
  };
  const { work } = row;
  const hasWork = work.primary + work.backup + work.tasks > 0;

  function start() {
    setNotice(null);
    setError(null);
    setPicked(null);
    setOpen(true);
    focus(id("group"));
  }

  function cancel() {
    setOpen(false);
    setError(null);
    focus(id("open"));
  }

  async function submit() {
    if (!picked || busy) return;
    setBusy(true);
    setError(null);
    const outcome = await sendJson(REASSIGN_URL, "POST", { from_user_id: row.id, to_user_id: picked.id });
    setBusy(false);
    if (!outcome.ok) {
      // A 5xx in plain words (bdm-025 QA25-03); a 4xx keeps the server's own sentence.
      setError((outcome.status ?? 0) >= 500 ? `We couldn't reassign ${row.full_name}'s work. Please try again.` : outcome.message);
      focus(id("error"));
      return;
    }
    const moved = outcome.data.moved as PartnershipWork;
    setOpen(false);
    setNotice(`Moved to ${picked.label}: ${workText(moved)}.`);
    router.refresh();
  }

  return (
    <>
      {hasWork && !open && (
        <button id={id("open")} type="button" className="btn secondary small" aria-label={`Reassign ${row.full_name}'s work`} onClick={start}>Reassign</button>
      )}
      {notice && <p role="status" className="muted" style={{ margin: "6px 0 0", fontSize: 13 }}>{notice}</p>}
      {open && (
        <div id={id("group")} tabIndex={-1} role="group" aria-label={`Reassign ${row.full_name}'s work`} className="form" style={{ marginTop: 6 }}
          onKeyDown={(e: KeyboardEvent) => { if (e.key === "Escape") cancel(); }}>
          <p style={{ margin: 0 }}>{row.full_name} is {workText(work)}.</p>
          <SearchableSelect id={id("to")} label="Move everything to" noun="manager" required search={search} disabled={busy} onChange={setPicked} />
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            Where the new manager is already the other manager of a university, they become its primary and the backup is cleared.
          </p>
          <div className="actions">
            <button type="button" className="btn small" disabled={!picked || busy} onClick={() => void submit()}>{busy ? "Reassigning…" : "Reassign"}</button>
            <button type="button" className="btn secondary small" onClick={cancel} disabled={busy}>Cancel</button>
          </div>
          {error && <p id={id("error")} tabIndex={-1} className="form-error" role="alert">{error}</p>}
        </div>
      )}
    </>
  );
}
