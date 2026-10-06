"use client";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import BdmTaskForm from "@/components/BdmTaskForm";
import BdmTaskItem from "@/components/BdmTaskItem";
import SearchableSelect from "@/components/SearchableSelect";
import { teamMemberSearch } from "@/lib/bdmAppointments";
import { LINK_STYLE, ORG_TYPES } from "@/lib/bdmOrganizations";
import { EMPTY_TEXT, isTaskPage, KIND_LABEL, KINDS, orgTypeText, TAB_LABEL, TABS, type Tab, type Task, TASK_PAGE, type TaskPage, tasksUrl } from "@/lib/bdmTasks";
import type { PickOption } from "@/lib/lookups";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-008 (spec §9): a BDM's follow-ups and tasks, or a manager's team's (read only). The API scopes the rows and computes the counts
// from the same filters, so the chips always add up to the list. Filters live in the URL; every value is checked before it reaches the API.
type Filters = { bucket: Tab; kind: string; orgType: string; bdm: string; offset: number };
const TYPES: readonly string[] = [...ORG_TYPES, "none"];
const ADD_ID = "tasks-add"; // the header Add button: where focus returns when the form closes (QA8-02)

function readFilters(params: URLSearchParams): Filters {
  const bucket = params.get("bucket") ?? "";
  const kind = params.get("kind") ?? "";
  const orgType = params.get("org_type") ?? "";
  const n = Number.parseInt(params.get("offset") ?? "", 10);
  return {
    bucket: (TABS as readonly string[]).includes(bucket) ? (bucket as Tab) : "today",
    kind: (KINDS as readonly string[]).includes(kind) ? kind : "",
    orgType: TYPES.includes(orgType) ? orgType : "",
    bdm: params.get("bdm") ?? "",
    offset: Number.isFinite(n) && n > 0 ? n : 0,
  };
}

function toUrl(f: Filters): URLSearchParams {
  const next = new URLSearchParams();
  if (f.bucket !== "today") next.set("bucket", f.bucket);
  if (f.kind) next.set("kind", f.kind);
  if (f.orgType) next.set("org_type", f.orgType);
  if (f.bdm) next.set("bdm", f.bdm);
  if (f.offset > 0) next.set("offset", String(f.offset));
  return next;
}

