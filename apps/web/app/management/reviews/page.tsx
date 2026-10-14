import { accessUnavailable } from "@/components/AccessUnavailable";
import DiscussionsShell from "@/components/DiscussionsShell";
import ManagementReviewGenerate from "@/components/ManagementReviewGenerate";
import ManagementReviews from "@/components/ManagementReviews";
import { ApiError, serverApi } from "@/lib/api";
import { indiaToday } from "@/lib/bdmTravel";
import type { ManagementMe } from "@/lib/management";
import { REVIEWS_API, type ReviewPage } from "@/lib/managementReviews";

const UNAVAILABLE = "Monthly reviews are unavailable right now. Please try again.";

// mgmt-032 (EVID-017 §32, MR1/MR3/MR4): every month's review and "Generate review". Partners only: the API refuses the super admin and
// the accountant (M13), and the page then shows the access card.
export default async function ManagementReviewsPage() {
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: ReviewPage | null = null;
  let error = "";
  try {
    data = await serverApi<ReviewPage>(REVIEWS_API);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    error = UNAVAILABLE;
  }
  return (
    <DiscussionsShell me={me} section="Monthly business review" title="Monthly business review"
      intro="Each month's review is drafted on the 1st with that month's figures frozen. Add the problems and next month's notes, then finalise it.">
      {data && <ManagementReviewGenerate today={indiaToday()} reviewed={data.items.map((r) => r.month)} />}
      <ManagementReviews data={data} error={error} />
    </DiscussionsShell>
  );
}
