import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import MeetingTable from "@/components/MeetingTable";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import {
  type MeetingFilters, meetingListQuery, type MeetingPage, meetingPageHref, MEETINGS_PATH, MEETINGS_URL, newMeetingPath, SCHEDULER_ROLES,
  VIEW_EMPTY, VIEW_LABELS, viewOf, VIEWS,
} from "@/lib/meetings";
import { PAGE_SIZE, pageOffset } from "@/lib/telecaller";
import type { User } from "@/lib/types";
import { shellFor } from "@/lib/universities";

// upc-009 (§7, MG16): every university meeting, for the partnership roles (MG14), in four views with counts. Filters and paging live in
// the URL, so refresh and back keep them; the tabs and the "mine" toggle are plain links and a GET form (they work without JavaScript).
// The API is the gate: any other role gets its 403 here with a link home.
export default async function MeetingsPage({ searchParams }: { searchParams: Promise<MeetingFilters> }) {
  const filters = await searchParams;
  const view = viewOf(filters.view);
  const offset = pageOffset(filters.offset);
  let user: User, page: MeetingPage;
  try {
    [user, page] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<MeetingPage>(`${MEETINGS_URL}?${meetingListQuery(filters, PAGE_SIZE, offset)}`)]);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const end = page.offset + page.items.length;
  const keep = { university_id: filters.university_id, mine: filters.mine };
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Meetings</div>
            <h2>University meetings</h2>
            <p className="muted">Every interaction scheduled with a university. Record the outcome after the meeting: its next action becomes a follow-up.</p>
          </div>
          {SCHEDULER_ROLES.has(user.role) && <div className="actions"><Link className="btn" href={newMeetingPath(filters.university_id)}>Schedule a meeting</Link></div>}
        </div>
        <nav aria-label="Meeting views" style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
          {VIEWS.map((v) => (
            <Link key={v} className={`btn small ${v === view ? "" : "secondary"}`} aria-current={v === view ? "page" : undefined} href={meetingPageHref({ ...keep, view: v })}>
              {VIEW_LABELS[v]} <span className="badge">{page.counts[v]}</span>
            </Link>
          ))}
        </nav>
        <form method="get" action={MEETINGS_PATH} className="card" aria-label="Filter meetings" style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", padding: 14, marginBottom: 16 }}>
          <input type="hidden" name="view" value={view} />
          {filters.university_id && <input type="hidden" name="university_id" value={filters.university_id} />}
          <label style={{ display: "inline-flex", gap: 6, alignItems: "center", minHeight: 40 }}>
            <input type="checkbox" name="mine" value="true" defaultChecked={filters.mine === "true"} /> Only my meetings
          </label>
          <button type="submit" className="btn secondary small">Apply</button>
          {(filters.mine || filters.university_id) && <Link className="btn ghost small" href={meetingPageHref({ view })}>Clear</Link>}
        </form>
        {page.total === 0 ? (
          <p className="empty" role="status">{filters.mine || filters.university_id ? "No meetings match these filters." : VIEW_EMPTY[view]}</p>
        ) : page.items.length === 0 ? (
          <>
            <p className="empty" role="status">This page is past the end of the list.</p>
            <Link className="btn secondary small" href={meetingPageHref({ ...keep, view })}>Go to the first page</Link>
          </>
        ) : (
          <>
            <MeetingTable items={page.items} total={page.total} label={`${VIEW_LABELS[view]} meetings`} />
            {page.total > page.limit && (
              <nav aria-label="Meeting pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                <span className="muted" style={{ fontSize: 13 }}>Showing {page.offset + 1}–{end} of {page.total}</span>
                {page.offset > 0 && <Link className="btn secondary small" aria-label="Previous page" href={meetingPageHref({ ...keep, view }, Math.max(0, page.offset - page.limit))}>Previous</Link>}
                {end < page.total && <Link className="btn secondary small" aria-label="Next page" href={meetingPageHref({ ...keep, view }, end)}>Next</Link>}
              </nav>
            )}
          </>
        )}
      </div>
    </PortalShell>
  );
}
