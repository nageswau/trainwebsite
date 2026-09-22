import PortalShell from "@/components/PortalShell";
import SchoolAcademicProgressPanel, { type ProgressRow } from "@/components/SchoolAcademicProgressPanel";
import SchoolAcademicResultsPanel from "@/components/SchoolAcademicResultsPanel";
import SchoolTestPrepLanguagePanel from "@/components/SchoolTestPrepLanguagePanel";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessUnavailable } from "@/components/AccessUnavailable";

type Student = { id: string; full_name: string; school_name: string };
type Result = {
  id: string; school_student_id: string; academic_year: string; term: string; subject: string;
  max_marks: number; marks_obtained: number; percentage: number | null; grade: string | null;
  teacher_remarks: string | null;
  status: string; uploaded_by_user_id: string; verified_by_user_id: string | null; published_by_user_id: string | null;
};
type TestPrepRecord = { id: string; school_student_id: string; test_type: string; mock_scores: string[]; target_score: string | null; actual_score: string | null; status: string };
type LanguageRecord = { id: string; school_student_id: string; language: string; level: string | null; classes_attended: number; assessment_score: string | null; certification_status: string };

// SCH-006: every assigned student's result status at a glance -- who still needs a result
// uploaded, who's Draft, who's Published.
export default async function SchoolAcademicTeamDashboardPage() {
  let user: User;
  let results: Result[];
  let students: Student[];
  let testPrepRecords: TestPrepRecord[];
  let languageRecords: LanguageRecord[];
  let progress: ProgressRow[] | null;
  try {
    [user, results, students, testPrepRecords, languageRecords, progress] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<Result[]>("/api/v1/school/academic-team/results"),
      serverApi<Student[]>("/api/v1/school/portfolio-students"),
      serverApi<TestPrepRecord[]>("/api/v1/school/academic-team/test-prep-records"),
      serverApi<LanguageRecord[]>("/api/v1/school/academic-team/language-records"),
      // Optional summary: a failure here must not hide the upload/results/test-prep workspace.
      serverApi<ProgressRow[]>("/api/v1/school/academic-team/progress").catch(() => null),
    ]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV["academic-team"]} roleLabel="Academic Team" userName={user.full_name}>
      <SchoolAcademicProgressPanel progress={progress} />
      <SchoolAcademicResultsPanel results={results} students={students} currentUserId={user.id} />
      <SchoolTestPrepLanguagePanel testPrepRecords={testPrepRecords} languageRecords={languageRecords} students={students} />
    </PortalShell>
  );
}
