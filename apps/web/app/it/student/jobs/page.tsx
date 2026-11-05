import { accessUnavailable } from "@/components/AccessUnavailable";
import CandidateJobsBoard from "@/components/CandidateJobsBoard";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { apiPath, type JobsPage, parseOffset, parseView } from "@/lib/candidateJobs";
import { PORTAL_NAV } from "@/lib/navigation";
import { type StudentAccess, withLocks } from "@/lib/studentAccess";
import type { User } from "@/lib/types";

const BASE = "/it/student/jobs";

// hrc-027 (DEC-SCOPE-398 J12): the IT student's jobs, the same board as the candidate portal's inside the student shell (with its
// payment-lock badges, as every student page carries).
export default async function StudentJobsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const q = typeof params.q === "string" ? params.q : "";
  let user: User;
  let data: JobsPage;
  let access: StudentAccess | null;
  try {
    [user, data, access] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<JobsPage>(apiPath(parseView(params.view), q, parseOffset(params.offset))),
      serverApi<StudentAccess>("/api/v1/workflows/it/student/access").catch(() => null),
    ]);
  } catch (e) {
    return accessUnavailable(e, "/it/login");
  }
  return (
    <PortalShell nav={withLocks(PORTAL_NAV["it/student"], access)} roleLabel="IT Student" userName={user.full_name} studentCode={user.student_code}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Placement</div>
            <h2>Jobs</h2>
            <p className="muted">Open jobs you can apply to, with the ones that fit your profile first. Track them under Job Applications.</p>
          </div>
        </div>
        <CandidateJobsBoard data={data} base={BASE} profileHref="/it/student/profile" />
      </div>
    </PortalShell>
  );
}
