import Link from "next/link";
import type { InputHTMLAttributes } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PartnershipWorldMap from "@/components/PartnershipWorldMap";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { LEVELS } from "@/lib/courseMaster";
import {
  ACTIVITY, colourOf, countryHref, EXCLUSIVITY, isFiltered, MAP_PATH, MAP_URL, type MapFilters, mapHref, type MapPage, mapQuery,
  STATUS_LABELS, STATUS_ORDER,
} from "@/lib/partnershipMap";
import type { User } from "@/lib/types";
import { INSTITUTION_TYPES, PRIORITIES, RANKING_SYSTEMS, REGIONS, shellFor } from "@/lib/universities";
import { filterProblem, PARTNER_STATUSES } from "@/lib/universitySearch";
import { SHAPES } from "@/lib/worldMapShapes";

// upc-025 (DEC-SCOPE-164): §2 "Global University Partnership Map" -- every country's partner, in-progress, target and lost counts for
// the §2 filters, on an inline SVG map or as a table (the same figures). A plain GET form: the URL holds the filters and the view, so
// Back, Refresh and a shared link keep them, and the page works without client JS. A country opens the upc-024 search for it (MP3).
const INVALID = "These filters are not valid. Change or clear them and try again.";

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

export default async function PartnershipMapPage({ searchParams }: { searchParams: Promise<MapFilters> }) {
  const filters = await searchParams;
  const table = filters.view === "table";
  let problem = filterProblem(filters);
  let user: User, page: MapPage | null = null;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  if (!problem) {
    try {
      page = await serverApi<MapPage>(`${MAP_URL}?${mapQuery(filters)}`);
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 422)) return accessUnavailable(e, "/overseas/login");
      problem = INVALID;
    }
  }
  const { nav, roleLabel } = shellFor(user.role);
  const managerOptions: Option[] = [...(user.role === "partnership_manager" ? [["me", "Assigned to me"] as Option] : []), ["none", "Unassigned"]];
  const undrawn = page?.countries.filter((c) => !c.iso2 || !SHAPES[c.iso2]) ?? [];
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">🗺️ Global Partnership Map</div>
            <h2>Global Partnership Map</h2>
            <p className="muted">Universities by country and partnership status. Select a country to open its universities in the Global University Database.</p>
          </div>
        </div>
        {/* keyed on the filters: a view switch or Clear is a client navigation that would otherwise keep the old uncontrolled values (upc-024 QA24-01) */}
        <form key={mapHref(filters)} className="action-card wide" method="get" action={MAP_PATH} aria-label="Map filters">
          {table && <input type="hidden" name="view" value="table" />}
          <div className="form-grid" style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
            <Input id="pm-country" name="country" text="Country" maxLength={100} value={filters.country} placeholder="e.g. Japan or JP" />
            <Choice id="pm-region" name="region" text="Region" value={filters.region} options={pairs(REGIONS)} />
            <Choice id="pm-status" name="partner_status" text="Partner status" value={filters.partner_status} options={Object.entries(PARTNER_STATUSES)} />
            <Choice id="pm-stage" name="stage" text="Partnership stage" value={filters.stage} options={(page?.stages ?? []).map((s) => [s.key, s.label])} />
            <Choice id="pm-type" name="institution_type" text="University type" value={filters.institution_type} options={Object.entries(INSTITUTION_TYPES)} />
            <Input id="pm-ranking" name="ranking_max" text="Ranked in top" type="number" min={1} max={10000} step={1} value={filters.ranking_max} placeholder="e.g. 200" />
            <Choice id="pm-ranking-system" name="ranking_system" text="Ranking system" value={filters.ranking_system} options={pairs(RANKING_SYSTEMS)} />
            <Input id="pm-course" name="course" text="Course" maxLength={100} value={filters.course} placeholder="Title or category, e.g. Business" />
            <Choice id="pm-level" name="level" text="Course level" value={filters.level} options={pairs(LEVELS)} />
            <Choice id="pm-priority" name="priority" text="Priority" value={filters.priority} options={pairs(PRIORITIES)} />
            <Choice id="pm-manager" name="manager" text="Partnership manager" value={filters.manager} options={managerOptions} />
            <Input id="pm-expected-from" name="expected_from" text="Expected partnership from" type="date" value={filters.expected_from} />
            <Input id="pm-expected-to" name="expected_to" text="Expected partnership to" type="date" value={filters.expected_to} />
            <Choice id="pm-activity" name="activity" text="Active / inactive" value={filters.activity} options={Object.entries(ACTIVITY)} any="" />
            <Choice id="pm-exclusivity" name="exclusivity" text="Exclusive / non-exclusive" value={filters.exclusivity} options={Object.entries(EXCLUSIVITY)} />
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, marginTop: 12 }}>
            <button className="btn small" type="submit">Apply filters</button>
            {isFiltered(filters) && <Link className="btn secondary small" href={mapHref({ view: filters.view })}>Clear</Link>}
          </div>
        </form>
        {!page ? (
          <p className="form-error" role="alert">{problem}</p>
        ) : (
          <>
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12, marginTop: 16 }}>
              <ul className="map-legend" aria-label="Totals by partnership status">
                {STATUS_ORDER.map((status) => (
                  <li key={status}><i className={`map-swatch map-${status}`} aria-hidden="true" /> {STATUS_LABELS[status]}: <strong>{page.totals[status]}</strong></li>
                ))}
                <li><i className="map-swatch map-none" aria-hidden="true" /> No universities</li>
              </ul>
              <nav aria-label="Map view" style={{ display: "flex", gap: 8 }}>
                <Link className={`btn small ${table ? "secondary" : ""}`} aria-current={table ? undefined : "page"} href={mapHref(filters, { view: "" })}>Map</Link>
                <Link className={`btn small ${table ? "" : "secondary"}`} aria-current={table ? "page" : undefined} href={mapHref(filters, { view: "table" })}>Table</Link>
              </nav>
            </div>
            <p className="muted" style={{ fontSize: 13, margin: "0 0 12px" }}>
              {page.totals.total} {page.totals.total === 1 ? "university" : "universities"} in {page.countries.length} {page.countries.length === 1 ? "country" : "countries"}. A
              country takes the colour of its best status: partner, then in progress, then target, then lost.
            </p>
            {page.totals.total === 0 ? (
              <p className="empty" role="status">{isFiltered(filters) ? "No universities match these filters." : "No universities yet."}</p>
            ) : table ? (
              <div className="telecaller-list">
                <div className="table-wrap" role="region" aria-label="Universities by country" tabIndex={0}>
                  <table>
                    <caption className="visually-hidden">Universities by country and partnership status, {page.countries.length} countries</caption>
                    <thead>
                      <tr>
                        <th scope="col">Country</th><th scope="col">Region</th><th scope="col">Partner</th><th scope="col">In progress</th>
                        <th scope="col">Target</th><th scope="col">Lost / closed</th><th scope="col">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {page.countries.map((c) => (
                        <tr key={`${c.iso2}-${c.name}`}>
                          <td data-label="Country"><span><i className={`map-swatch map-${colourOf(c)}`} aria-hidden="true" /> {c.iso2 ? <Link href={countryHref(filters, c.iso2)}>{c.name}</Link> : c.name}</span></td>
                          <td data-label="Region">{c.region ?? "—"}</td>
                          <td data-label="Partner">{c.partner}</td>
                          <td data-label="In progress">{c.in_progress}</td>
                          <td data-label="Target">{c.target}</td>
                          <td data-label="Lost / closed">{c.lost}</td>
                          <td data-label="Total">{c.total}</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr>
                        <th scope="row" data-label="Country">All countries</th><td data-label="Region">—</td><td data-label="Partner">{page.totals.partner}</td>
                        <td data-label="In progress">{page.totals.in_progress}</td><td data-label="Target">{page.totals.target}</td>
                        <td data-label="Lost / closed">{page.totals.lost}</td><td data-label="Total">{page.totals.total}</td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>
            ) : (
              <>
                <PartnershipWorldMap countries={page.countries} filters={filters} />
                {undrawn.length > 0 && (
                  <p className="muted" style={{ fontSize: 13 }}>
                    Not drawn on the map: {undrawn.map((c) => c.name).join(", ")}. <Link href={mapHref(filters, { view: "table" })}>See the table</Link>.
                  </p>
                )}
              </>
            )}
          </>
        )}
      </div>
    </PortalShell>
  );
}
