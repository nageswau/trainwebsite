import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PartnershipDashboardTiles from "@/components/PartnershipDashboardTiles";
import PartnershipMenuCard from "@/components/PartnershipMenuCard";
import PartnershipProfileCard from "@/components/PartnershipProfileCard";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { ME_URL, type PartnershipMe } from "@/lib/partnership";
import { withAlertBadge } from "@/lib/partnershipAlerts";
import { DASHBOARD_READERS, DASHBOARD_URL, followupTiles, monthTiles, overviewTiles, type PartnershipDashboard } from "@/lib/partnershipDashboard";
import type { User } from "@/lib/types";
import { shellFor } from "@/lib/universities";

const monthName = (first: string) => new Date(`${first}T00:00:00Z`).toLocaleString("en-IN", { month: "long", year: "numeric", timeZone: "UTC" });

// upc-001 (AC3): the partnership manager's landing page; upc-022 (§22, §20; spec §4) fills in the dashboard: the follow-up bands, the
// Global Partnership Overview (D1-D5) and This Month (D6-D14), each figure linked to its list. Heads (and super_admin) reach it from
// their nav. The API is the gate and the scope; if only the figures fail to load, the rest of the page still renders. upc-015: the unread
// alerts on the sidebar's Alerts entry.
export default async function PartnershipDashboardPage() {
  let user: User;
  let me: PartnershipMe | null = null;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (!DASHBOARD_READERS.has(user.role)) return accessDenied(user, "The partnership dashboard is for partnership managers and heads");
    if (user.role === "partnership_manager") me = await serverApi<PartnershipMe>(ME_URL); // a manager without a profile: its 403 message
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const [figures, shellNav] = await Promise.all([serverApi<PartnershipDashboard>(DASHBOARD_URL).catch(() => null), withAlertBadge(nav)]);
  return (
    <PortalShell nav={shellNav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Dashboard</div>
            <h2>Welcome, {user.full_name}</h2>
            <p className="muted">
              {user.role === "partnership_manager" ? "Your universities" : "Your team's universities"} at a glance: follow-ups due, where every partnership stands
              and this month&apos;s activity. Open any figure to see the list behind it.
            </p>
          </div>
        </div>
        {figures === null ? (
          <p className="muted" role="status">The dashboard figures are unavailable right now. Please refresh in a moment.</p>
        ) : (
          <>
            <PartnershipDashboardTiles id="followups-heading" title="Follow-ups" tiles={followupTiles(figures)} />
            <PartnershipDashboardTiles id="overview-heading" title="Global Partnership Overview" tiles={overviewTiles(figures, user.role)} />
            <PartnershipDashboardTiles id="month-heading" title={`This Month — ${monthName(figures.month.first)}`} tiles={monthTiles(figures)} />
          </>
        )}
        {me && <PartnershipProfileCard me={me} />}
        {me && <PartnershipMenuCard />}
      </div>
    </PortalShell>
  );
}
