import { accessUnavailable } from "@/components/AccessUnavailable";
import CandidateJobsBoard from "@/components/CandidateJobsBoard";
import MyResultsCard from "@/components/MyResultsCard";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { apiPath, type JobsPage, parseOffset, parseView } from "@/lib/candidateJobs";
import { CANDIDATE_NAV, CANDIDATE_PORTAL_HOME } from "@/lib/candidatePortal";
import type { User } from "@/lib/types";

const BASE = "/it/careers/portal/jobs";

// hrc-027 (DEC-SCOPE-398 J12): the external candidate's jobs -- recommended, matching their skills, and all open jobs.
export default async function CandidateJobsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const q = typeof params.q === "string" ? params.q : "";
  let user: User;
  let data: JobsPage;
  try {
    [user, data] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<JobsPage>(apiPath(parseView(params.view), q, parseOffset(params.offset)))]);
  } catch (e) {
    return accessUnavailable(e, "/it/login");
  }
  return (
    <PortalShell nav={CANDIDATE_NAV} roleLabel="Candidate" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Candidate portal</div>
            <h2>Jobs</h2>
            <p className="muted">Open jobs you can apply to, with the ones that fit your profile first.</p>
          </div>
        </div>
        <MyResultsCard />{/* hrc-030 (DEC-SCOPE-409 R9) */}
        <CandidateJobsBoard data={data} base={BASE} profileHref={CANDIDATE_PORTAL_HOME} />
      </div>
    </PortalShell>
  );
}
