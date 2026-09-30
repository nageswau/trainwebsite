import PortalShell from "@/components/PortalShell";
import SchoolChildOverview, { loadChildOverview, type ChildOverview } from "@/components/SchoolChildOverview";
import SchoolGradeHistory, { loadGradeHistory, type StudentGradeHistory } from "@/components/SchoolGradeHistory";
import SchoolStudentTimeline, { loadStudentTimeline, type StudentTimeline } from "@/components/SchoolStudentTimeline";
import SchoolTransferHistory, { loadTransferHistory, type TransferHistoryEntry } from "@/components/SchoolTransferHistory";
import PortfolioPanel from "@/components/PortfolioPanel";
import ReportDownloadButton from "@/components/ReportDownloadButton";
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
        {/* QA15-03: flex-start, so a download message under its button does not stretch the other buttons in the row.
            QA15-11: `child-page-actions` narrows the download hint here only, so it cannot widen the row. */}
        <div className="child-page-actions" style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-start" }}>
          <a className="btn" href={`/school/parent/children/${id}/360`}>Open 360° view</a>
          {/* ENH-015: the same overview as a PDF -- own linked child only, checked by the server. */}
          <ReportDownloadButton url={`/api/v1/school/students/${id}/progress-report`} label="Download progress report (PDF)" filename="progress-report.pdf" hint="PDFs are not screen-reader friendly. The same information is on this page." />
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
