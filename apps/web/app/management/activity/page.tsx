import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementActivity from "@/components/ManagementActivity";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { activityFilters, activityUrl, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementActivityPage, type ManagementMe } from "@/lib/management";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

const UNAVAILABLE = "Management activity is unavailable right now. Please try again.";

// mgmt-002 (EVID-017 §2, DEC-SCOPE-187): the Management Activity page. The API decides which entries the caller's tier may see (403 for
// anyone without a tier); a 422 (bad filters) is shown above the form, which keeps the filters so they can be corrected.
export default async function ManagementActivityPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const filters = activityFilters(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: ManagementActivityPage | null = null;
  let error = "";
  try {
    data = await serverApi<ManagementActivityPage>(activityUrl(filters));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    error = e instanceof ApiError && e.status === 422 ? e.message : UNAVAILABLE;
  }
  return (
    <PortalShell nav={me.role === "super_admin" ? SUPER_ADMIN_NAV : managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">EduSphere management</div>
            <h2>Management activity</h2>
            <p className="muted">Who did what in management: tasks, targets, expenses, investments, financial figures and decisions. You see the kinds your access allows. Times are India time (IST).</p>
          </div>
        </div>
        <ManagementActivity data={data} error={error} filters={filters} />
      </div>
    </PortalShell>
  );
}
