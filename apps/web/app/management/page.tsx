import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementHome from "@/components/ManagementHome";
import ManagementPillars from "@/components/ManagementPillars";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_ROLE_LABEL, managementNavFor, pillarsFor, type ManagementMe } from "@/lib/management";
import { HOME_API, type ManagementHome as Home } from "@/lib/managementHome";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

const TIER_NAMES = { operational: "Operations", finance: "Finance", partner_only: "Partner-only" } as const;
const HOME_UNAVAILABLE = "Today's figures are unavailable right now. Please try again.";

// mgmt-001 (AC3, MG8, MG10): the Management Command Center home. The API decides the caller's tiers (403 for anyone without one);
// the page lists only the pillars those tiers allow. The super admin keeps their own sidebar, as on the other shared pages.
// mgmt-031 (HM1): the operational tier (partner, super_admin) first gets the §31 home; the accountant's page is unchanged. A failed
// home never takes the Command Center down with it.
export default async function ManagementPage() {
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let home: Home | null = null;
  let error = "";
  if (me.tiers.operational) {
    try {
      home = await serverApi<Home>(HOME_API);
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
      error = HOME_UNAVAILABLE;
    }
  }
  const access = (Object.keys(TIER_NAMES) as (keyof typeof TIER_NAMES)[]).filter((tier) => me.tiers[tier]).map((tier) => TIER_NAMES[tier]);
  return (
    <PortalShell nav={me.role === "super_admin" ? SUPER_ADMIN_NAV : managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        {error && <p className="form-error" role="alert">{error}</p>}
        {home && <ManagementHome data={home} userName={me.full_name} />}
        <div className="portal-title">
          <div>
            <div className="eyebrow">EduSphere management</div>
            <h2>Management Command Center</h2>
            <p className="muted">Your access: {access.join(" · ")}. Each area opens here as it is built.</p>
          </div>
        </div>
        <ManagementPillars pillars={pillarsFor(me.tiers)} />
      </div>
    </PortalShell>
  );
}
