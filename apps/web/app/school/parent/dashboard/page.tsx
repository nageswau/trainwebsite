import PortalShell from "@/components/PortalShell";
import { ChildStatusRow, childrenSpanSchools, formatDate, loadChildOverview, type ChildOverview } from "@/components/SchoolChildOverview";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

type Student = { id: string; student_code: string; full_name: string; date_of_birth: string | null; grade_or_class: string | null };
type NotificationItem = { id: string; title: string; body: string; read: boolean; action_url: string | null; created_at: string };

// SCH-001 + SCH-007: a Parent's view of their own child(ren) -- own SchoolParentLink rows
// only, read-only (SCH-001-AC03). ENH-008: a parent's links can span more than one
// institution, so this is no longer "own institution AND own child(ren)". One card per linked child with the child's
// career-guidance / counselling / psychometric status and published-result count, a link
// to the full child page, the school's upcoming sessions, and the parent's latest
// notifications. No switcher control: every child's summary is visible at once.
export default async function SchoolParentDashboardPage() {
  let user: User;
  let children: Student[];
  let notifications: NotificationItem[] = [];
  try {
    [user, children] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Student[]>("/api/v1/school/students")]);
    notifications = await serverApi<NotificationItem[]>("/api/v1/workflows/notifications").catch(() => []);
  } catch (e) {
    return (
      <div className="section">
        <div className="container card">
          <h1>Access unavailable</h1>
          <p>{e instanceof Error ? e.message : "Unable to load this workspace"}</p>
          <a className="btn" href="/overseas/login">Return to login</a>
        </div>
      </div>
    );
  }
  const overviews = await Promise.all(children.map((c) => loadChildOverview(c.id).catch(() => null)));
  const multiSchool = childrenSpanSchools(overviews); // ENH-008 Task 8: only then are cards grouped under a school heading (not a per-card name)
  const upcoming = new Map<string, ChildOverview["activities"]["upcoming"][number]>();
  for (const o of overviews) for (const a of o?.activities.upcoming ?? []) upcoming.set(a.id, a);
  const upcomingList = [...upcoming.values()].sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at));
  const latest = notifications.slice(0, 5);
  const unread = notifications.filter((n) => !n.read).length;

  return (
    <PortalShell nav={SCHOOL_NAV.parent} roleLabel="Parent" userName={user.full_name}>
      <div className="portal-content">
        <h1>My children</h1>
        {children.length === 0 ? (
          <div className="card">
            <p className="muted">No child linked to your account yet. Contact your school to get set up.</p>
          </div>
        ) : (
          (() => {
            const cards = children.map((c, i) => {
              const o = overviews[i];
              return (
                <div className="card" key={c.id} data-testid={`child-card-${c.id}`}>
                  <h2>{c.full_name} <span className="muted" style={{ fontSize: 14 }}>({c.student_code})</span></h2>
                  <p><strong>Grade/Class:</strong> {c.grade_or_class || "-"}</p>
                  <p><strong>Date of birth:</strong> {formatDate(c.date_of_birth)}</p>
                  {o ? (
                    <>
                      <p><strong>Class teacher:</strong> {o.student.assigned_teacher_name || "Not assigned yet"}</p>
                      <ChildStatusRow overview={o} />
                      {o.recommended_careers.length > 0 && (
                        <p><strong>Recommended careers:</strong> {o.recommended_careers.map((r) => <span className="badge" key={r.id} style={{ marginRight: 6 }}>{r.notes}</span>)}</p>
                      )}
                    </>
                  ) : (
                    <p className="muted">Progress details are unavailable right now.</p>
                  )}
                  <a className="btn" href={`/school/parent/children/${c.id}`}>View full profile &amp; progress</a>
                </div>
              );
            });
            if (!multiSchool) return cards;
            const bySchool = new Map<string, typeof cards>();
            children.forEach((c, i) => {
              const school = overviews[i]?.student.school_name || "Other";
              bySchool.set(school, [...(bySchool.get(school) ?? []), cards[i]]);
            });
            return [...bySchool.entries()].map(([school, group]) => (
              <div key={school}>
                <h2 style={{ marginTop: 24 }}>{school}</h2>
                {group}
              </div>
            ));
          })()
        )}

        <div className="card">
          <h2>Upcoming sessions</h2>
          {upcomingList.length === 0 ? (
            <p className="muted">Nothing scheduled yet.</p>
          ) : (
            <ul>{upcomingList.map((a) => <li key={a.id}><strong>{formatDate(a.scheduled_at, true)}</strong> — {a.title}</li>)}</ul>
          )}
        </div>

        <div className="card">
          <h2>Important notifications {unread > 0 && <span className="badge">{unread} unread</span>}</h2>
          {latest.length === 0 ? (
            <p className="muted">No notifications yet. You will be notified here when an assessment, counselling session, workshop, or result is recorded for your child.</p>
          ) : (
            <ul>
              {latest.map((n) => (
                <li key={n.id} style={{ marginBottom: 8 }}>
                  <strong>{n.title}</strong> <span className="muted">{formatDate(n.created_at, true)}</span>
                  <br />
                  {n.body} {n.action_url && <a href={n.action_url}>Open</a>}
                </li>
              ))}
            </ul>
          )}
          <a className="btn secondary" href="/school/parent/notifications">All notifications</a>
        </div>
      </div>
    </PortalShell>
  );
}