export default function BdmTasksPanel({ isBdm }: { isBdm: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const filters = readFilters(useSearchParams());
  const apiUrl = tasksUrl({ bucket: filters.bucket, kind: filters.kind, orgType: filters.orgType, bdm: filters.bdm, offset: filters.offset });
  const [data, setData] = useState<TaskPage | null>(null);
  const [failed, setFailed] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<{ text: string; done?: Task } | null>(null);
  const [picked, setPicked] = useState<PickOption | null>(null);
  const basePath = isBdm ? "/bdm" : "/bdm/manager";
  const focus = useFocusAfterRender();

  useEffect(() => {
    let live = true;
    setFailed(false);
    setFetching(true);
    fetch(apiUrl)
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (!response.ok || !isTaskPage(body)) throw new Error("not a page");
        if (live) setData(body);
      })
      .catch(() => live && setFailed(true))
      .finally(() => live && setFetching(false));
    return () => { live = false; };
  }, [apiUrl, version]);

  function go(next: Partial<Filters>) {
    const url = toUrl({ ...filters, offset: 0, ...next });
    router.push(url.size ? `${pathname}?${url}` : pathname, { scroll: false });
  }
  const reload = () => setVersion((v) => v + 1);
  const changed = (task: Task, text: string) => { setNotice({ text, done: task.status === "done" ? task : undefined }); setAdding(false); reload(); };
  const refused = (message: string) => { setNotice({ text: `${message}. This item changed elsewhere — the list has been reloaded.` }); reload(); };
  const filtered = Boolean(filters.kind || filters.orgType || filters.bdm);
  const addButton = (id?: string) => isBdm && !adding && <button id={id} type="button" className="btn small" onClick={() => setAdding(true)}>Add follow-up or task</button>;
  const doneOrg = notice?.done?.organization && !notice.done.organization.archived ? notice.done.organization : null;

  return (
    <div className="action-card wide" aria-busy={fetching && !failed}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3>Follow-ups and tasks</h3>
        {addButton(ADD_ID)}
      </div>
      <div role="status" aria-live="polite">
        {notice && (
          <p style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "8px 0" }}>
            <span>{notice.text}</span>
            {doneOrg && <Link href={`/bdm/organizations/${doneOrg.id}#org-${doneOrg.id}-activity`} style={LINK_STYLE}>Log activity</Link>}
            {doneOrg && <Link href={`/bdm/appointments/new?organization=${doneOrg.id}`} style={LINK_STYLE}>Book appointment</Link>}
          </p>
        )}
      </div>
      {adding && <BdmTaskForm onSaved={(t) => changed(t, "Added.")} onCancel={() => { setAdding(false); focus(ADD_ID); }} />}
      <nav aria-label="Follow-up lists" style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "8px 0" }}>
        {TABS.map((tab) => {
          const n = data?.counts.buckets[tab];
          return (
            <button key={tab} type="button" aria-current={filters.bucket === tab ? "page" : undefined}
              className={`btn small${filters.bucket === tab ? "" : " secondary"}`} onClick={() => go({ bucket: tab })}>
              {TAB_LABEL[tab]}{n === undefined ? "" : ` (${n})`}
            </button>
          );
        })}
      </nav>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        {data?.counts.by_org_type.map((c) => {
          const value = c.org_type ?? "none";
          const pressed = filters.orgType === value;
          return (
            <button key={value} type="button" aria-pressed={pressed} className={`btn small${pressed ? "" : " secondary"}`} onClick={() => go({ orgType: pressed ? "" : value })}>
              {orgTypeText(c.org_type)} {c.count}
            </button>
          );
        })}
        <div className="field" style={{ flex: "0 1 180px", margin: 0 }}>
          <label htmlFor="task-filter-kind">Kind</label>
          <select id="task-filter-kind" value={filters.kind} onChange={(e) => go({ kind: e.target.value })}>
            <option value="">All</option>
            {KINDS.map((k) => <option key={k} value={k}>{KIND_LABEL[k]}s</option>)}
          </select>
        </div>
        {!isBdm && (
          <div style={{ flex: "1 1 220px" }}>
            <SearchableSelect key={filters.bdm || "all"} label="BDM" noun="BDM" search={teamMemberSearch()}
              initial={picked && picked.id === filters.bdm ? picked : null} onChange={(o) => { setPicked(o); go({ bdm: o?.id ?? "" }); }} />
          </div>
        )}
        {filtered && <button type="button" className="btn secondary small" onClick={() => go({ kind: "", orgType: "", bdm: "" })}>Clear filters</button>}
      </div>
      {failed ? (
        <div role="alert">
          <p className="form-error">Unable to load follow-ups.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status">Loading follow-ups…</p>
      ) : data.total === 0 ? (
        <div role="status">
          <p className="empty">{filtered ? "No items match these filters." : EMPTY_TEXT[filters.bucket]}</p>
          {filtered ? <button type="button" className="btn secondary small" onClick={() => go({ kind: "", orgType: "", bdm: "" })}>Clear filters</button> : addButton()}
        </div>
      ) : data.items.length === 0 ? (
        <div role="status">
          <p className="empty">This page is past the end of the list.</p>
          <button type="button" className="btn secondary small" onClick={() => go({})}>Go to the first page</button>
        </div>
      ) : (
        <>
          {fetching && <p className="muted" role="status" style={{ margin: 0 }}>Updating…</p>}
          <ul aria-label={TAB_LABEL[filters.bucket]} style={{ padding: 0, margin: 0, opacity: fetching ? 0.6 : undefined }}>
            {data.items.map((t) => (
              <BdmTaskItem key={t.id} task={t} today={data.today} basePath={basePath} showAssignee={!isBdm} onChanged={changed} onRefused={refused} />
            ))}
          </ul>
          {data.total > TASK_PAGE && (
            <nav aria-label="Follow-up pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" disabled={data.offset === 0} onClick={() => go({ offset: Math.max(0, filters.offset - TASK_PAGE) })}>Previous</button>
              <button type="button" className="btn secondary small" disabled={data.offset + data.items.length >= data.total} onClick={() => go({ offset: filters.offset + TASK_PAGE })}>Next</button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
