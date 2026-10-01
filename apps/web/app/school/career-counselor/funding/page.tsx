import PortalShell from "@/components/PortalShell";
import SchoolFundingRecordsPanel from "@/components/SchoolFundingRecordsPanel";
import { accessUnavailable } from "@/components/AccessUnavailable";
import { serverApi } from "@/lib/api";
import type { FundingRecord } from "@/lib/fundingRecords";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

type Student = { id: string; full_name: string; school_name: string };

// ENH-020 (spec §6, SCR-SCH-040): the Career Counsellor's funding support cases across their portfolio, read in one parallel fetch.
export default async function SchoolCareerCounselorFundingPage() {
  let user: User;
  let records: FundingRecord[];
  let students: Student[];
  try {
    [user, records, students] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<FundingRecord[]>("/api/v1/school/career-counselor/funding-records"),
      serverApi<Student[]>("/api/v1/school/portfolio-students"),
    ]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV["career-counselor"]} roleLabel="Career Counselor" userName={user.full_name}>
      <SchoolFundingRecordsPanel records={records} students={students} />
    </PortalShell>
  );
}
