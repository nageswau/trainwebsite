import PortalShell from "@/components/PortalShell";
import SchoolCareerRecordsPanel from "@/components/SchoolCareerRecordsPanel";
import Student360Directory from "@/components/Student360Directory";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessUnavailable } from "@/components/AccessUnavailable";

type Student = { id: string; full_name: string; school_name: string };
type Record_ = { id: string; school_student_id: string; record_type: string; notes: string; created_at: string };

// SCH-004: every assigned student, one list -- the Career Counselor's starting point for
// adding a guidance session, counselling note, or recommendation.
export default async function SchoolCareerCounselorDashboardPage() {
  let user: User;
  let records: Record_[];
  let students: Student[];
  try {
    [user, records, students] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<Record_[]>("/api/v1/school/career-counselor/records"),
      serverApi<Student[]>("/api/v1/school/portfolio-students"),
    ]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV["career-counselor"]} roleLabel="Career Counselor" userName={user.full_name}>
      <SchoolCareerRecordsPanel records={records} students={students} />
      <Student360Directory role="career_counselor" students={students} />
    </PortalShell>
  );
}
