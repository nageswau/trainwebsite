import PortalShell from "@/components/PortalShell";
import SchoolActivityFeedbackPanel from "@/components/SchoolActivityFeedbackPanel";
import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import { type FeedbackActivity, isFeedbackFilter } from "@/lib/activityFeedback";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ENH-018 (D8): the principal reads their school's activity feedback; read-only. Principal-only (QA-018-12): a coordinator has their
// own Feedback page and was otherwise shown this one under a "Principal" label. `?status=` keeps the filter in the URL (QA-018-07).
export default async function SchoolPrincipalFeedbackPage({ searchParams }: { searchParams: Promise<{ status?: string | string[] }> }) {
  const { status: rawStatus } = await searchParams;
  const status = isFeedbackFilter(rawStatus) ? rawStatus : "all";
  let user: User;
  let initial: Page<FeedbackActivity>;
  try {
    [user, initial] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Page<FeedbackActivity>>(`/api/v1/school/activity-feedback?status=${status}&limit=25&offset=0`)]);
  } catch (e) {
    return accessUnavailable(e);
  }
  if (user.role !== "school_principal") return accessDenied(user, "Principal role required");
  return (
    <PortalShell nav={SCHOOL_NAV.principal} roleLabel="Principal" userName={user.full_name}>
      <SchoolActivityFeedbackPanel initial={initial} canSubmit={false} initialFilter={status} />
    </PortalShell>
  );
}
