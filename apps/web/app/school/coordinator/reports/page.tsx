import PortalShell from "@/components/PortalShell";
import SchoolReportsPanel from "@/components/SchoolReportsPanel";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

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
// (lib/navigation.ts), not the shared PORTAL_NAV/[section] dispatcher.
export default async function SchoolCoordinatorReportsPage() {
  let user: User;
  let report: ReportData;
  try {
    [user, report] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<ReportData>("/api/v1/school/reports")]);
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
  return (
    <PortalShell nav={SCHOOL_NAV.coordinator} roleLabel="School Coordinator" userName={user.full_name}>
      <SchoolReportsPanel report={report} />
    </PortalShell>
  );
}
