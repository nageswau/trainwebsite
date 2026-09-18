import PortalShell from "@/components/PortalShell";
import SchoolChildOverview, { loadChildOverview, type ChildOverview } from "@/components/SchoolChildOverview";
import SchoolStudentTimeline, { loadStudentTimeline, type StudentTimeline } from "@/components/SchoolStudentTimeline";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// SCH-007: one child's full profile & progress for their Parent. Same own-child deny as
// the dashboard, verified server-side even via this direct record ID (SCH-001-AC03).
// SCH-008: the journey timeline is fetched with the same own-scope check, on its own --
// a failure there never blocks the rest of the page from rendering.
export default async function SchoolParentChildPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User;
  let overview: ChildOverview;
  try {
    [user, overview] = await Promise.all([serverApi<User>("/api/v1/auth/me"), loadChildOverview(id)]);
  } catch (e) {
    return (
      <div className="section">
        <div className="container card">
          <h1>Access unavailable</h1>
          <p>{e instanceof Error ? e.message : "This student is not linked to your account, or does not exist."}</p>
          <a className="btn" href="/school/parent/dashboard">Back to my children</a>
        </div>
      </div>
    );
  }
  const timeline: StudentTimeline | null = await loadStudentTimeline(id).catch(() => null);
  return (
    <PortalShell nav={SCHOOL_NAV.parent} roleLabel="Parent" userName={user.full_name}>
      <div className="portal-content">
        <a className="btn secondary" href="/school/parent/dashboard">Back to my children</a>
        <SchoolChildOverview overview={overview} />
        <div className="card">
          <h3>Journey timeline</h3>
          {timeline ? <SchoolStudentTimeline events={timeline.events} /> : <p className="muted">Timeline is unavailable right now.</p>}
        </div>
      </div>
    </PortalShell>
  );
}
