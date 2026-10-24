import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import CounselorTaskForm from "@/components/CounselorTaskForm";
import CounselorTaskList from "@/components/CounselorTaskList";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { COUNSELOR_FOLLOW_UPS_API, COUNSELOR_TASKS_API, LIST_LIMIT, type CounselorTaskOptions, type CounselorTaskPage } from "@/lib/counselorTasks";
import { formatDateTimeIn, SCHOOL_TIME_ZONE } from "@/lib/formatDate";
import { PORTAL_NAV } from "@/lib/navigation";
import { reasonLabel, type FollowUpPage } from "@/lib/telecallerFollowUps";
import type { User } from "@/lib/types";

// ccrm-029 (DEC-SCOPE-250, T6/T7, spec AC 7): the overseas counselor's own tasks in Overdue / Today / Upcoming / Done, an add form, then
// their overdue lead follow-ups. A failed follow-up read only blanks that section. Unauthenticated users are redirected by the middleware.
const REFUSED = "Only an overseas counselor has a task list";

export default async function CounselorTasksPage() {
  let user: User, tasks: CounselorTaskPage, options: CounselorTaskOptions;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "counselor" || user.division !== "overseas") return accessDenied(user, REFUSED);
    [tasks, options] = await Promise.all([
      serverApi<CounselorTaskPage>(`${COUNSELOR_TASKS_API}?limit=${LIST_LIMIT}`),
      serverApi<CounselorTaskOptions>(`${COUNSELOR_TASKS_API}/options`),
    ]);
  } catch (e) {
    return accessUnavailable(e);
  }
  const followUps = await serverApi<FollowUpPage>(`${COUNSELOR_FOLLOW_UPS_API}?view=overdue&limit=50`).catch(() => null);
  return (
    <PortalShell nav={PORTAL_NAV["overseas/counselor"]} roleLabel="Counselor" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Workspace</div>
            <h2>My tasks</h2>
            <p className="muted">
              {tasks.counts.overdue} overdue · {tasks.counts.today} due today · {tasks.counts.upcoming} upcoming. Tasks the Overseas Admin gives you show here too.
            </p>
          </div>
        </div>
        <div style={{ display: "grid", gap: 24, maxWidth: 900 }}>
          <CounselorTaskForm options={options} today={tasks.today} />
          <CounselorTaskList items={tasks.items} options={options} today={tasks.today} empty="You have no open tasks. Add one above." />
          <section aria-labelledby="overdue-follow-ups">
            <h3 id="overdue-follow-ups">Overdue follow-ups{followUps ? ` (${followUps.counts.overdue})` : ""}</h3>
            {followUps === null ? (
              <p className="form-error" role="alert">Your follow-ups can&apos;t be loaded right now. Try again in a moment.</p>
            ) : followUps.items.length === 0 ? (
              <p className="empty" role="status">No follow-ups on your leads are overdue.</p>
            ) : (
              <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 10 }}>
                {followUps.items.map((f) => (
                  <li key={f.id} className="action-card" style={{ display: "grid", gap: 4, overflowWrap: "anywhere" }}>
                    <Link href={`/overseas/counselor/leads/${encodeURIComponent(f.lead.id)}`} style={{ fontWeight: 700 }}>{f.lead.lead_code} · {f.lead.name}</Link>
                    <span className="muted" style={{ fontSize: 14 }}>Was due {formatDateTimeIn(f.due_at, SCHOOL_TIME_ZONE, true)} · {reasonLabel(f.reason)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </PortalShell>
  );
}
