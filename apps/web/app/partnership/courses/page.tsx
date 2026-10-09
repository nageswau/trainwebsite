import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import {
  commissionText,
  type CourseFilters,
  courseListQuery,
  coursePageHref,
  type CourseRow,
  COURSES_PATH,
  COURSES_URL,
  englishText,
  LEVELS,
} from "@/lib/courseMaster";
import { PAGE_SIZE, pageOffset } from "@/lib/telecaller";
import type { User } from "@/lib/types";
import { shellFor, universityPath } from "@/lib/universities";

// upc-017 (CO15): the §32 "🎓 Courses & Programs" menu -- every university's courses, by university then title, filtered by level, status
// and a title / university search. Courses are added, edited and imported on each university's page. The commission column appears only
// when the API sent commission, which it does for the commission roles alone (U2).
const STATUSES = { active: "Active", inactive: "Inactive", all: "All" } as const;

export default async function CoursesPage({ searchParams }: { searchParams: Promise<CourseFilters> }) {
  const filters = await searchParams;
  const offset = pageOffset(filters.offset);
  let user: User, page: Page<CourseRow>;
  try {
    [user, page] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Page<CourseRow>>(`${COURSES_URL}?${courseListQuery(filters, PAGE_SIZE, offset)}`)]);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const filtered = Boolean(filters.level || (filters.status && filters.status !== "active") || filters.q?.trim());
  const withCommission = page.items.some((c) => "commission" in c);
  const end = page.offset + page.items.length;
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Courses &amp; Programs</div>
            <h2>Courses &amp; programmes</h2>
            <p className="muted">What each university offers. Add, edit and import courses on the university&apos;s page.</p>
          </div>
        </div>
        <form method="get" action={COURSES_PATH} className="card" aria-label="Filter courses" style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end", padding: 14, marginBottom: 16 }}>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="course-filter-level">Level</label>
            <select id="course-filter-level" name="level" defaultValue={filters.level ?? ""}>
              <option value="">Any level</option>
              {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="course-filter-status">Status</label>
            <select id="course-filter-status" name="status" defaultValue={filters.status ?? "active"}>
              {Object.entries(STATUSES).map(([key, word]) => <option key={key} value={key}>{word}</option>)}
            </select>
          </div>
          <div className="field" style={{ margin: 0, flex: "1 1 14rem" }}>
            <label htmlFor="course-filter-q">Search</label>
            <input id="course-filter-q" name="q" type="search" maxLength={100} defaultValue={filters.q ?? ""} placeholder="Course, university or code" />
          </div>
          <button type="submit" className="btn secondary small">Apply</button>
          {filtered && <Link className="btn ghost small" href={COURSES_PATH}>Clear</Link>}
        </form>
        {page.total === 0 ? (
          <p className="empty" role="status">{filtered ? "No courses match these filters." : "No courses recorded yet."}</p>
        ) : page.items.length === 0 ? (
          <>
            <p className="empty" role="status">This page is past the end of the list.</p>
            <Link className="btn secondary small" href={coursePageHref(filters, 0)}>Go to the first page</Link>
          </>
        ) : (
          <div className="telecaller-list">
            <div className="table-wrap" role="region" aria-label="Courses" tabIndex={0}>
              <table>
                <caption className="visually-hidden">Courses, {page.total} in total</caption>
                <thead>
                  <tr>
                    <th scope="col">Course</th><th scope="col">University</th><th scope="col">Level</th><th scope="col">Duration</th><th scope="col">Intakes</th>
                    <th scope="col">Tuition fee</th><th scope="col">English</th>{withCommission && <th scope="col">Commission</th>}
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((c) => (
                    <tr key={c.id}>
                      {/* one wrapper per mixed cell -- on a phone each cell is a flex row (upc-026 QA-01) */}
                      <td data-label="Course"><span>{c.title}{!c.active && <> <span className="badge">Inactive</span></>}</span></td>
                      <td data-label="University">
                        <span><Link href={universityPath(c.university.id)}>{c.university.name}</Link> <span className="muted" style={{ whiteSpace: "nowrap" }}>{c.university.country}</span></span>
                      </td>
                      <td data-label="Level">{c.level}</td>
                      <td data-label="Duration">{c.duration}</td>
                      <td data-label="Intakes">{c.intake || "—"}</td>
                      <td data-label="Tuition fee">{c.tuition_fee || "—"}</td>
                      <td data-label="English">{englishText(c) ?? "—"}</td>
                      {withCommission && <td data-label="Commission">{commissionText(c.commission)}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {page.total > page.limit && (
              <nav aria-label="Course pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                <span className="muted" style={{ fontSize: 13 }}>Showing {page.offset + 1}–{end} of {page.total}</span>
                {page.offset > 0 && <Link className="btn secondary small" aria-label="Previous page" href={coursePageHref(filters, Math.max(0, page.offset - page.limit))}>Previous</Link>}
                {end < page.total && <Link className="btn secondary small" aria-label="Next page" href={coursePageHref(filters, end)}>Next</Link>}
              </nav>
            )}
          </div>
        )}
      </div>
    </PortalShell>
  );
}
