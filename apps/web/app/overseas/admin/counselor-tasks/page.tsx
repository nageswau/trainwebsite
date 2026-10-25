import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import CounselorTaskForm from "@/components/CounselorTaskForm";
import CounselorTaskList from "@/components/CounselorTaskList";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import OverdueByCounselor from "@/components/OverdueByCounselor";
import {
  adminFilters, adminTasksUrl, BANDS, COUNSELOR_TASKS_API, OVERDUE_BY_COUNSELOR_API, type CounselorTaskOptions, type CounselorTaskPage, type OverdueByCounselorPage,
} from "@/lib/counselorTasks";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ccrm-029 (DEC-SCOPE-250, CC3/T3): the Overseas Admin's view of every counselor's tasks -- filter by counselor and band (a GET form, so
// the filters are in the URL), add a task for any active overseas counselor, and change or cancel any task. Super Admin passes too.
const ADMIN_ROLES = ["overseas_admin", "super_admin"];

export default async function AdminCounselorTasksPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const filters = adminFilters(await searchParams);
  let user: User, tasks: CounselorTaskPage, options: CounselorTaskOptions, overdue: OverdueByCounselorPage;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (!ADMIN_ROLES.includes(user.role)) return accessDenied(user, "Overseas Administrator role required");
    [tasks, options, overdue] = await Promise.all([
      serverApi<CounselorTaskPage>(adminTasksUrl(filters)),
      serverApi<CounselorTaskOptions>(`${COUNSELOR_TASKS_API}/options`),
      serverApi<OverdueByCounselorPage>(OVERDUE_BY_COUNSELOR_API),
    ]);
  } catch (e) {
    return accessUnavailable(e);
  }
  const filtered = Boolean(filters.counselor || filters.band);
  return (
    <PortalShell nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Workspace</div>
            <h2>Counselor tasks</h2>
            <p className="muted">
              Every overseas counselor&apos;s tasks: {tasks.counts.overdue} overdue · {tasks.counts.today} due today · {tasks.counts.upcoming} upcoming
              {filters.counselor ? " for this counselor" : ""}. The counselor is notified of a task you add or change.
            </p>
          </div>
        </div>
        <div style={{ display: "grid", gap: 24, maxWidth: 900 }}>
          <OverdueByCounselor data={overdue} />
          <CounselorTaskForm options={options} today={tasks.today} admin />
          {/* ccrm-031 QA-01: keyed by the filters so a client-side visit ("View tasks") re-mounts the uncontrolled selects */}
          <form key={`${filters.counselor}:${filters.band}`} method="get" role="search" aria-label="Filter tasks" className="form-grid" style={{ alignItems: "end" }}>
            <div className="field" style={{ margin: 0 }}>
              <label htmlFor="filter-counselor">Counselor</label>
              <select id="filter-counselor" name="counselor" defaultValue={filters.counselor}>
                <option value="">All counselors</option>
                {options.counselors.map((c) => <option key={c.id} value={c.id}>{c.full_name}</option>)}
              </select>
            </div>
            <div className="field" style={{ margin: 0 }}>
              <label htmlFor="filter-band">Show</label>
              <select id="filter-band" name="band" defaultValue={filters.band}>
                <option value="">Open and recently done</option>
                {BANDS.map((b) => <option key={b.band} value={b.band}>{b.label}</option>)}
              </select>
            </div>
            <div className="actions">
              <button className="btn" type="submit">Apply</button>
              {filtered && <Link className="btn ghost" href="/overseas/admin/counselor-tasks">Clear</Link>}
            </div>
          </form>
          {tasks.total > tasks.items.length && <p className="muted" role="status">Showing the first {tasks.items.length} of {tasks.total} tasks. Filter by counselor to see the rest.</p>}
          <CounselorTaskList items={tasks.items} options={options} today={tasks.today} admin empty={filtered ? "No tasks match these filters." : "No counselor has an open task."} />
        </div>
      </div>
    </PortalShell>
  );
}
