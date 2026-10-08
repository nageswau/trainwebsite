import { accessUnavailable } from "@/components/AccessUnavailable";
import PartnershipMenuCard from "@/components/PartnershipMenuCard";
import PartnershipProfileCard from "@/components/PartnershipProfileCard";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { PARTNERSHIP_NAV } from "@/lib/navigation";
import { ME_URL, ROLE_LABEL, type PartnershipMe } from "@/lib/partnership";

// upc-001 (AC3): the partnership manager's landing page. The API is the gate: any other role, or a manager without a profile, gets its
// 403 message here with a link home. upc-022 fills in the dashboard itself.
export default async function PartnershipDashboardPage() {
  let me: PartnershipMe;
  try {
    me = await serverApi<PartnershipMe>(ME_URL);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  return (
    <PortalShell nav={PARTNERSHIP_NAV} roleLabel={ROLE_LABEL.manager} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Dashboard</div>
            <h2>Welcome, {me.full_name}</h2>
            <p className="muted">Your University Partnership CRM. Universities, meetings, agreements and targets will appear here as each area opens.</p>
          </div>
        </div>
        <PartnershipProfileCard me={me} />
        <PartnershipMenuCard />
      </div>
    </PortalShell>
  );
}
