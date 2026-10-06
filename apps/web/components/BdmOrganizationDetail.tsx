"use client";
import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";

import BdmActivityTimeline from "@/components/BdmActivityTimeline";
import BdmConfirm from "@/components/BdmConfirm";
import BdmOrganizationContacts from "@/components/BdmOrganizationContacts";
import BdmOrganizationForm from "@/components/BdmOrganizationForm";
import BdmOrganizationLeads from "@/components/BdmOrganizationLeads";
import BdmOrganizationMou from "@/components/BdmOrganizationMou";
import BdmOrganizationOnboarding from "@/components/BdmOrganizationOnboarding";
import BdmOrganizationPipeline from "@/components/BdmOrganizationPipeline";
import BdmOrganizationProfileDetails, { DetailList, multiline } from "@/components/BdmOrganizationProfileDetails";
import BdmOrganizationReassign from "@/components/BdmOrganizationReassign";
import BdmOrganizationSchoolActivity from "@/components/BdmOrganizationSchoolActivity";
import BdmOrganizationTasks from "@/components/BdmOrganizationTasks";
import BdmStageHistory from "@/components/BdmStageHistory";
import { type Page, sendRequest } from "@/lib/apiErrors";
import type { Activity } from "@/lib/bdmActivities";
import type { Lead } from "@/lib/bdmLeads";
import type { OrgMou } from "@/lib/bdmMous";
import type { StageEvent } from "@/lib/bdmPipeline";
import type { SchoolActivity } from "@/lib/bdmSchoolActivity";
import type { TaskPage } from "@/lib/bdmTasks";
import { display, isOrganizationBody, LINK_STYLE, meetingText, type Organization, ORG_TYPE_LABEL, ORGS_URL, safeWebsite } from "@/lib/bdmOrganizations";
import { formatDate } from "@/lib/formatDate";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-005 QA5-06: an archived or Lost organization refuses every MoU write (409); the card says so instead of just showing no buttons.
function mouReadOnlyNote(org: Organization): string | undefined {
  if (org.archived) return "This organization is archived, so its MoU is read-only.";
  return org.pipeline.lost ? "This organization is marked lost, so its MoU is read-only." : undefined;
}

