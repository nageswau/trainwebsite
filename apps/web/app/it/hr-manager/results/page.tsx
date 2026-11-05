import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import ResultApprovalQueue from "@/components/ResultApprovalQueue";
import { serverApi } from "@/lib/api";
import { parseOffset, parseState, queueUrl, type ResultQueue, type ResultSettings, RESULTS_URL } from "@/lib/interviewResults";
import { PORTAL_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// hrc-030 (DEC-SCOPE-409 R11/R13): the approver's interview results. The API decides who reads it (a `results.release` holder; anyone else
// 403, shown as the access card).
export default async function HrManagerResultsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const state = parseState(params.state);
  const offset = parseOffset(params.offset); // QA-02: the list is paged
  let user: User;
  let page: ResultQueue;
  let settings: ResultSettings;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    [page, settings] = await Promise.all([serverApi<ResultQueue>(queueUrl(state, offset)), serverApi<ResultSettings>(`${RESULTS_URL}/settings`)]);
  } catch (e) {
    return accessUnavailable(e, "/it/login");
  }
  const superAdmin = user.role === "super_admin";
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : PORTAL_NAV["it/hr-manager"]} roleLabel={superAdmin ? "Super Administrator" : "HR Manager"} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Recruitment</div>
            <h2>Result approvals</h2>
            <p className="muted">Interview decisions waiting to be published to the candidate. Publishing sends the candidate your message and shows the result in their portal.</p>
          </div>
        </div>
        <ResultApprovalQueue key={`${state}-${offset}`} state={state} page={page} settings={settings} />
      </div>
    </PortalShell>
  );
}
