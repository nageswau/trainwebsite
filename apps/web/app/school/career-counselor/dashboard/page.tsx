import PortalShell from "@/components/PortalShell";
import SchoolCareerRecordsPanel from "@/components/SchoolCareerRecordsPanel";
import Student360Directory from "@/components/Student360Directory";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessUnavailable } from "@/components/AccessUnavailable";

import type { CareerRecord } from "@/lib/careerRecords";

type Student = { id: string; full_name: string; school_name: string };

// SCH-004: every assigned student, one list -- the Career Counselor's starting point for
// adding a guidance session, counselling note, or recommendation.
export default async function SchoolCareerCounselorDashboardPage() {
  let user: User;
  let records: CareerRecord[];
  let students: Student[];
  try {
    [user, records, students] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<CareerRecord[]>("/api/v1/school/career-counselor/records"),
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
