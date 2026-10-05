"use client";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { isPage, type Page } from "@/lib/apiErrors";
import { PAGE_SIZE } from "@/lib/bdm";
import { APPOINTMENTS_URL, type AppointmentRow, STATUS_CLASS, STATUS_LABEL, STATUSES, teamMemberSearch, todayIst, TYPE_LABEL, whenText } from "@/lib/bdmAppointments";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import type { PickOption } from "@/lib/lookups";

// bdm-006 (spec §6.2, §12.2): a BDM's own appointments or a manager's team's. The API scopes the rows; nothing here filters for
// security. Filters and the page live in the URL (BdmOrganizationsPanel's pattern); "From" defaults to today in India time, and an
// empty "From" in the URL (date_from=) means every date. bdm-007 (AC5): "Outcome pending" is offered as a status; the API reads it as
// outcome_pending=true (open and past its start, no meeting report).
const PENDING = "outcome_pending";
type Filters = { offset: number; q: string; dateFrom: string; dateTo: string; status: string; type: string; organization: string; bdm: string };

// A stale or hand-edited URL must not wedge the list on an API 422: every value is checked here, before it reaches the API.
function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const d = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === value;
}

function readFilters(params: URLSearchParams, today: string, types: readonly string[]): Filters {
  const n = Number.parseInt(params.get("offset") ?? "", 10);
  const from = params.get("date_from");
  const dateFrom = from === null ? today : from === "" || validDate(from) ? from : today;
  const to = params.get("date_to") ?? "";
  const status = params.get("status") ?? "";
  const type = params.get("type") ?? "";
  return {
    offset: Number.isFinite(n) && n > 0 ? n : 0,
    q: (params.get("q") ?? "").trim(),
    dateFrom,
    dateTo: validDate(to) && !(dateFrom && dateFrom > to) ? to : "",
    status: (STATUSES as readonly string[]).includes(status) || status === PENDING ? status : "",
    type: types.includes(type) ? type : "",
    organization: params.get("organization") ?? "",
    bdm: params.get("bdm") ?? "",
  };
}

function toUrl(f: Filters, today: string): URLSearchParams {
  const next = new URLSearchParams();
  if (f.offset > 0) next.set("offset", String(f.offset));
  if (f.q) next.set("q", f.q);
  if (f.dateFrom !== today) next.set("date_from", f.dateFrom);
  if (f.dateTo) next.set("date_to", f.dateTo);
  if (f.status) next.set("status", f.status);
  if (f.type) next.set("type", f.type);
  if (f.organization) next.set("organization", f.organization);
  if (f.bdm) next.set("bdm", f.bdm);
  return next;
}

function toApi(f: Filters): string {
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(f.offset) });
  if (f.q) query.set("q", f.q);
  if (f.dateFrom) query.set("date_from", f.dateFrom);
  if (f.dateTo) query.set("date_to", f.dateTo);
  if (f.status === PENDING) query.set("outcome_pending", "true");
  else if (f.status) query.set("status", f.status);
  if (f.type) query.set("appointment_type", f.type);
  if (f.organization) query.set("organization_id", f.organization);
  if (f.bdm) query.set("bdm_user_id", f.bdm);
  return `${APPOINTMENTS_URL}?${query}`;
}

