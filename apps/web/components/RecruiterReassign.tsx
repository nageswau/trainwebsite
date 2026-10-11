"use client";
import { useRouter } from "next/navigation";
import { type KeyboardEvent, useMemo, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import type { PickOption } from "@/lib/lookups";
import { RECRUITER_REASSIGN_URL, type RecruiterTeamMember, type RecruiterWork } from "@/lib/recruiter";
import { recruiterSearch } from "@/lib/recruiterCompanies";
import { plural } from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

export function workText(work: RecruiterWork): string {
  return `${plural(work.companies, "company", "companies")}, ${plural(work.requirements, "requirement")} and ${plural(work.follow_ups, "open follow-up")}`;
}

// rec-037 (DEC-SCOPE-177): a Team row's Reassign -- every company and requirement of this recruiter (open follow-ups ride with their
// company) moves to another active recruiter of the manager's team in one server transaction (RC5). The upc-032 PartnershipReassign
// conventions: no dialog library, the group takes focus, Escape cancels, an error takes focus; the server re-checks every rule. The cell
// stays mounted after the refresh, so the notice survives the row losing its work.
export default function RecruiterReassign({ row }: { row: RecruiterTeamMember }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<PickOption | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `rec-reassign-${name}-${row.id}`;
  const search = useMemo(() => recruiterSearch(row.id), [row.id]); // active team-mates; the source itself is never a choice
  const { work } = row;
  const hasWork = work.companies + work.requirements > 0;

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
    const outcome = await sendJson(RECRUITER_REASSIGN_URL, "POST", { from_user_id: row.id, to_user_id: picked.id });
    setBusy(false);
    if (!outcome.ok) {
      // A 5xx in plain words (bdm-025 QA25-03); a 4xx keeps the server's own sentence.
      setError((outcome.status ?? 0) >= 500 ? `We couldn't reassign ${row.full_name}'s work. Please try again.` : outcome.message);
      focus(id("error"));
      return;
    }
    setOpen(false);
    setNotice(`Moved to ${picked.label}: ${workText(outcome.data.moved as RecruiterWork)}.`);
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
          <p style={{ margin: 0 }}>{row.full_name} has {workText(work)}.</p>
          <SearchableSelect id={id("to")} label="Move everything to" noun="recruiter" required search={search} disabled={busy} onChange={setPicked} />
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            Every company (archived ones too) and requirement moves; open follow-ups go with their company.
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
