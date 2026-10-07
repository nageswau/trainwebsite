import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import TelecallerFollowUpsCard, { DASHBOARD_FOLLOW_UPS } from "@/components/TelecallerFollowUpsCard";
import TelecallerProfileCard from "@/components/TelecallerProfileCard";
import TelecallerTargetsCard from "@/components/TelecallerTargetsCard";
import { serverApi } from "@/lib/api";
import { TELECALLER_NAV, TELECALLER_SIGN_IN } from "@/lib/navigation";
import { teamRoleLabel, type TelecallerMe } from "@/lib/telecaller";
import { FOLLOW_UPS_URL, type FollowUpPage } from "@/lib/telecallerFollowUps";
import type { TargetsInEffect } from "@/lib/telecallerTargets";

// tel-001 (AC3): the telecaller landing page -- a minimal shell; tel-021 fills it in. The API is the gate: any other role, or a
// telecaller without a profile, gets its 403 message here with a link home.
export default async function TelecallerDashboardPage() {
  let me: TelecallerMe;
  try {
    me = await serverApi<TelecallerMe>("/api/v1/telecaller/me");
  } catch (e) {
    return accessUnavailable(e, TELECALLER_SIGN_IN);
  }
  // tel-022 (G4): a failed targets read shows a note in the card, never an error page.
  const [targets, followUps] = await Promise.all([
    serverApi<TargetsInEffect>("/api/v1/telecaller/targets/effective").catch(() => null),
    serverApi<FollowUpPage>(`${FOLLOW_UPS_URL}?view=day&limit=${DASHBOARD_FOLLOW_UPS}`).catch(() => null), // tel-011
  ]);
  return (
    <PortalShell nav={TELECALLER_NAV} roleLabel={teamRoleLabel(me.telecaller_profile.team)} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Dashboard</div>
            <h2>Welcome, {me.full_name}</h2>
            <p className="muted">Your leads, calls and follow-ups will appear here.</p>
          </div>
        </div>
        <TelecallerFollowUpsCard page={followUps} />
        <TelecallerProfileCard me={me} />
        <TelecallerTargetsCard targets={targets} />
      </div>
    </PortalShell>
  );
}
