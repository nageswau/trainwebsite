import Link from "next/link";
import type { InputHTMLAttributes } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { COMMISSION_ROLES, CURRENCIES, LEVELS, MONTHS } from "@/lib/courseMaster";
import { pageOffset } from "@/lib/telecaller";
import type { User } from "@/lib/types";
import { dateText } from "@/lib/universityAgreements";
import { ACTIVITY, EXCLUSIVITY } from "@/lib/partnershipMap";
import { INSTITUTION_TYPES, label, OWNERSHIP_TYPES, PRIORITIES, RANKING_SYSTEMS, REGIONS, shellFor, universityPath } from "@/lib/universities";
import {
  filterProblem, isFiltered, PARTNER_STATUSES, type SearchFilters, searchHref, type SearchPage, searchQuery, SEARCH_PATH, SEARCH_URL,
  statusCounts,
} from "@/lib/universitySearch";

// upc-024 (DEC-SCOPE-163): §32's "🌍 Global University Database" -- every active university in the master, by the §25 search fields and
// filters. A plain GET form: the URL holds the search, so Back, Refresh and a shared link keep it, and it works without client JS. The
// commission filter is offered to the commission roles only; the API ignores it for everyone else (U2, SR10).
const PAGE_SIZE = 50;
const INVALID = "These filters are not valid. Change or clear them and search again.";

type Option = [string, string];
function Choice({ id, name, text, value, options, any = "Any" }: { id: string; name: string; text: string; value?: string; options: Option[]; any?: string }) {
  return (
    <div className="field">
      <label htmlFor={id}>{text}</label>
      <select id={id} name={name} defaultValue={value ?? ""}>
        {any && <option value="">{any}</option>}
        {options.map(([key, word]) => <option key={key} value={key}>{word}</option>)}
      </select>
    </div>
  );
}

function Input({ id, name, text, value, ...rest }: { id: string; name: string; text: string; value?: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className="field">
      <label htmlFor={id}>{text}</label>
      <input id={id} name={name} defaultValue={value ?? ""} {...rest} />
    </div>
  );
}

const pairs = (values: readonly string[]): Option[] => values.map((v) => [v, v]);

