"use client";
import Link from "next/link";
import { useState } from "react";

import BdmActivityForm from "@/components/BdmActivityForm";
import BdmConfirm from "@/components/BdmConfirm";
import LocalTime from "@/components/LocalTime";
import { sendRequest } from "@/lib/apiErrors";
import { type Activity, activityUrl, CHANNEL_LABEL, contactText, DIRECTION_LABEL } from "@/lib/bdmActivities";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-009 (spec §6.3): one activity in a timeline or a day list. Edit / Delete only when the API says `can_change` (owner, today).
// A 403 / 409 makes the item read-only with the reason; a 404 means it is already gone (there is no single-activity GET).
export default function BdmActivityItem({
  activity, showOrganization = false, orgBasePath = "/bdm/organizations", onChanged, onDeleted,
}: {
  activity: Activity;
  showOrganization?: boolean;
  orgBasePath?: string;
  onChanged: (a: Activity) => void;
  onDeleted: (id: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const editId = `activity-${activity.id}-edit`;
  const deleteId = `activity-${activity.id}-delete`;
  const contact = contactText(activity);
  const heading = `${CHANNEL_LABEL[activity.channel]}${activity.direction ? ` · ${DIRECTION_LABEL[activity.direction]}` : ""}`;

  async function remove() {
    setBusy(true);
    setFailure(null);
    const outcome = await sendRequest(activityUrl(activity.id), { method: "DELETE" });
    setBusy(false);
    setConfirming(false);
    if (outcome.ok || outcome.status === 404) return onDeleted(activity.id);
    setFailure(outcome.message);
    if (outcome.status === 403 || outcome.status === 409) onChanged({ ...activity, permissions: { can_change: false } });
  }

  return (
    <li className="jtl-row">
      <div className="jtl-rail" aria-hidden="true"><span className="jtl-node" /></div>
      <div className="jtl-body">
        <div className="jtl-date"><LocalTime value={activity.occurred_at} time /></div>
        <div className="jtl-title">
          <span className="jtl-badge">{heading}</span>
          {showOrganization && (
            <> <Link href={`${orgBasePath}/${activity.organization.id}`} style={LINK_STYLE}>{activity.organization.name}</Link></>
          )}
        </div>
        <p className="jtl-detail" style={{ margin: 0 }}>
          {contact ? `${contact} · ` : ""}Logged by {activity.bdm.full_name}
        </p>
        {activity.note && <p className="jtl-detail" style={{ margin: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{activity.note}</p>}
        {failure && <p className="form-error" role="alert">{failure}</p>}
        {editing ? (
          <BdmActivityForm organizationId={activity.organization.id} activity={activity}
            onSaved={(a) => { setEditing(false); onChanged(a); focus(editId); }}
            onCancel={() => { setEditing(false); focus(editId); }} />
        ) : (
          activity.permissions.can_change && (
            <div className="actions">
              <button id={editId} type="button" className="btn secondary small" onClick={() => setEditing(true)}>Edit</button>
              <button id={deleteId} type="button" className="btn secondary small" onClick={() => setConfirming(true)} disabled={busy}>Delete</button>
            </div>
          )
        )}
        {confirming && (
          <BdmConfirm label="Confirm delete" confirmText="Yes, delete" busyText="Deleting…" cancelText="Keep it" busy={busy}
            onConfirm={() => void remove()} onCancel={() => { setConfirming(false); focus(deleteId); }}>
            Delete this {CHANNEL_LABEL[activity.channel].toLowerCase()}? It is removed from today&apos;s counts.
          </BdmConfirm>
        )}
      </div>
    </li>
  );
}
