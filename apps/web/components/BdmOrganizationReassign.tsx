"use client";
import { type KeyboardEvent, useMemo, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { isOrganizationBody, type Organization, ORGS_URL, teamSearch } from "@/lib/bdmOrganizations";
import type { LookupPage, PickOption } from "@/lib/lookups";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-002 AC4: a manager (or super_admin) moves the organization to another active BDM of the same type in their team. The picker
// only offers those (minus the current assignee); the server re-checks every rule and answers one message for any invalid target.
export default function BdmOrganizationReassign({ organization, onChanged }: { organization: Organization; onChanged: (o: Organization, notice: string) => void }) {
  const [picked, setPicked] = useState<PickOption | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const assignee = organization.assigned_bdm.id;
  const search = useMemo(() => {
    const team = teamSearch(organization.bdm_type);
    return async (q: string, signal: AbortSignal): Promise<LookupPage> => {
      const page = await team(q, signal);
      return { ...page, items: page.items.filter((item) => item.id !== assignee) };
    };
  }, [organization.bdm_type, assignee]);
  const triggerId = `org-${organization.id}-reassign`;

  async function reassign() {
    if (!picked) return;
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(`${ORGS_URL}/${organization.id}/assign`, "POST", { bdm_user_id: picked.id });
    setBusy(false);
    setConfirming(false);
    if (outcome.ok && isOrganizationBody(outcome.data)) onChanged(outcome.data.organization, `Reassigned to ${picked.label}.`);
    else setFailure(outcome.ok ? "Unable to reassign this organization." : outcome.message);
  }
  const cancel = () => {
    setConfirming(false);
    focus(triggerId);
  };

  return (
    <section className="action-card wide" aria-labelledby={`org-${organization.id}-assignment`}>
      <h3 id={`org-${organization.id}-assignment`}>Assignment</h3>
      <p style={{ margin: 0 }}>
        Assigned to {organization.assigned_bdm.full_name}
        {organization.assigned_bdm.active ? "" : " (inactive)"}.
      </p>
      <SearchableSelect
        key={assignee}
        label="Reassign to"
        noun="BDM"
        search={search}
        onChange={(option) => {
          setPicked(option);
          setConfirming(false);
        }}
      />
      <div>
        <button id={triggerId} type="button" className="btn secondary small" disabled={!picked || busy} onClick={() => setConfirming(true)}>
          Reassign
        </button>
      </div>
      {confirming && picked && (
        <div role="group" aria-label="Confirm reassign" onKeyDown={(e: KeyboardEvent) => e.key === "Escape" && cancel()}>
          <p>
            Reassign {organization.code} to {picked.label}?
          </p>
          <button type="button" className="btn small" autoFocus onClick={() => void reassign()} disabled={busy}>
            {busy ? "Reassigning…" : "Yes, reassign"}
          </button>{" "}
          <button type="button" className="btn secondary small" onClick={cancel}>
            Cancel
          </button>
        </div>
      )}
      {failure && (
        <p className="form-error" role="alert">
          {failure}
        </p>
      )}
    </section>
  );
}
