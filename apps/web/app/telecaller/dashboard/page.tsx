import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import TelecallerProfileCard from "@/components/TelecallerProfileCard";
import { serverApi } from "@/lib/api";
import { TELECALLER_NAV, TELECALLER_SIGN_IN } from "@/lib/navigation";
import { teamRoleLabel, type TelecallerMe } from "@/lib/telecaller";

// tel-001 (AC3): the telecaller landing page -- a minimal shell; tel-021 fills it in. The API is the gate: any other role, or a
// telecaller without a profile, gets its 403 message here with a link home.
export default async function TelecallerDashboardPage() {
  let me: TelecallerMe;
  try {
    me = await serverApi<TelecallerMe>("/api/v1/telecaller/me");
  } catch (e) {
    return accessUnavailable(e, TELECALLER_SIGN_IN);
  }
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
        <TelecallerProfileCard me={me} />
      </div>
    </PortalShell>
  );
}
