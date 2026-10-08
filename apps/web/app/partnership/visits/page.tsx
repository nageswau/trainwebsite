import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import VisitTable from "@/components/VisitTable";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { PAGE_SIZE, pageOffset } from "@/lib/telecaller";
import type { User } from "@/lib/types";
import { shellFor } from "@/lib/universities";
import { APPROVALS_PATH, newVisitPath, PLANNER_ROLES, VISIT_STATUSES, VISITS_PATH, VISITS_URL, type VisitFilters, visitListQuery, visitPageHref, type VisitRow } from "@/lib/visits";

// upc-010 (§8): every university visit, for the partnership roles (VS7). Filters and paging live in the URL; a plain GET form, so it
// works without JavaScript. The API is the gate: any other role gets its 403 here with a link home.
export default async function VisitsPage({ searchParams }: { searchParams: Promise<VisitFilters> }) {
  const filters = await searchParams;
  const offset = pageOffset(filters.offset);
  let user: User, page: Page<VisitRow>;
  try {
    [user, page] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Page<VisitRow>>(`${VISITS_URL}?${visitListQuery(filters, PAGE_SIZE, offset)}`)]);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const filtered = Boolean(filters.status || filters.mine || filters.university_id);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">University Visits</div>
            <h2>University visits</h2>
            <p className="muted">Visits to partner and target universities, separate from meetings. A visit needs the partnership head&apos;s approval before travel is booked.</p>
          </div>
          <div className="actions">
            {user.role !== "partnership_manager" && <Link className="btn secondary" href={APPROVALS_PATH}>Visit approvals</Link>}
            {PLANNER_ROLES.has(user.role) && <Link className="btn" href={newVisitPath()}>Plan a visit</Link>}
          </div>
        </div>
        <form method="get" action={VISITS_PATH} className="card" aria-label="Filter visits" style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end", padding: 14, marginBottom: 16 }}>
          {filters.university_id && <input type="hidden" name="university_id" value={filters.university_id} />}
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="visit-filter-status">Status</label>
            <select id="visit-filter-status" name="status" defaultValue={filters.status ?? ""}>
              <option value="">Any status</option>
              {Object.entries(VISIT_STATUSES).map(([key, word]) => <option key={key} value={key}>{word}</option>)}
            </select>
          </div>
          <label style={{ display: "inline-flex", gap: 6, alignItems: "center", minHeight: 40 }}>
            <input type="checkbox" name="mine" value="true" defaultChecked={filters.mine === "true"} /> Only my visits
          </label>
          <button type="submit" className="btn secondary small">Apply</button>
          {filtered && <Link className="btn ghost small" href={VISITS_PATH}>Clear</Link>}
        </form>
        {page.total === 0 ? (
          <p className="empty" role="status">{filtered ? "No visits match these filters." : "No visits planned yet."}</p>
        ) : page.items.length === 0 ? (
          <>
            <p className="empty" role="status">This page is past the end of the list.</p>
            <Link className="btn secondary small" href={visitPageHref(filters, 0)}>Go to the first page</Link>
          </>
        ) : (
          <VisitTable page={page} label="University visits" pageHref={(o) => visitPageHref(filters, o)} />
        )}
      </div>
    </PortalShell>
  );
}
