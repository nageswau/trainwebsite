import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PoDailyPlan from "@/components/PoDailyPlan";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { addDays, dayLabel, type Plan, PLAN_URL } from "@/lib/recruiterPoWork";
import { istToday } from "@/lib/telecallerTargets";
import type { User } from "@/lib/types";

// pob-009 T6: today's plan, picked from due follow-ups and this month's target companies; earlier days are read only.
export default async function DailyPlanPage({ searchParams }: { searchParams: Promise<{ date?: string }> }) {
  const today = istToday();
  const raw = (await searchParams).date;
  const day = raw && /^\d{4}-\d{2}-\d{2}$/.test(raw) && raw <= today ? raw : today;
  let user: User, plan: Plan;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "placement_team") return accessDenied(user, "This page is for placement officers.");
    plan = await serverApi<Plan>(`${PLAN_URL}?date=${day}`);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Daily plan</div>
            <h2>{day === today ? "Today's plan" : "Plan"} — {dayLabel(day)}</h2>
            <p className="muted">
              <a href={`/recruiter/daily-plan?date=${addDays(day, -1)}`}>Previous day</a>
              {day !== today && <> · <a href="/recruiter/daily-plan">Today</a></>}
              {" · "}<a href={`/recruiter/activity-reports?period=daily&start=${day}`}>This day&apos;s report</a>
            </p>
          </div>
        </div>
        <PoDailyPlan plan={plan} />
      </div>
    </PortalShell>
  );
}
