import PortalShell from "@/components/PortalShell";
import SchoolPsychometricRecordsPanel from "@/components/SchoolPsychometricRecordsPanel";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessUnavailable } from "@/components/AccessUnavailable";

type Student = { id: string; full_name: string; school_name: string };
type Record_ = { id: string; school_student_id: string; assessment_type: string; report_url: string | null; status: string; created_at: string };

// SCH-005: every assigned student, one list -- who needs an assessment assigned, who has
// a report pending upload.
export default async function SchoolPsychometricTeamDashboardPage() {
  let user: User;
  let records: Record_[];
  let students: Student[];
  try {
    [user, records, students] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<Record_[]>("/api/v1/school/psychometric-team/records"),
      serverApi<Student[]>("/api/v1/school/portfolio-students"),
    ]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV["psychometric-team"]} roleLabel="Psychometric Team" userName={user.full_name}>
      <SchoolPsychometricRecordsPanel records={records} students={students} />
    </PortalShell>
  );
}
