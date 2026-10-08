"use client";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import { isPage, type Page } from "@/lib/apiErrors";
import { display, LINK_STYLE } from "@/lib/bdmOrganizations";
import { formatCalendarDate } from "@/lib/formatDate";
import { personName } from "@/lib/recruiterCompanies";
import {
  DEADLINE_LABEL,
  PRIORITY_LABEL,
  REQUIREMENTS_PATH,
  REQUIREMENTS_URL,
  type RequirementRow,
  STATUS_KEYS,
  type StatusCatalogue,
} from "@/lib/recruiterRequirements";
import { PAGE_SIZE } from "@/lib/telecaller";

// rec-007 (spec §6): the requirement list -- a recruiter's own (assigned, or of their companies), a manager's team, or every one for
// super admin; the API scopes the rows. Filters and the page live in the URL (RecruiterCompaniesPanel's pattern), so refresh keeps the
// place and Back returns to the previous view. Below 980px each row is a card of labelled lines (`.telecaller-list`).
type Filters = { offset: number; q: string; status: string; priority: string; deadline: string; assigned: string };
type Team = { id: string; full_name: string; active: boolean }[];
const DEADLINES = ["expiring", "expired"] as const;

function readFilters(params: URLSearchParams): Filters {
  const n = Number.parseInt(params.get("offset") ?? "", 10);
  const pick = (name: string, allowed: readonly string[]) => (allowed.includes(params.get(name) ?? "") ? params.get(name)! : ""); // a hand-edited URL never 422s
  return {
    offset: Number.isFinite(n) && n > 0 ? n : 0,
    q: (params.get("q") ?? "").trim(),
    status: pick("status", STATUS_KEYS),
    priority: pick("priority", Object.keys(PRIORITY_LABEL)),
    deadline: pick("deadline", DEADLINES),
    assigned: params.get("assigned") ?? "",
  };
}

function toUrl(f: Filters): URLSearchParams {
  const next = new URLSearchParams();
  for (const [key, value] of Object.entries(f)) if (value && !(key === "offset" && value === 0)) next.set(key, String(value));
  return next;
}

function Picker({ id, label, value, all, options, onChange }: { id: string; label: string; value: string; all: string; options: { id: string; name: string }[]; onChange: (v: string) => void }) {
  return (
    <div className="field" style={{ flex: "0 1 180px", margin: 0 }}>
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{all}</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
    </div>
  );
}

