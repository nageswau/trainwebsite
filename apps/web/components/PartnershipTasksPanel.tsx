"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import PartnershipTaskForm from "@/components/PartnershipTaskForm";
import PartnershipTaskItem from "@/components/PartnershipTaskItem";
import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import { SESSION_ENDED } from "@/lib/bdmTasks";
import { BAND_LABEL, type Band, BANDS, EMPTY_TEXT, isTaskPage, type PartnershipTask, TASK_CREATORS, TASK_PAGE, type TaskPage, tasksUrl } from "@/lib/partnershipTasks";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// upc-020 (§20): the Follow-ups & Tasks list -- band tabs with counts (the API counts every band over the same filters, so they add up),
// whose items (a manager: their own by default; a head: their team's), and the add form. With `university` it is that university's
// open items, without tabs or filters (the university page). Filters live in the URL; unknown values fall back to the defaults.
type Filters = { band: Band; assignee: string; offset: number };
const ADD_ID = "tasks-add"; // the Add button: where focus returns when the form closes

const ASSIGNEE_CHOICES: Record<string, [string, string][]> = {
  partnership_manager: [["me", "My items"], ["all", "Everyone"]],
  partnership_head: [["me", "My items"], ["team", "My team"], ["all", "Everyone"]],
};
const defaultAssignee = (role: string) => (role === "partnership_manager" ? "me" : role === "partnership_head" ? "team" : "all");

function readFilters(params: URLSearchParams, role: string): Filters {
  const band = params.get("band") ?? "";
  const assignee = params.get("assignee") ?? "";
  const n = Number.parseInt(params.get("offset") ?? "", 10);
  const choices = (ASSIGNEE_CHOICES[role] ?? []).map(([key]) => key);
  return {
    band: (BANDS as readonly string[]).includes(band) ? (band as Band) : "today",
    assignee: choices.includes(assignee) ? assignee : defaultAssignee(role),
    offset: Number.isFinite(n) && n > 0 ? n : 0,
  };
}

function toUrl(f: Filters, role: string): URLSearchParams {
  const next = new URLSearchParams();
  if (f.band !== "today") next.set("band", f.band);
  if (f.assignee !== defaultAssignee(role)) next.set("assignee", f.assignee);
  if (f.offset > 0) next.set("offset", String(f.offset));
  return next;
}

export default function PartnershipTasksPanel({ role, university, canAdd }: { role: string; university?: { id: string; name: string }; canAdd?: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const filters = readFilters(params, role);
  const apiUrl = university
    ? tasksUrl({ band: "open", university: university.id })
    : tasksUrl({ band: filters.band, assignee: filters.assignee === "all" ? undefined : filters.assignee, offset: filters.offset });
  const [data, setData] = useState<TaskPage | null>(null);
  const [failed, setFailed] = useState<false | "error" | "session">(false);
  const [fetching, setFetching] = useState(true);
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const mayAdd = university ? Boolean(canAdd) : TASK_CREATORS.has(role);
  const canAssign = role === "partnership_head";

  useEffect(() => {
    let live = true;
    setFailed(false);
    setFetching(true);
    fetch(apiUrl)
      .then(async (response) => {
        if (response.status === 401) throw new Error("session");
        const body = await response.json().catch(() => null);
        if (!response.ok || !isTaskPage(body)) throw new Error("not a page");
        if (live) setData(body);
      })
      .catch((e: Error) => live && setFailed(e.message === "session" ? "session" : "error"))
      .finally(() => live && setFetching(false));
    return () => { live = false; };
  }, [apiUrl, version]);
  useEffect(() => setNotice(null), [apiUrl]); // a notice belongs to the list it was given on

  function go(next: Partial<Filters>) {
    const url = toUrl({ ...filters, offset: 0, ...next }, role);
    router.push(url.size ? `${pathname}?${url}` : pathname, { scroll: false });
  }
  const reload = () => setVersion((v) => v + 1);
  const changed = (_task: PartnershipTask, text: string) => {
    setNotice(text);
    setAdding(false);
    reload();
    if (university) router.refresh(); // the university's Next / Last Action are server-rendered
  };
  const refused = (message: string) => { setNotice(`${message}. This item changed elsewhere — the list has been reloaded.`); reload(); };
  const addButton = (buttonId?: string) =>
    mayAdd && !adding && <button id={buttonId} type="button" className="btn small" onClick={() => setAdding(true)}>Add follow-up or task</button>;
  const emptyText = university ? "No open follow-ups or tasks." : EMPTY_TEXT[filters.band];
  const choices = ASSIGNEE_CHOICES[role];

  return (
    <div aria-busy={fetching && !failed}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        {!university && (
          <nav aria-label="Follow-up bands" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {BANDS.map((band) => {
              const n = data?.counts[band];
              return (
                <button key={band} type="button" aria-current={filters.band === band ? "page" : undefined}
                  className={`btn small${filters.band === band ? "" : " secondary"}`} onClick={() => go({ band })}>
                  {BAND_LABEL[band]}{n === undefined ? "" : ` (${n})`}
                </button>
              );
            })}
          </nav>
        )}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
          {!university && choices && (
            <div className="field" style={{ margin: 0 }}>
              <label htmlFor="task-filter-assignee">Show</label>
              <select id="task-filter-assignee" value={filters.assignee} onChange={(e) => go({ assignee: e.target.value })}>
                {choices.map(([key, text]) => <option key={key} value={key}>{text}</option>)}
              </select>
            </div>
          )}
          {addButton(ADD_ID)}
        </div>
      </div>
      <div role="status" aria-live="polite">{notice && <p style={{ margin: "8px 0" }}>{notice}</p>}</div>
      {adding && (
        <PartnershipTaskForm university={university} canAssign={canAssign} onSaved={(t) => changed(t, "Added.")}
          onCancel={() => { setAdding(false); focus(ADD_ID); }} />
      )}
      {failed === "session" ? (
        <div role="alert">
          <p className="form-error">{SESSION_ENDED}</p>
          <ReturnToLoginLink loginHref="/overseas/login" />
        </div>
      ) : failed ? (
        <div role="alert">
          <p className="form-error">Unable to load follow-ups.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status">Loading follow-ups…</p>
      ) : data.total === 0 ? (
        <p className="empty" role="status">{emptyText}</p>
      ) : data.items.length === 0 ? (
        <div role="status">
          <p className="empty">This page is past the end of the list.</p>
          <button type="button" className="btn secondary small" onClick={() => go({})}>Go to the first page</button>
        </div>
      ) : (
        <>
          {fetching && <p className="muted" role="status" style={{ margin: 0 }}>Updating…</p>}
          <ul aria-label={university ? "Open follow-ups and tasks" : BAND_LABEL[filters.band]} style={{ padding: 0, margin: "8px 0 0", opacity: fetching ? 0.6 : undefined }}>
            {data.items.map((t) => (
              <PartnershipTaskItem key={t.id} task={t} showUniversity={!university} canAssign={canAssign} onChanged={changed} onRefused={refused} />
            ))}
          </ul>
          {!university && data.total > TASK_PAGE && (
            <nav aria-label="Follow-up pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" disabled={data.offset === 0} onClick={() => go({ offset: Math.max(0, filters.offset - TASK_PAGE) })}>Previous</button>
              <button type="button" className="btn secondary small" disabled={data.offset + data.items.length >= data.total} onClick={() => go({ offset: filters.offset + TASK_PAGE })}>Next</button>
            </nav>
          )}
          {university && data.total > data.items.length && <p className="muted">Showing the first {data.items.length} of {data.total} open items.</p>}
        </>
      )}
    </div>
  );
}
