import PortalShell from "@/components/PortalShell";
import ReportDownloadButton from "@/components/ReportDownloadButton";
import SchoolAnalyticsSections from "@/components/SchoolAnalyticsSections";
import SchoolReportsPanel from "@/components/SchoolReportsPanel";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import { loadSchoolAnalytics } from "@/lib/schoolAnalytics";
import type { User } from "@/lib/types";
import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";

type ReportData = {
  student_count: number;
  students_with_teacher: number;
  teacher_count: number;
  parent_count: number;
  principal_count: number;
  pending_invite_count: number;
  grade_breakdown: { grade: string; count: number }[];
  career_guidance: { students_covered: number; total_students: number };
  psychometric: { completed: number; assigned_only: number; total_students: number };
  results_published: { students_covered: number; total_students: number };
  activities: { total: number; upcoming: number; past: number };
  attendance: { present: number; total: number };
};

// School Coordinator's Reports view -- real, computed-from-live-data figures only
// (GET /school/reports, own institution scope). Part of the Coordinator's own SCHOOL_NAV
// (lib/navigation.ts), not the shared PORTAL_NAV/[section] dispatcher. ENH-016 adds the
// §29 / Part B §14 / §28 analytics sections below it, each loaded on its own.
export default async function SchoolCoordinatorReportsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  let user: User;
  let report: ReportData;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    // QA15-08: the coordinator's page only -- a principal has their own Reports page and must not get this shell and nav.
    if (user.role !== "school_coordinator") return accessDenied(user, "School Coordinator role required");
    report = await serverApi<ReportData>("/api/v1/school/reports");
  } catch (e) {
    return accessUnavailable(e);
  }
  const analytics = await loadSchoolAnalytics(await searchParams);
  return (
    <PortalShell nav={SCHOOL_NAV.coordinator} roleLabel="School Coordinator" userName={user.full_name}>
      {/* ENH-015: the downloadable School Summary PDF (own school), above the on-screen report it summarises. */}
      <div className="portal-content report-downloads">
        <div className="card">
          <h2>Download reports</h2>
          <p className="muted">A PDF of your school&apos;s summary figures and grade-by-grade table, as of today.</p>
          <ReportDownloadButton url="/api/v1/school/reports/school-summary" label="Download school report (PDF)" filename="school-report.pdf" />
        </div>
      </div>
      <SchoolReportsPanel report={report} />
      <SchoolAnalyticsSections data={analytics} role="coordinator" />
    </PortalShell>
  );
}