export default function RecruiterRequirementsPanel({ canCreate, isManager = false }: { canCreate: boolean; isManager?: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const filters = readFilters(params);
  const key = toUrl(filters).toString();
  const [data, setData] = useState<Page<RequirementRow> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [target, setTarget] = useState<string | null>(null);
  const loading = fetching || (target !== null && target !== key);
  const [version, setVersion] = useState(0);
  const [draftQ, setDraftQ] = useState(filters.q);
  const [statuses, setStatuses] = useState<StatusCatalogue["statuses"]>([]);
  const [team, setTeam] = useState<Team>([]);

  useEffect(() => setDraftQ(filters.q), [filters.q]);

  // The filter pickers: a failed read leaves a picker with only "All" (the list itself still works).
  useEffect(() => {
    const abort = new AbortController();
    fetch(`${REQUIREMENTS_URL}/statuses`, { signal: abort.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((body: StatusCatalogue | null) => body && setStatuses(body.statuses), () => undefined);
    if (isManager) {
      fetch("/api/v1/recruiter/manager/team?limit=100", { signal: abort.signal })
        .then((r) => (r.ok ? r.json() : null))
        .then((body) => body && setTeam(body.items), () => undefined);
    }
    return () => abort.abort();
  }, [isManager]);

  useEffect(() => {
    let live = true;
    setLoadFailed(false);
    setFetching(true);
    setTarget(null);
    const f = readFilters(new URLSearchParams(key));
    const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(f.offset) });
    for (const [name, value] of toUrl({ ...f, offset: 0 })) query.set(name, value);
    fetch(`${REQUIREMENTS_URL}?${query}`)
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (!response.ok || !isPage<RequirementRow>(body)) throw new Error("not a page");
        if (live) setData(body);
      })
      .catch(() => {
        if (live) setLoadFailed(true);
      })
      .finally(() => {
        if (live) setFetching(false);
      });
    return () => {
      live = false;
    };
  }, [key, version]);

  function go(next: Partial<Filters>) {
    const url = toUrl({ ...filters, offset: 0, ...next });
    setTarget(url.toString());
    router.push(url.size ? `${pathname}?${url}` : pathname, { scroll: false });
  }
  const filtered = Boolean(filters.q || filters.status || filters.priority || filters.deadline || filters.assigned);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    go({ q: draftQ.trim() });
  };
  const addLink = canCreate && (
    <Link className="btn small" href={`${REQUIREMENTS_PATH}/new`}>
      Add job requirement
    </Link>
  );

  return (
    <div className="action-card wide telecaller-list" aria-busy={loading && !loadFailed}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3>Job requirements</h3>
        {addLink}
      </div>
      <form role="search" aria-label="Filter job requirements" onSubmit={submit} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        <div className="field" style={{ flex: "1 1 220px", margin: 0 }}>
          <label htmlFor="requirement-filter-q">Title, code or company</label>
          <input id="requirement-filter-q" type="search" value={draftQ} maxLength={200} onChange={(e) => setDraftQ(e.target.value)} />
        </div>
        <Picker id="requirement-filter-status" label="Status" value={filters.status} all="All statuses" options={statuses.map((s) => ({ id: s.key, name: s.label }))} onChange={(v) => go({ status: v })} />
        <Picker id="requirement-filter-priority" label="Priority" value={filters.priority} all="All priorities" options={Object.entries(PRIORITY_LABEL).map(([id, name]) => ({ id, name }))} onChange={(v) => go({ priority: v })} />
        <Picker id="requirement-filter-deadline" label="Deadline" value={filters.deadline} all="Any deadline" options={DEADLINES.map((d) => ({ id: d, name: DEADLINE_LABEL[d] }))} onChange={(v) => go({ deadline: v })} />
        {isManager && (
          <Picker
            id="requirement-filter-assigned"
            label="Recruiter"
            value={filters.assigned}
            all="Anyone"
            options={[{ id: "unassigned", name: "Unassigned" }, ...team.map((r) => ({ id: r.id, name: personName(r) }))]}
            onChange={(v) => go({ assigned: v })}
          />
        )}
        <button type="submit" className="btn secondary small">
          Search
        </button>
        {filtered && (
          <button type="button" className="btn secondary small" onClick={() => go({ q: "", status: "", priority: "", deadline: "", assigned: "" })}>
            Clear filters
          </button>
        )}
      </form>
      {loadFailed ? (
        <>
          <p className="form-error" role="alert">
            Unable to load job requirements.
          </p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((v) => v + 1)}>
            Retry
          </button>
        </>
      ) : data === null ? (
        <p className="muted" role="status">
          Loading job requirements…
        </p>
      ) : data.total === 0 ? (
        filtered ? (
          <p className="empty" role="status">
            No job requirements match these filters.
          </p>
        ) : (
          <div role="status">
            <p className="empty">No job requirements yet.</p>
            {addLink}
          </div>
        )
      ) : data.items.length === 0 ? (
        <>
          <p className="empty" role="status">
            This page is past the end of the list.
          </p>
          <button type="button" className="btn secondary small" onClick={() => go({})}>
            Go to the first page
          </button>
        </>
      ) : (
        <>
          {loading && (
            <p className="muted" role="status" style={{ margin: 0 }}>
              Updating job requirements…
            </p>
          )}
          <div className="table-wrap" role="region" aria-label="Job requirements" tabIndex={0} style={loading ? { opacity: 0.6 } : undefined}>
            <table style={{ width: "100%", overflowWrap: "anywhere" }}>
              <thead>
                {/* QA-01: headers never break mid-word (the table's overflowWrap is for long cell values) */}
                <tr style={{ whiteSpace: "nowrap" }}>
                  <th scope="col">Code</th>
                  <th scope="col">Job title</th>
                  <th scope="col">Company</th>
                  <th scope="col">Status</th>
                  <th scope="col">Priority</th>
                  <th scope="col">Vacancies</th>
                  <th scope="col">Deadline</th>
                  <th scope="col">Recruiter</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.id}>
                    <td data-label="Code" style={{ whiteSpace: "nowrap" }}>{r.code}</td>
                    <td data-label="Job title" style={{ minWidth: 160 }}>
                      <Link href={`${REQUIREMENTS_PATH}/${r.id}`} style={LINK_STYLE}>
                        {r.title}
                      </Link>
                    </td>
                    <td data-label="Company">{r.company.name}</td>
                    <td data-label="Status">
                      <span className="badge" style={{ whiteSpace: "nowrap" }}>
                        {r.status_label}
                      </span>
                    </td>
                    <td data-label="Priority">{r.priority ? PRIORITY_LABEL[r.priority] : "—"}</td>
                    <td data-label="Vacancies">{display(r.vacancies)}</td>
                    <td data-label="Deadline">
                      {r.closes_on ? formatCalendarDate(r.closes_on) : "—"}
                      {r.deadline_state && (
                        <>
                          {" "}
                          <span className={r.deadline_state === "expired" ? "status error" : "status pending"}>{DEADLINE_LABEL[r.deadline_state]}</span>
                        </>
                      )}
                    </td>
                    <td data-label="Recruiter">{personName(r.assigned_recruiter)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.total > PAGE_SIZE && (
            <nav aria-label="Job requirement pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>
                Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}
              </span>
              <button type="button" className="btn secondary small" disabled={data.offset === 0} onClick={() => go({ offset: Math.max(0, filters.offset - PAGE_SIZE) })}>
                Previous
              </button>
              <button type="button" className="btn secondary small" disabled={data.offset + data.items.length >= data.total} onClick={() => go({ offset: filters.offset + PAGE_SIZE })}>
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