export default async function SearchUniversitiesPage({ searchParams }: { searchParams: Promise<SearchFilters> }) {
  const filters = await searchParams;
  const offset = pageOffset(filters.offset);
  let problem = filterProblem(filters);
  let user: User, page: SearchPage | null = null;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  if (!problem) {
    try {
      page = await serverApi<SearchPage>(`${SEARCH_URL}?${searchQuery(filters, PAGE_SIZE, offset)}`);
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 422)) return accessUnavailable(e, "/overseas/login");
      problem = INVALID;
    }
  }
  const { nav, roleLabel } = shellFor(user.role);
  const managerOptions: Option[] = [...(user.role === "partnership_manager" ? [["me", "Assigned to me"] as Option] : []), ["none", "Unassigned"]];
  const withCourses = page?.items.some((u) => u.matching_courses !== null) ?? false; // the API sends counts only for a course filter
  const end = page ? page.offset + page.items.length : 0;
  const first = page?.items[0];
  const fromMap = [
    filters.iso2 && { key: "iso2" as const, text: `Country: ${first?.country.iso2 === filters.iso2.toUpperCase() ? first.country.name : filters.iso2.toUpperCase()}` },
    filters.stage && { key: "stage" as const, text: `Stage: ${page?.items.find((u) => u.stage === filters.stage)?.stage_label ?? filters.stage}` },
  ].filter((x) => !!x);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">🌍 Global University Database</div>
            <h2>Global University Database</h2>
            <p className="muted">Every active university in the University Master, whoever manages it. Combine filters, e.g. Japan + Cyber Security + Not partnered.</p>
          </div>
        </div>
        {/* keyed on the search: a chip, Clear or paging is a client navigation that would otherwise keep the old uncontrolled values (QA24-01) */}
        <form key={searchHref(filters)} className="action-card wide" method="get" action={SEARCH_PATH} role="search" aria-label="Search universities">
          <div className="form-grid" style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
            <Input id="us-q" name="q" text="University" type="search" maxLength={200} value={filters.q} placeholder="Name, code, city or country" />
            <Input id="us-country" name="country" text="Country" maxLength={100} value={filters.country} placeholder="e.g. Japan or JP" />
            <Choice id="us-region" name="region" text="Region" value={filters.region} options={pairs(REGIONS)} />
            <Input id="us-city" name="city" text="City" maxLength={120} value={filters.city} />
            <Choice id="us-type" name="institution_type" text="University type" value={filters.institution_type} options={Object.entries(INSTITUTION_TYPES)} />
            <Choice id="us-ownership" name="ownership_type" text="Public / private" value={filters.ownership_type} options={Object.entries(OWNERSHIP_TYPES)} />
            <Input id="us-ranking" name="ranking_max" text="Ranked in top" type="number" min={1} max={10000} step={1} value={filters.ranking_max} placeholder="e.g. 200" />
            <Choice id="us-ranking-system" name="ranking_system" text="Ranking system" value={filters.ranking_system} options={pairs(RANKING_SYSTEMS)} />
            <Input id="us-course" name="course" text="Course" maxLength={100} value={filters.course} placeholder="Title or category, e.g. Business" />
            <Choice id="us-level" name="level" text="UG / PG" value={filters.level} options={pairs(LEVELS)} />
            <Choice id="us-intake" name="intake" text="Intake" value={filters.intake} options={pairs(MONTHS)} />
            <Input id="us-tuition-min" name="tuition_min" text="Tuition from" type="number" min={0} step="any" value={filters.tuition_min} />
            <Input id="us-tuition-max" name="tuition_max" text="Tuition up to" type="number" min={0} step="any" value={filters.tuition_max} />
            <Choice id="us-currency" name="tuition_currency" text="Tuition currency" value={filters.tuition_currency} options={pairs(CURRENCIES)} />
            <Choice id="us-scholarship" name="scholarship" text="Scholarship" value={filters.scholarship} options={[["true", "Scholarship available"]]} />
            {COMMISSION_ROLES.has(user.role) && (
              <Input id="us-commission" name="commission_min" text="Commission at least (%)" type="number" min={0.01} max={100} step="any" value={filters.commission_min} />
            )}
            <Choice id="us-status" name="partner_status" text="Partner status" value={filters.partner_status} options={Object.entries(PARTNER_STATUSES)} />
            <Choice id="us-priority" name="priority" text="Priority" value={filters.priority} options={pairs(PRIORITIES)} />
            <Choice id="us-manager" name="manager" text="Partnership manager" value={filters.manager} options={managerOptions} />
            <Input id="us-expected-from" name="expected_from" text="Expected partnership from" type="date" value={filters.expected_from} />
            <Input id="us-expected-to" name="expected_to" text="Expected partnership to" type="date" value={filters.expected_to} />
            <Choice id="us-activity" name="activity" text="Active / inactive" value={filters.activity} options={Object.entries(ACTIVITY)} any="Active" />
            <Choice id="us-exclusivity" name="exclusivity" text="Exclusive / non-exclusive" value={filters.exclusivity} options={Object.entries(EXCLUSIVITY)} />
          </div>
          {/* upc-025: the map's exact country and stage have no field here; they ride along and can be removed */}
          {fromMap.length > 0 && (
            <p className="muted" style={{ fontSize: 13, margin: "12px 0 0" }}>
              {fromMap.map(({ key, text }) => (
                <span key={key} style={{ marginRight: 12 }}>
                  <input type="hidden" name={key} value={filters[key]} />
                  {text} <Link href={searchHref(filters, { [key]: "" })} aria-label={`Remove ${text}`}>Remove</Link>
                </span>
              ))}
            </p>
          )}
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, marginTop: 12 }}>
            <button className="btn small" type="submit">Search</button>
            {isFiltered(filters) && <Link className="btn secondary small" href={SEARCH_PATH}>Clear</Link>}
          </div>
        </form>
        {!page ? (
          <p className="form-error" role="alert">{problem}</p>
        ) : (
          <>
            <nav aria-label="Partner status" style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "16px 0" }}>
              {statusCounts(page.facets).map(([status, count]) => {
                const current = (filters.partner_status ?? "") === status;
                return (
                  <Link key={status || "any"} className={`btn small ${current ? "" : "secondary"}`} aria-current={current ? "true" : undefined} href={searchHref(filters, { partner_status: status })}>
                    {status ? PARTNER_STATUSES[status] : "Any"} ({count})
                  </Link>
                );
              })}
            </nav>
            {page.total === 0 ? (
              <p className="empty" role="status">{isFiltered(filters) ? "No universities match these filters." : "No active universities yet."}</p>
            ) : page.items.length === 0 ? (
              <>
                <p className="empty" role="status">This page is past the end of the results.</p>
                <Link className="btn secondary small" href={searchHref(filters)}>Go to the first page</Link>
              </>
            ) : (
              <div className="telecaller-list">
                <div className="table-wrap" role="region" aria-label="Universities found" tabIndex={0}>
                  <table>
                    <caption className="visually-hidden">Universities found, {page.total} in total</caption>
                    <thead>
                      <tr>
                        <th scope="col">University</th><th scope="col">Country / city</th><th scope="col">Type</th><th scope="col">Ranking</th>
                        <th scope="col">Partner status</th><th scope="col">Manager</th><th scope="col">Expected partnership</th>
                        {withCourses && <th scope="col">Matching courses</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {page.items.map((u) => (
                        <tr key={u.id}>
                          {/* one wrapper per mixed cell -- on a phone each cell is a flex row (upc-026 QA-01) */}
                          <td data-label="University"><span><Link href={universityPath(u.id)}>{u.name}</Link> <span className="muted" style={{ whiteSpace: "nowrap" }}>{u.university_code}</span>{!u.active && <> <span className="badge">Inactive</span></>}</span></td>
                          <td data-label="Country / city"><span>{u.country.name} <span className="muted">{u.city}</span></span></td>
                          <td data-label="Type">{label(INSTITUTION_TYPES, u.institution_type)}{u.ownership_type && `, ${label(OWNERSHIP_TYPES, u.ownership_type)}`}</td>
                          <td data-label="Ranking">{u.ranking ?? "—"}</td>
                          <td data-label="Partner status"><span><span className="badge">{PARTNER_STATUSES[u.partner_status]}</span> <span className="muted">{u.stage_label}</span></span></td>
                          <td data-label="Manager">{u.primary_manager?.full_name ?? "Unassigned"}</td>
                          <td data-label="Expected partnership">{dateText(u.target_partnership_date)}</td>
                          {withCourses && <td data-label="Matching courses">{u.matching_courses ?? 0}</td>}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {page.total > page.limit && (
                  <nav aria-label="Result pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                    <span className="muted" style={{ fontSize: 13 }}>Showing {page.offset + 1}–{end} of {page.total}</span>
                    {page.offset > 0 && <Link className="btn secondary small" aria-label="Previous page" href={searchHref(filters, {}, Math.max(0, page.offset - page.limit))}>Previous</Link>}
                    {end < page.total && <Link className="btn secondary small" aria-label="Next page" href={searchHref(filters, {}, end)}>Next</Link>}
                  </nav>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </PortalShell>
  );
}
