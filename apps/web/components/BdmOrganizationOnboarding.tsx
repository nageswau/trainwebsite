"use client";
import { type FormEvent, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { AGENCY_STATUS, onboardingMessage, requestUrl } from "@/lib/bdmOnboarding";
import { isOrganizationBody, type Organization } from "@/lib/bdmOrganizations";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-018 (spec §6): the School organization's handover to Overseas Admin -- linked, pending, rejected or not yet requested. The
// server decides who may request (`can_request`: the assigned BDM or super_admin, MoU Signed/Active, nothing pending or linked); a
// request re-renders the page from the organization the API returns, so the pipeline's live steps follow.
export default function BdmOrganizationOnboarding({ organization, onRequested }: { organization: Organization; onRequested: (next: Organization) => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const onboarding = organization.onboarding;
  if (!onboarding) return null;
  const { request, school, can_request } = onboarding;
  const ids = { open: `onboarding-${organization.id}-open`, note: `onboarding-${organization.id}-note` };

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const note = String(new FormData(event.currentTarget).get("note") ?? "").trim();
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(requestUrl(organization.id), "POST", note ? { note } : {});
    setBusy(false);
    if (outcome.ok && isOrganizationBody(outcome.data)) {
      setOpen(false);
      onRequested(outcome.data.organization);
    } else setFailure(outcome.ok ? "Unable to send the request." : onboardingMessage(outcome));
  }

  const cancel = () => {
    setOpen(false);
    setFailure(null);
    focus(ids.open);
  };

  // bdm-019 (DEC-SCOPE-106): an Agent organization is linked to an existing Agent Organization; the BDM sees its summary only.
  const isAgent = organization.bdm_type === "agent";
  const agent = onboarding.agent ?? null;
  const linked = Boolean(school || agent);
  const title = isAgent ? "Agent onboarding" : "School onboarding";
  let status: string;
  if (school) status = `Onboarded as ${school.name}${school.school_code ? ` (School ID ${school.school_code})` : ""}.`;
  else if (agent) status = `Linked to ${agent.name} (code ${agent.prefix}). Status: ${AGENCY_STATUS[agent.status] ?? agent.status}.`;
  else if (request?.status === "pending") status = `Requested on ${formatSchoolDateTime(request.created_at, true)}. ${isAgent ? "Waiting for Overseas Admin to link the agent organization." : "Waiting for Overseas Admin to create or link the School."}`;
  else if (request?.status === "rejected") status = `Not approved on ${formatSchoolDateTime(request.resolved_at, true)}. Reason: ${request.reject_reason}`;
  else if (can_request) status = isAgent ? "Ready to hand over: Overseas Admin will link the agent organization once the agency is registered." : "Ready to hand over: Overseas Admin will create the School, or link one that already exists.";
  else if (!organization.permissions.can_edit) status = "Not requested yet.";
  else status = isAgent ? "Available once the agreement is signed." : "Available once the MoU is Signed or Active.";

  return (
    <section className="action-card wide" aria-label={title}>
      <h3>{title}</h3>
      <p className={request?.status === "rejected" && !linked ? "form-message" : undefined}>{status}</p>
      {agent && <p className="muted">Master login: {agent.master_login ? "Created" : "Not yet"} · Staff logins: {agent.staff_count}</p>}
      {can_request && !open && (
        <button id={ids.open} type="button" className="btn small" onClick={() => setOpen(true)}>
          {request?.status === "rejected" ? "Request again" : "Request onboarding"}
        </button>
      )}
      {open && (
        <form className="form" aria-label="Request onboarding" onSubmit={submit} aria-busy={busy}>
          <div className="field">
            <label htmlFor={ids.note}>Note for Overseas Admin (optional)</label>
            <textarea id={ids.note} name="note" maxLength={1000} rows={3} disabled={busy} autoFocus />
          </div>
          {failure && <p className="form-error" role="alert">{failure}</p>}
          <div className="actions">
            <button type="submit" className="btn small" disabled={busy}>{busy ? "Sending…" : "Send request"}</button>
            <button type="button" className="btn secondary small" onClick={cancel} disabled={busy}>Cancel</button>
          </div>
        </form>
      )}
    </section>
  );
}
