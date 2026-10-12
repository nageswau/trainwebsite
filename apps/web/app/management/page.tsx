import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementPillars from "@/components/ManagementPillars";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { MANAGEMENT_ROLE_LABEL, managementNavFor, pillarsFor, type ManagementMe } from "@/lib/management";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

const TIER_NAMES = { operational: "Operations", finance: "Finance", partner_only: "Partner-only" } as const;

// mgmt-001 (AC3, MG8, MG10): the Management Command Center home. The API decides the caller's tiers (403 for anyone without one);
// the page lists only the pillars those tiers allow. The super admin keeps their own sidebar, as on the other shared pages.
export default async function ManagementPage() {
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const access = (Object.keys(TIER_NAMES) as (keyof typeof TIER_NAMES)[]).filter((tier) => me.tiers[tier]).map((tier) => TIER_NAMES[tier]);
  return (
    <PortalShell nav={me.role === "super_admin" ? SUPER_ADMIN_NAV : managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
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
