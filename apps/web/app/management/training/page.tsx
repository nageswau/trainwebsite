import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementTraining from "@/components/ManagementTraining";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { trainingQuery, trainingUrl, type TrainingDashboard } from "@/lib/managementTraining";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

const UNAVAILABLE = "Training figures are unavailable right now. Please try again.";

// mgmt-017 (EVID-017 §12, spec TR1-TR16): the operational tier (partner, super_admin) reads the training KPIs and every trainer's figures
// for a period. The super admin keeps their own sidebar (MG10); anyone else is refused by the API, shown as the access card.
export default async function ManagementTrainingPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = trainingQuery(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: TrainingDashboard | null = null;
  let error = "";
  try {
    data = await serverApi<TrainingDashboard>(trainingUrl(query));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    error = e instanceof ApiError && e.status === 422 && typeof e.message === "string" && !e.message.startsWith("[object") ? e.message : UNAVAILABLE;
  }
  return (
    <PortalShell nav={me.role === "super_admin" ? SUPER_ADMIN_NAV : managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">
              <Link href={MANAGEMENT_HOME}>Command Center</Link>
            </div>
            <h2>Training dashboard</h2>
          </div>
        </div>
        <ManagementTraining data={data} error={error} query={query} />
      </div>
    </PortalShell>
  );
}
