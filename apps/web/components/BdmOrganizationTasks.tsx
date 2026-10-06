"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import BdmTaskForm from "@/components/BdmTaskForm";
import BdmTaskItem from "@/components/BdmTaskItem";
import { isTaskPage, orgTasksUrl, type TaskPage } from "@/lib/bdmTasks";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-008 (spec §9): the organization's open follow-ups and tasks (the caller's own for a BDM, the team's for a manager). Every write
// reloads the first page; `version` changes when the organization is archived on this page (the archive cancelled them). Notices go
// to the profile's one live region.
export default function BdmOrganizationTasks({ organization, initial, canAdd, basePath, version, onNotice }: {
  organization: { id: string; name: string }; initial: TaskPage | null; canAdd: boolean; basePath: "/bdm" | "/bdm/manager"; version: number;
  onNotice: (text: string, focusStatus?: boolean) => void;
}) {
  const [data, setData] = useState<TaskPage | null>(initial);
  const [failed, setFailed] = useState(initial === null);
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(false);
  const latest = useRef(0);
  const focus = useFocusAfterRender();
  const addId = `org-${organization.id}-add-task`;

  const load = useCallback(async () => {
    const ticket = ++latest.current;
    setLoading(true);
    const response = await fetch(orgTasksUrl(organization.id)).catch(() => null);
    const body: unknown = response?.ok ? await response.json().catch(() => null) : null;
    if (ticket !== latest.current) return;
    setLoading(false);
    if (!isTaskPage(body)) return setFailed(true);
    setFailed(false);
    setData(body);
  }, [organization.id]);

  useEffect(() => {
    if (version > 0) void load();
  }, [version, load]);

  const changed = (text: string) => { onNotice(text, true); setAdding(false); void load(); };
  return (
    <section className="action-card wide" aria-labelledby={`org-${organization.id}-tasks`}>
      <div className="portal-title" style={{ gap: 12, flexWrap: "wrap" }}>
        <h3 id={`org-${organization.id}-tasks`}>Follow-ups &amp; tasks</h3>
        {canAdd && !adding && <button id={addId} type="button" className="btn small" onClick={() => { setAdding(true); onNotice(""); }}>Add task</button>}
      </div>
      {adding && <BdmTaskForm organization={organization} onSaved={() => changed("Added.")} onCancel={() => { setAdding(false); focus(addId); }} />}
      {failed ? (
        <div role="alert">
          <p className="form-error">Follow-ups couldn&apos;t be loaded.</p>
          <button type="button" className="btn secondary small" onClick={() => void load()} disabled={loading}>{loading ? "Loading…" : "Try again"}</button>
        </div>
      ) : !data || data.total === 0 ? (
        <p className="muted">No open follow-ups or tasks.</p>
      ) : (
        <>
          <ul aria-label="Open follow-ups and tasks" style={{ padding: 0, margin: 0 }}>
            {data.items.map((t) => (
              <BdmTaskItem key={t.id} task={t} today={data.today} basePath={basePath} showAssignee={basePath === "/bdm/manager"}
                onChanged={(_, text) => changed(text)} onRefused={(message) => changed(`${message}. The list has been reloaded.`)} />
            ))}
          </ul>
          {data.total > data.items.length && (
            <p className="muted">Showing {data.items.length} of {data.total}. <Link href={`${basePath}/follow-ups?bucket=today`} style={LINK_STYLE}>See all follow-ups</Link></p>
          )}
        </>
      )}
    </section>
  );
}
