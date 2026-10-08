import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import UniversityFilters from "@/components/UniversityFilters";
import UniversityTable from "@/components/UniversityTable";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { PAGE_SIZE, pageOffset } from "@/lib/telecaller";
import type { User } from "@/lib/types";
import { IMPORT_PATH } from "@/lib/universityImport";
import { CREATOR_ROLES, type Filters, listQuery, shellFor, UNIVERSITIES_PATH, UNIVERSITIES_URL, type UniversityRow } from "@/lib/universities";

// upc-003: the University Master list for every role that reads it (partnership managers and heads, overseas_admin, super_admin). The
// API is the gate and decides each row's actions; filters and paging live in the URL.
export default async function UniversitiesPage({ searchParams }: { searchParams: Promise<Filters> }) {
  const filters = await searchParams;
  const offset = pageOffset(filters.offset);
  let user: User, page: Page<UniversityRow>;
  try {
    [user, page] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<Page<UniversityRow>>(`${UNIVERSITIES_URL}?${listQuery(filters, PAGE_SIZE, offset)}`),
    ]);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const filtered = Object.entries(filters).some(([key, value]) => key !== "offset" && value);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">University Master</div>
            <h2>Universities and institutions</h2>
            <p className="muted">One record per institution, shared across EduSphere. Only published universities appear in the public catalogue.</p>
          </div>
          {CREATOR_ROLES.has(user.role) && (
            <div className="actions">
              <Link className="btn secondary" href={IMPORT_PATH}>Import universities</Link>
              <Link className="btn" href={`${UNIVERSITIES_PATH}/new`}>Add university</Link>
            </div>
          )}
        </div>
        <UniversityFilters filters={filters} isManager={user.role === "partnership_manager"} />
        {page.total === 0 ? (
          <p className="empty" role="status">{filtered ? "No universities match these filters." : "No universities yet."}</p>
        ) : page.items.length === 0 ? (
          <>
            <p className="empty" role="status">This page is past the end of the list.</p>
            <Link className="btn secondary small" href={UNIVERSITIES_PATH}>Go to the first page</Link>
          </>
        ) : (
          <UniversityTable page={page} filters={filters} />
        )}
      </div>
    </PortalShell>
  );
}
