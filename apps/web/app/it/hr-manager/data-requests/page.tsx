import { accessUnavailable } from "@/components/AccessUnavailable";
import CandidateDataRequestQueue from "@/components/CandidateDataRequestQueue";
import CandidateRetentionCard from "@/components/CandidateRetentionCard";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { DATA_REQUESTS_URL, type DataRequestRow, type Retention, RETENTION_URL } from "@/lib/candidateDataRequests";
import { PORTAL_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// hrc-035 (DEC-SCOPE-396 K7/K8): candidates' deletion requests and the retention rule. The API decides who reads it (a `candidates.erase`
// holder; anyone else 403, shown as the access card).
export default async function HrManagerDataRequestsPage() {
  let user: User;
  let open: { items: DataRequestRow[] };
  let decided: { items: DataRequestRow[] };
  let retention: Retention;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    [open, decided, retention] = await Promise.all([
      serverApi<{ items: DataRequestRow[] }>(`${DATA_REQUESTS_URL}?state=open`),
      serverApi<{ items: DataRequestRow[] }>(`${DATA_REQUESTS_URL}?state=decided`),
      serverApi<Retention>(RETENTION_URL),
    ]);
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
            <h2>Candidate data requests</h2>
            <p className="muted">Candidates who asked for their data to be deleted, and how long inactive candidate data is kept.</p>
          </div>
        </div>
        <div className="grid" style={{ gap: 18 }}>
          <CandidateDataRequestQueue open={open.items} decided={decided.items} />
          <CandidateRetentionCard initial={retention} />
        </div>
      </div>
    </PortalShell>
  );
}
