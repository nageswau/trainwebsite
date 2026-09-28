import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import PortfolioPanel from "@/components/PortfolioPanel";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import { loadPortfolio, type PortfolioData } from "@/lib/portfolio";
import type { User } from "@/lib/types";

// QA24-01 (ENH-024 browser QA): the Academic Team is one of the three Digital Portfolio writers (DEC-SCOPE-031 D10, ENH-012's
// WRITE_ROLES) but had no screen to write from -- only the read-only 360° view. This is its student page, reached the way the
// coordinator reaches hers: dashboard directory -> student page -> "Open 360° view" (whose back link returns here). The API
// enforces the team's school-portfolio scope and decides `can_edit`; this page adds no rule of its own.
export default async function SchoolAcademicTeamStudentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User;
  let portfolio: PortfolioData;
  try {
    [user, portfolio] = await Promise.all([serverApi<User>("/api/v1/auth/me"), loadPortfolio(id)]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV["academic-team"]} roleLabel="Academic Team" userName={user.full_name}>
      <div className="portal-content">
        <div className="card">
          <h1>{portfolio.student.full_name}</h1>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <a className="btn" href={`/school/academic-team/students/${id}/360`}>Open 360° view</a>
            <a className="btn secondary" href="/school/academic-team/dashboard">Back to dashboard</a>
          </div>
        </div>
        <PortfolioPanel data={portfolio} />
      </div>
    </PortalShell>
  );
}
