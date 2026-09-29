import PortalShell from "@/components/PortalShell";
import SchoolAnalyticsSections from "@/components/SchoolAnalyticsSections";
import SchoolReportsPanel from "@/components/SchoolReportsPanel";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import { loadSchoolAnalytics } from "@/lib/schoolAnalytics";
import type { User } from "@/lib/types";
import { accessUnavailable } from "@/components/AccessUnavailable";

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
    [user, report] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<ReportData>("/api/v1/school/reports")]);
  } catch (e) {
    return accessUnavailable(e);
  }
  const analytics = await loadSchoolAnalytics(await searchParams);
  return (
    <PortalShell nav={SCHOOL_NAV.coordinator} roleLabel="School Coordinator" userName={user.full_name}>
      <SchoolReportsPanel report={report} />
      <SchoolAnalyticsSections data={analytics} role="coordinator" />
    </PortalShell>
  );
}
