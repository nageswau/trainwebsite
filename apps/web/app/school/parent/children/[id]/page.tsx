import PortalShell from "@/components/PortalShell";
import SchoolChildOverview, { loadChildOverview, type ChildOverview } from "@/components/SchoolChildOverview";
import SchoolGradeHistory, { loadGradeHistory, type StudentGradeHistory } from "@/components/SchoolGradeHistory";
import SchoolStudentTimeline, { loadStudentTimeline, type StudentTimeline } from "@/components/SchoolStudentTimeline";
import SchoolTransferHistory, { loadTransferHistory, type TransferHistoryEntry } from "@/components/SchoolTransferHistory";
import PortfolioPanel from "@/components/PortfolioPanel";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { loadPortfolio, type PortfolioData } from "@/lib/portfolio";

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
  const [timeline, gradeHistory, transferHistory, portfolio]: [StudentTimeline | null, StudentGradeHistory | null, TransferHistoryEntry[] | null, PortfolioData | null] = await Promise.all([
    loadStudentTimeline(id).catch(() => null),
    loadGradeHistory(id).catch(() => null),
    loadTransferHistory(id),
    loadPortfolio(id).catch(() => null),
  ]);
  return (
    <PortalShell nav={SCHOOL_NAV.parent} roleLabel="Parent" userName={user.full_name}>
      <div className="portal-content">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <a className="btn" href={`/school/parent/children/${id}/360`}>Open 360° view</a>
          <a className="btn secondary" href="/school/parent/dashboard">Back to my children</a>
        </div>
        <SchoolChildOverview overview={overview} />
        <div className="card">
          <h3>Grade history</h3>
          {gradeHistory ? <SchoolGradeHistory history={gradeHistory.history} /> : <p className="muted">Grade history is unavailable right now.</p>}
        </div>
        <SchoolTransferHistory history={transferHistory} />
        <div className="card">
          <h3>Journey timeline</h3>
          {timeline ? <SchoolStudentTimeline events={timeline.events} /> : <p className="muted">Timeline is unavailable right now.</p>}
        </div>
        {portfolio ? <PortfolioPanel data={portfolio} /> : <div className="card"><h3>Digital Portfolio</h3><p className="muted">Portfolio is unavailable right now.</p></div>}
      </div>
    </PortalShell>
  );
}
