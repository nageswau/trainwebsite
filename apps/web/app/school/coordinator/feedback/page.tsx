import PortalShell from "@/components/PortalShell";
import SchoolActivityFeedbackPanel from "@/components/SchoolActivityFeedbackPanel";
import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import type { FeedbackActivity } from "@/lib/activityFeedback";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ENH-018: the coordinator records feedback on each completed Edusphere activity of their own school. Coordinator-only (QA-018-12):
// the read API also serves the principal, so without this check a principal saw a form they could not submit. `?activity=<id>`
// (the Activities page's per-row link, QA-018-09) narrows the list to that activity; anything that is not a UUID is ignored.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default async function SchoolCoordinatorFeedbackPage({ searchParams }: { searchParams: Promise<{ activity?: string | string[] }> }) {
  const { activity } = await searchParams;
  const focusActivityId = typeof activity === "string" && UUID.test(activity) ? activity : undefined;
  let user: User;
  let initial: Page<FeedbackActivity>;
  try {
    [user, initial] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<Page<FeedbackActivity>>(`/api/v1/school/activity-feedback?status=all&limit=25&offset=0${focusActivityId ? `&activity_id=${focusActivityId}` : ""}`),
    ]);
  } catch (e) {
    return accessUnavailable(e);
  }
  if (user.role !== "school_coordinator") return accessDenied(user, "School Coordinator role required");
  return (
    <PortalShell nav={SCHOOL_NAV.coordinator} roleLabel="School Coordinator" userName={user.full_name}>
      <SchoolActivityFeedbackPanel initial={initial} canSubmit focusActivityId={focusActivityId} />
    </PortalShell>
  );
}
