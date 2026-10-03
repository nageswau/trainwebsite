"use client";
import Link from "next/link";
import { type KeyboardEvent, type ReactNode, useState } from "react";

import BdmOrganizationContacts from "@/components/BdmOrganizationContacts";
import BdmOrganizationForm from "@/components/BdmOrganizationForm";
import BdmOrganizationReassign from "@/components/BdmOrganizationReassign";
import { sendRequest } from "@/lib/apiErrors";
import { display, isOrganizationBody, type Organization, ORG_TYPE_LABEL, ORGS_URL, safeWebsite } from "@/lib/bdmOrganizations";
import { formatDate } from "@/lib/formatDate";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-002 (spec §6.2, §12.2): one organization. Actions render from `permissions` only -- the server enforces every rule (AC3-AC5).
// Every write re-renders from the organization the API returns (no refetch). Last/Next meeting stay "—" until bdm-006 (AC6).
export default function BdmOrganizationDetail({ initial, basePath, created = false }: { initial: Organization; basePath: string; created?: boolean }) {
  const [org, setOrg] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(created ? `Organization ${initial.code} created.` : null);
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const archiveId = `org-${org.id}-archive`;
  const editId = `org-${org.id}-edit`;
  const closeEditor = () => {
    setEditing(false);
    focus(editId); // browser QA-12: the form (and the focused control) is gone
  };
  const p = org.permissions;

  const changed = (next: Organization, text: string) => {
    setOrg(next);
    setNotice(text);
    setFailure(null);
  };
  async function act(path: "archive" | "restore") {
    setBusy(true);
    setFailure(null);
    const outcome = await sendRequest(`${ORGS_URL}/${org.id}/${path}`, { method: "POST" });
    setBusy(false);
    setConfirming(false);
    if (outcome.ok && isOrganizationBody(outcome.data)) changed(outcome.data.organization, path === "archive" ? "Organization archived." : "Organization restored.");
    else setFailure(outcome.ok ? "Unable to update this organization." : outcome.message);
  }
  const cancel = () => {
    setConfirming(false);
    focus(archiveId);
  };

  const site = safeWebsite(org.website);
  const rows: [string, ReactNode][] = [
    ["Type", ORG_TYPE_LABEL[org.org_type]],
    ["City", org.city],
    ["State", display(org.state)],
    ["Contact person", display(org.primary_contact?.name)],
    ["Designation", display(org.primary_contact?.designation)],
    ["Phone", display(org.phone)],
    ["Email", display(org.email)],
    [
      "Website",
      site ? (
        <a href={site} target="_blank" rel="noopener noreferrer">
          {site}
          <span className="visually-hidden"> (opens in a new tab)</span>
        </a>
      ) : (
        display(org.website)
      ),
    ],
    ["Existing partner", org.existing_partner ? "Yes" : "No"],
    ["Courses interested", display(org.courses_interested)],
    ["Number of students", display(org.student_count)],
    ["Last meeting", display(org.last_meeting_at)],
    ["Next meeting", display(org.next_meeting_at)],
    ["Assigned BDM", `${org.assigned_bdm.full_name}${org.assigned_bdm.active ? "" : " (inactive)"}`],
    ["Created by", `${org.created_by_name} on ${formatDate(org.created_at)}`],
  ];

  return (
    <>
      <div className="portal-title" style={{ flexWrap: "wrap", gap: 12 }}>
        <div>
          <div className="eyebrow">
            {org.code} · {ORG_TYPE_LABEL[org.org_type]}
          </div>
          <h2>
            {org.name} {org.archived && <span className="badge">Archived</span>}
          </h2>
          <p style={{ margin: 0 }}>
            <Link href={basePath}>Back to organizations</Link>
          </p>
        </div>
        <div className="actions">
          {p.can_edit && !editing && (
            <button id={editId} type="button" className="btn secondary small" onClick={() => setEditing(true)}>
              Edit
            </button>
          )}
          {p.can_archive && !editing && ( // browser QA-14: archiving under an open edit form left it stale
            <button id={archiveId} type="button" className="btn secondary small" onClick={() => setConfirming(true)} disabled={busy}>
              Archive
            </button>
          )}
          {p.can_restore && (
            <button type="button" className="btn small" onClick={() => void act("restore")} disabled={busy}>
              {busy ? "Restoring…" : "Restore"}
            </button>
          )}
        </div>
      </div>
      <div role="status" aria-live="polite" className={notice ? "form-message" : undefined}>
        {notice}
      </div>
      {failure && (
        <p className="form-error" role="alert">
          {failure}
        </p>
      )}
      {confirming && (
        <div role="group" aria-label="Confirm archive" className="action-card" onKeyDown={(e: KeyboardEvent) => e.key === "Escape" && cancel()}>
          <p style={{ margin: 0 }}>Archive {org.name}? It will be hidden from the list and read-only until a manager restores it.</p>
          <div className="actions">
            <button type="button" className="btn small" autoFocus onClick={() => void act("archive")} disabled={busy}>
              {busy ? "Archiving…" : "Yes, archive"}
            </button>
            <button type="button" className="btn secondary small" onClick={cancel}>
              Keep it
            </button>
          </div>
        </div>
      )}
      {editing ? (
        <section className="action-card wide" aria-label="Edit details">
          <h3>Edit details</h3>
          <BdmOrganizationForm
            mode="edit"
            organization={org}
            onSaved={(o) => {
              changed(o, "Changes saved.");
              closeEditor();
            }}
            onCancel={closeEditor}
          />
        </section>
      ) : (
        <section className="action-card wide" aria-label="Details">
          <h3>Details</h3>
          <dl style={{ display: "grid", gridTemplateColumns: "minmax(120px, max-content) 1fr", gap: "8px 16px", margin: 0 }}>
            {rows.map(([label, value]) => [
              <dt key={`${label}-t`} className="muted">
                {label}
              </dt>,
              <dd key={`${label}-d`} style={{ margin: 0, overflowWrap: "anywhere" }}>
                {value}
              </dd>,
            ])}
          </dl>
        </section>
      )}
      <BdmOrganizationContacts organization={org} onChanged={changed} />
      {p.can_reassign && <BdmOrganizationReassign organization={org} onChanged={changed} />}
    </>
  );
}
