import PortalShell from "@/components/PortalShell";
import SchoolActivityFeedbackPanel from "@/components/SchoolActivityFeedbackPanel";
import { accessUnavailable } from "@/components/AccessUnavailable";
import type { FeedbackActivity } from "@/lib/activityFeedback";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ENH-018: the coordinator records feedback on each completed Edusphere activity of their own school.
export default async function SchoolCoordinatorFeedbackPage() {
  let user: User;
  let initial: Page<FeedbackActivity>;
  try {
    [user, initial] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Page<FeedbackActivity>>("/api/v1/school/activity-feedback?status=all&limit=25&offset=0")]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.coordinator} roleLabel="School Coordinator" userName={user.full_name}>
      <SchoolActivityFeedbackPanel initial={initial} canSubmit />
    </PortalShell>
  );
}