// bdm-002 (spec §6.2, §12.2): one organization. Actions render from `permissions` only -- the server enforces every rule (AC3-AC5).
// Every write re-renders from the organization the API returns (no refetch). Last/Next meeting come from bdm-006 appointments ("—" when none).
export default function BdmOrganizationDetail({ initial, basePath, created = false, activities, leads, stageHistory, tasks, mou, schoolActivity }: {
  initial: Organization; basePath: string; created?: boolean; activities?: Page<Activity> | null; leads?: Page<Lead> | null;
  stageHistory?: Page<StageEvent> | null; tasks?: TaskPage | null; mou?: OrgMou | null; schoolActivity?: SchoolActivity | null;
}) {
  const [org, setOrg] = useState(initial);
  const [historyVersion, setHistoryVersion] = useState(0); // bdm-004: bumped by each pipeline write, which reloads the stage history
  const [tasksVersion, setTasksVersion] = useState(0); // bdm-008: bumped by an archive here, which cancelled the open follow-ups
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(created ? `Organization ${initial.code} created.` : null);
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  // Browser QA-08: "created" is said once -- the flag leaves the address, so a refresh or a shared link doesn't repeat it. History
  // only: a router navigation would re-run the server page for nothing (simplify review A8).
  useEffect(() => {
    if (created) window.history.replaceState(null, "", `${basePath}/${initial.id}`);
  }, [created, basePath, initial.id]);
  const archiveId = `org-${org.id}-archive`;
  const editId = `org-${org.id}-edit`;
  const statusId = `org-${org.id}-status`;
  const closeEditor = () => {
    setEditing(false);
    focus(editId); // browser QA-12: the form (and the focused control) is gone
  };
  const p = org.permissions;
  const showEditor = editing && p.can_edit; // a write that removes edit rights also closes the form (simplify review A9)

  // The sections' notices (activity, leads) go to the profile's one live region (QA9-01); `focusStatus` when the used control is gone.
  const notify = (text: string, focusStatus?: boolean) => {
    setNotice(text);
    setFailure(null);
    if (focusStatus) focus(statusId);
  };
  const changed = (next: Organization, text: string) => {
    setOrg(next);
    setNotice(text);
    setFailure(null);
  };
  // bdm-005 (D28): a Signed MoU moved the pipeline server-side; re-read the organization so the pipeline and its history show it.
  // bdm-018: any MoU status change re-reads it too, since Signed / Active decide whether onboarding can be requested.
  async function reloadOrganization() {
    const fresh = await sendRequest(`${ORGS_URL}/${org.id}`, { method: "GET" });
    if (fresh.ok && isOrganizationBody(fresh.data)) {
      setOrg(fresh.data.organization);
      setHistoryVersion((v) => v + 1);
    }
  }
  async function act(path: "archive" | "restore") {
    setBusy(true);
    setFailure(null);
    const outcome = await sendRequest(`${ORGS_URL}/${org.id}/${path}`, { method: "POST" });
    setBusy(false);
    setConfirming(false);
    if (outcome.ok && isOrganizationBody(outcome.data)) {
      changed(outcome.data.organization, path === "archive" ? "Organization archived." : "Organization restored.");
      if (path === "archive") setTasksVersion((v) => v + 1);
      focus(statusId); // the button that was used is gone (simplify review A5)
    } else setFailure(outcome.ok ? "Unable to update this organization." : outcome.message);
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
    ["Address", multiline(org.address)],
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
    ["Courses interested", multiline(org.courses_interested)],
    ["Number of students", display(org.student_count)],
    ["Last meeting", meetingText(org.last_meeting_at)],
    ["Next meeting", meetingText(org.next_meeting_at)],
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
            <Link href={basePath} style={LINK_STYLE}>
              Back to organizations
            </Link>
          </p>
        </div>
        <div className="actions">
          {basePath === "/bdm/organizations" && p.can_edit && !showEditor && ( // bdm-006: the assigned BDM, not archived (A3, A4)
            <Link className="btn small" href={`/bdm/appointments/new?organization=${org.id}`}>
              Add appointment
            </Link>
          )}
          {p.can_edit && !showEditor && (
            <button id={editId} type="button" className="btn secondary small" onClick={() => setEditing(true)}>
              Edit
            </button>
          )}
          {p.can_archive && !showEditor && ( // browser QA-14: archiving under an open edit form left it stale
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
      <div id={statusId} tabIndex={-1} role="status" aria-live="polite" className={notice ? "form-message" : undefined}>
        {notice}
      </div>
      {failure && (
        <p className="form-error" role="alert">
          {failure}
        </p>
      )}
      {confirming && (
        <BdmConfirm label="Confirm archive" className="action-card" confirmText="Yes, archive" busyText="Archiving…" cancelText="Keep it" busy={busy} onConfirm={() => void act("archive")} onCancel={cancel}>
          Archive {org.name}? It will be hidden from the list and read-only until a manager restores it.
        </BdmConfirm>
      )}
      <BdmOrganizationPipeline
        organization={org}
        onChanged={(o, text) => {
          changed(o, text);
          setHistoryVersion((v) => v + 1);
          focus(statusId); // the form that was used is reset or gone
        }}
        onRefreshed={(o) => {
          // QA4-07: someone else changed it; the pipeline section says why, so no success notice here
          setOrg(o);
          setNotice(null);
          setHistoryVersion((v) => v + 1);
        }}
      />
      {mou !== undefined && (
        <BdmOrganizationMou orgId={org.id} initial={mou} onNotice={notify} onPipelineChanged={() => void reloadOrganization()} readOnlyNote={mouReadOnlyNote(org)} />
      )}
      <BdmOrganizationOnboarding
        organization={org}
        onRequested={(o) => {
          changed(o, "Onboarding requested. Overseas Admin will create or link the School.");
          focus(statusId); // the form that was used is gone
        }}
      />
      {schoolActivity !== undefined && org.bdm_type === "school" && <BdmOrganizationSchoolActivity orgId={org.id} initial={schoolActivity} />}
      {showEditor ? (
        <section className="action-card wide" aria-label="Edit details">
          <h3>Edit details</h3>
          <BdmOrganizationForm
            mode="edit"
            organization={org}
            onSaved={(o, saved) => {
              changed(o, saved ? "Changes saved." : "No changes to save."); // browser QA-13
              closeEditor();
            }}
            onCancel={closeEditor}
          />
        </section>
      ) : (
        <section className="action-card wide" aria-label="Details">
          <h3>Details</h3>
          <DetailList rows={rows} />
          <BdmOrganizationProfileDetails organization={org} />
        </section>
      )}
      <BdmOrganizationContacts organization={org} onChanged={changed} />
      {/* QA4-05: the stage history sits with the activity timeline, after Details and Contacts */}
      {stageHistory !== undefined && <BdmStageHistory orgId={org.id} initial={stageHistory} version={historyVersion} />}
      {activities !== undefined && ( // bdm-009: the BDM view logs (assigned and not archived = can_edit); the manager view reads
        <BdmActivityTimeline organization={org} initial={activities} canLog={basePath === "/bdm/organizations" && p.can_edit} orgBasePath={basePath}
          onNotice={notify} />
      )}
      {tasks !== undefined && ( // bdm-008: the BDM view adds (assigned and not archived = can_edit); the manager view reads
        <BdmOrganizationTasks organization={{ id: org.id, name: org.name }} initial={tasks} canAdd={basePath === "/bdm/organizations" && p.can_edit}
          basePath={basePath === "/bdm/organizations" ? "/bdm" : "/bdm/manager"} version={tasksVersion} onNotice={notify} />
      )}
      {leads !== undefined && ( // bdm-017 (L6): the BDM view adds (assigned and not archived = can_edit); the manager view reads
        <BdmOrganizationLeads organizationId={org.id} initial={leads} canAdd={basePath === "/bdm/organizations" && p.can_edit} onNotice={notify} />
      )}
      {p.can_reassign && (
        <BdmOrganizationReassign
          organization={org}
          onChanged={(o, text) => {
            changed(o, text);
            focus(statusId); // the confirm group is gone (simplify review A5)
          }}
        />
      )}
    </>
  );
}
