import PortalShell from "@/components/PortalShell";
import SchoolReportsPanel from "@/components/SchoolReportsPanel";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
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

// Principal's Reports view -- same read-only report as the Coordinator's own
// (GET /school/reports, own institution scope), reusing SchoolReportsPanel rather than
// duplicating the chart layout.
export default async function SchoolPrincipalReportsPage() {
  let user: User;
  let report: ReportData;
  try {
    [user, report] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<ReportData>("/api/v1/school/reports")]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.principal} roleLabel="Principal" userName={user.full_name}>
      <SchoolReportsPanel report={report} />
    </PortalShell>
  );
}
