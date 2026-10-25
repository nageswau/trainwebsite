import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import ReminderRules from "@/components/ReminderRules";
import { serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import { REMINDER_RULES_API, type ReminderLogPage, type ReminderRule } from "@/lib/reminderRules";
import type { User } from "@/lib/types";

// ccrm-030 (DEC-SCOPE-269, RM9/RM10): the Overseas Admin configures the counselor reminder rules, runs them now to test with sample
// records (AC 12) and sees the recent firings. Super Admin passes too.
const ADMIN_ROLES = ["overseas_admin", "super_admin"];

export default async function ReminderRulesPage() {
  let user: User, rules: { rules: ReminderRule[] }, log: ReminderLogPage;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (!ADMIN_ROLES.includes(user.role)) return accessDenied(user, "Overseas Administrator role required");
    [rules, log] = await Promise.all([serverApi<{ rules: ReminderRule[] }>(REMINDER_RULES_API), serverApi<ReminderLogPage>(`${REMINDER_RULES_API}/log?limit=50`)]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Workspace</div>
            <h2>Reminder rules</h2>
            <p className="muted">
              Turn lead and application dates into counselor tasks and reminders. Agency partners keep their own deadline reminders; students are
              reminded only on direct applications, through the channels they opted in to.
            </p>
          </div>
        </div>
        <ReminderRules rules={rules.rules} log={log} />
      </div>
    </PortalShell>
  );
}