export default function BdmAppointmentsPanel({ basePath, isBdm, types }: { basePath: string; isBdm: boolean; types: string[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [today] = useState(todayIst);
  const filters = readFilters(params, today, types);
  const key = toUrl(filters, today).toString();
  const apiUrl = toApi(filters); // a string, so the fetch effect re-runs only when the request itself changes
  const [data, setData] = useState<Page<AppointmentRow> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [target, setTarget] = useState<string | null>(null);
  const loading = fetching || (target !== null && target !== key);
  const [version, setVersion] = useState(0);
  const [draftQ, setDraftQ] = useState(filters.q);
  // The select remounts when the BDM filter changes (key); the option picked here seeds it so the name stays. A deep link has no label.
  const [picked, setPicked] = useState<PickOption | null>(null);

  useEffect(() => setDraftQ(filters.q), [filters.q]);

  useEffect(() => {
    let live = true;
    setLoadFailed(false);
    setFetching(true);
    setTarget(null);
    fetch(apiUrl)
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (!response.ok || !isPage<AppointmentRow>(body)) throw new Error("not a page");
        if (live) setData(body);
      })
      .catch(() => live && setLoadFailed(true))
      .finally(() => live && setFetching(false));
    return () => {
      live = false;
    };
  }, [apiUrl, version]);

  function go(next: Partial<Filters>) {
    const url = toUrl({ ...filters, offset: 0, ...next }, today);
    setTarget(url.toString());
    router.push(url.size ? `${pathname}?${url}` : pathname, { scroll: false });
  }
  const clear = () => go({ q: "", dateFrom: today, dateTo: "", status: "", type: "", organization: "", bdm: "" });
  const filtered = Boolean(filters.q || filters.dateTo || filters.status || filters.type || filters.organization || filters.bdm || filters.dateFrom !== today);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    go({ q: draftQ.trim() });
  };
  const book = isBdm && (
    <Link className="btn small" href={`${basePath}/new`}>
      Book appointment
    </Link>
  );

  return (
    <div className="action-card wide" aria-busy={loading && !loadFailed}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3>Appointments</h3>
        {book}
      </div>
      <form role="search" aria-label="Filter appointments" onSubmit={submit} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        <div className="field" style={{ flex: "1 1 180px", margin: 0 }}>
          <label htmlFor="appt-filter-q">Code or organization</label>
          <input id="appt-filter-q" type="search" value={draftQ} maxLength={200} onChange={(e) => setDraftQ(e.target.value)} />
        </div>
        <div className="field" style={{ flex: "0 1 160px", margin: 0 }}>
          <label htmlFor="appt-filter-from">From (IST)</label>
          <input id="appt-filter-from" type="date" value={filters.dateFrom} onChange={(e) => go({ dateFrom: e.target.value })} />
        </div>
        <div className="field" style={{ flex: "0 1 160px", margin: 0 }}>
          <label htmlFor="appt-filter-to">To (IST)</label>
          <input id="appt-filter-to" type="date" value={filters.dateTo} min={filters.dateFrom || undefined} onChange={(e) => go({ dateTo: e.target.value })} />
        </div>
        <div className="field" style={{ flex: "0 1 160px", margin: 0 }}>
          <label htmlFor="appt-filter-status">Status</label>
          <select id="appt-filter-status" value={filters.status} onChange={(e) => go({ status: e.target.value, ...(e.target.value === PENDING ? { dateFrom: "" } : {}) })}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABEL[s]}
              </option>
            ))}
            <option value={PENDING}>Outcome pending</option>
          </select>
        </div>
        <div className="field" style={{ flex: "0 1 200px", margin: 0 }}>
          <label htmlFor="appt-filter-type">Type</label>
          <select id="appt-filter-type" value={filters.type} onChange={(e) => go({ type: e.target.value })}>
            <option value="">All types</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {TYPE_LABEL[t]}
              </option>
            ))}
          </select>
        </div>
        {!isBdm && (
          <div style={{ flex: "1 1 220px" }}>
            <SearchableSelect
              key={filters.bdm || "all"}
              label="BDM"
              noun="BDM"
              search={teamMemberSearch()}
              initial={picked && picked.id === filters.bdm ? picked : null}
              onChange={(option) => {
                setPicked(option);
                go({ bdm: option?.id ?? "" });
              }}
            />
          </div>
        )}
        <button type="submit" className="btn secondary small">
          Search
        </button>
        {filtered && (
          <button type="button" className="btn secondary small" onClick={clear}>
            Clear filters
          </button>
        )}
      </form>
      {(filters.organization || filters.bdm) && (
        <p className="muted" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", margin: "8px 0 0" }}>
          {filters.organization && <span className="badge">Showing one organization</span>}
          {filters.bdm && <span className="badge">Showing one BDM</span>}
          <button type="button" className="btn secondary small" onClick={() => go({ organization: "", bdm: "" })}>
            Show all
          </button>
        </p>
      )}
      {loadFailed ? (
        <>
          <p className="form-error" role="alert">
            Unable to load appointments.
          </p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((v) => v + 1)}>
            Retry
          </button>
        </>
      ) : data === null ? (
        <p className="muted" role="status">
          Loading appointments…
        </p>
      ) : data.total === 0 ? (
        filtered ? (
          <div role="status">
            <p className="empty">No appointments match these filters.</p>
            <button type="button" className="btn secondary small" onClick={clear}>
              Clear filters
            </button>
          </div>
        ) : (
          <div role="status">
            <p className="empty">{isBdm ? "No appointments yet." : "Your team has no appointments in this period."}</p>
            {book}
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
              Updating appointments…
            </p>
          )}
          <div className="table-wrap" role="region" aria-label="Appointments" tabIndex={0} style={loading ? { opacity: 0.6 } : undefined}>
            <table style={{ overflowWrap: "anywhere" }}>
              <thead>
                <tr>
                  <th scope="col">Code</th>
                  <th scope="col">Date &amp; time</th>
                  <th scope="col">Organization</th>
                  <th scope="col">Contact</th>
                  <th scope="col">Type</th>
                  <th scope="col">Status</th>
                  {!isBdm && <th scope="col">BDM</th>}
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.id}>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <Link href={`${basePath}/${r.id}`} style={LINK_STYLE}>
                        {r.code}
                      </Link>
                    </td>
                    <td style={{ minWidth: 150 }}>{whenText(r.starts_at, r.duration_minutes)}</td>
                    <td style={{ minWidth: 140 }}>
                      {r.organization.name}
                      {r.organization.archived && (
                        <>
                          {" "}
                          <span className="badge">Archived</span>
                        </>
                      )}
                    </td>
                    <td>{r.contact_name}</td>
                    <td>{TYPE_LABEL[r.appointment_type] ?? r.appointment_type}</td>
                    <td>
                      <span className={STATUS_CLASS[r.status]}>{STATUS_LABEL[r.status]}</span>
                      {r.outcome_pending && (
                        <>
                          {" "}
                          <span className="badge">Outcome pending</span>
                        </>
                      )}
                    </td>
                    {!isBdm && (
                      <td>
                        {r.bdm.full_name}
                        {!r.bdm.active && <span className="muted"> (inactive)</span>}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.total > PAGE_SIZE && (
            <nav aria-label="Appointment pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
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
