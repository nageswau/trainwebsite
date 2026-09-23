import PortalShell from "@/components/PortalShell";
import SchoolActivityFeedbackPanel from "@/components/SchoolActivityFeedbackPanel";
import { accessUnavailable } from "@/components/AccessUnavailable";
import type { FeedbackActivity } from "@/lib/activityFeedback";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ENH-018 (D8): the principal reads their school's activity feedback; read-only.
export default async function SchoolPrincipalFeedbackPage() {
  let user: User;
  let initial: Page<FeedbackActivity>;
  try {
    [user, initial] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Page<FeedbackActivity>>("/api/v1/school/activity-feedback?status=all&limit=25&offset=0")]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.principal} roleLabel="Principal" userName={user.full_name}>
      <SchoolActivityFeedbackPanel initial={initial} canSubmit={false} />
    </PortalShell>
  );
}
