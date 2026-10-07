import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import TelecallerActivityPanel from "@/components/TelecallerActivityPanel";
import TelecallerAppointmentsCard from "@/components/TelecallerAppointmentsCard";
import TelecallerDashboardTiles from "@/components/TelecallerDashboardTiles";
import TelecallerFollowUpsCard, { DASHBOARD_FOLLOW_UPS } from "@/components/TelecallerFollowUpsCard";
import TelecallerProfileCard from "@/components/TelecallerProfileCard";
import TelecallerTargetsCard from "@/components/TelecallerTargetsCard";
import { serverApi } from "@/lib/api";
import { TELECALLER_NAV, TELECALLER_SIGN_IN } from "@/lib/navigation";
import { teamRoleLabel, type TelecallerMe } from "@/lib/telecaller";
import { FOLLOW_UPS_URL, type FollowUpPage } from "@/lib/telecallerFollowUps";
import { DASHBOARD_URL, activityError, activityUrl, dayParam, type TelecallerActivity, type TelecallerDashboard } from "@/lib/telecallerMetrics";
import { istToday, type TargetsInEffect } from "@/lib/telecallerTargets";

// tel-001 (AC3): the telecaller landing page. The API is the gate: any other role, or a telecaller without a profile, gets its 403
// message here with a link home. tel-021: today's tiles, appointments, target progress and the daily activity for `?date=`.
export default async function TelecallerDashboardPage({ searchParams }: { searchParams: Promise<{ date?: string }> }) {
  let me: TelecallerMe;
  try {
    me = await serverApi<TelecallerMe>("/api/v1/telecaller/me");
  } catch (e) {
    return accessUnavailable(e, TELECALLER_SIGN_IN);
  }
  const day = dayParam((await searchParams).date);
  let activityFailure = "";
  // tel-022 (G4): each failed read shows a note in its card, never an error page.
  const [targets, followUps, dashboard, activity] = await Promise.all([
    serverApi<TargetsInEffect>("/api/v1/telecaller/targets/effective").catch(() => null),
    serverApi<FollowUpPage>(`${FOLLOW_UPS_URL}?view=day&limit=${DASHBOARD_FOLLOW_UPS}`).catch(() => null), // tel-011
    serverApi<TelecallerDashboard>(DASHBOARD_URL).catch(() => null),
    serverApi<TelecallerActivity>(activityUrl(day)).catch((e) => {
      activityFailure = activityError(e);
      return null;
    }),
  ]);
  const today = dashboard?.day ?? istToday();
  return (
    <PortalShell nav={TELECALLER_NAV} roleLabel={teamRoleLabel(me.telecaller_profile.team)} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Dashboard</div>
            <h2>Welcome, {me.full_name}</h2>
            <p className="muted">Your figures for today, worked out from your calls, follow-ups and appointments.</p>
          </div>
        </div>
        <TelecallerDashboardTiles tiles={dashboard?.tiles ?? null} />
        <TelecallerFollowUpsCard page={followUps} />
        <TelecallerAppointmentsCard appointments={dashboard?.appointments ?? null} />
        <TelecallerTargetsCard targets={targets} progress={dashboard?.targets ?? null} />
        <TelecallerActivityPanel activity={activity} error={activityFailure} day={day ?? today} today={today} />
        <TelecallerProfileCard me={me} />
      </div>
    </PortalShell>
  );
}
