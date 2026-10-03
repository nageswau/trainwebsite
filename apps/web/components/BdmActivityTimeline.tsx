"use client";
import { useState } from "react";

import BdmActivityForm from "@/components/BdmActivityForm";
import BdmActivityItem from "@/components/BdmActivityItem";
import { isPage, type Page } from "@/lib/apiErrors";
import { type Activity, orgActivitiesUrl, placeNewest } from "@/lib/bdmActivities";
import type { Organization } from "@/lib/bdmOrganizations";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-009 (spec §6.2, §6.3; V5): every BDM's activities on this organization, newest first, for anyone who can read it. Writes apply the
// returned activity locally (no router.refresh -- bdm-010 QA10-16). `null` = the server page could not load the first page.
export default function BdmActivityTimeline({
  organization, initial, canLog, orgBasePath,
}: { organization: Organization; initial: Page<Activity> | null; canLog: boolean; orgBasePath: string }) {
  const [items, setItems] = useState(initial?.items ?? []);
  const [total, setTotal] = useState(initial?.total ?? 0);
  const [loaded, setLoaded] = useState(initial !== null); // false: the server page couldn't read the first page (§12.2 F6)
  const [logging, setLogging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const logId = `org-${organization.id}-log-activity`;
  const statusId = `org-${organization.id}-activity-status`;

  async function load(offset: number) {
    setLoading(true);
    setFailure(null);
    try {
      const response = await fetch(orgActivitiesUrl(organization.id, offset));
      const data = response.ok ? await response.json() : null;
      if (!isPage<Activity>(data)) throw new Error("bad page");
      setItems((current) => (offset === 0 ? data.items : [...current, ...data.items.filter((a) => !current.some((c) => c.id === a.id))]));
      setTotal(data.total);
      setLoaded(true);
    } catch {
      setFailure(offset === 0 ? "Activity couldn't be loaded." : "More activity couldn't be loaded. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="action-card wide" aria-labelledby={`org-${organization.id}-activity`}>
      <div className="portal-title" style={{ gap: 12, flexWrap: "wrap" }}>
        <h3 id={`org-${organization.id}-activity`}>Activity</h3>
        {canLog && !logging && (
          <button id={logId} type="button" className="btn small" onClick={() => setLogging(true)}>Log activity</button>
        )}
      </div>
      <div id={statusId} tabIndex={-1} role="status" aria-live="polite" className={notice ? "form-message" : undefined}>{notice}</div>
      {logging && (
        <BdmActivityForm organizationId={organization.id} contacts={organization.contacts.map((c) => ({ id: c.id, name: c.name }))}
          onSaved={(a) => { setItems((current) => placeNewest(current, a)); setTotal((t) => t + 1); setLogging(false); setNotice("Activity logged."); focus(statusId); }}
          onCancel={() => { setLogging(false); focus(logId); }} />
      )}
      {!loaded ? (
        <div role="alert">
          <p className="form-error">Activity couldn&apos;t be loaded.</p>
          <button type="button" className="btn secondary small" onClick={() => void load(0)} disabled={loading}>{loading ? "Loading…" : "Try again"}</button>
        </div>
      ) : items.length === 0 ? (
        <p className="muted">No activity logged yet.</p>
      ) : (
        <ol className="jtl" aria-label="Activity" style={{ listStyle: "none", padding: 0 }}>
          {items.map((a) => (
            <BdmActivityItem key={a.id} activity={a} orgBasePath={orgBasePath}
              onChanged={(next) => { setItems((current) => placeNewest(current, next)); setNotice("Activity saved."); }}
              onDeleted={(id) => { setItems((current) => current.filter((x) => x.id !== id)); setTotal((t) => t - 1); setNotice("Activity deleted."); focus(statusId); }} />
          ))}
        </ol>
      )}
      {loaded && failure && <p className="form-error" role="alert">{failure}</p>}
      {loaded && items.length < total && (
        <button type="button" className="btn secondary small" onClick={() => void load(items.length)} disabled={loading}>{loading ? "Loading…" : "Load more"}</button>
      )}
    </section>
  );
}
