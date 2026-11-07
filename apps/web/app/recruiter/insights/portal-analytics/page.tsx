import { accessUnavailable } from "@/components/AccessUnavailable";
import { InsightsFrame, insightsShell, PeriodForm, PortalAnalyticsView } from "@/components/RecruitmentInsights";
import { ApiError, serverApi } from "@/lib/api";
import { RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { parsePeriod, type PortalAnalytics, portalAnalyticsUrl } from "@/lib/recruitmentInsights";
import type { User } from "@/lib/types";

// hrc-034 (DEC-SCOPE-416 I3): a period the API refuses (422) stays on the page with its reason; anything else is the access card.
export default async function PortalAnalyticsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const period = parsePeriod(await searchParams);
  try {
    const user = await serverApi<User>("/api/v1/auth/me");
    let data: PortalAnalytics | null = null;
    let refused = "";
    try {
      data = await serverApi<PortalAnalytics>(portalAnalyticsUrl(period));
    } catch (e) {
      if (!(e instanceof ApiError) || e.status !== 422) throw e;
      refused = e.message;
    }
    const shell = await insightsShell(user);
    return (
      <InsightsFrame current="portal-analytics" {...shell} userName={user.full_name}>
        <PeriodForm from={data?.from ?? period.from} to={data?.to ?? period.to} />
        {refused && <p className="form-error" role="alert">{refused}</p>}
        {data && <PortalAnalyticsView data={data} />}
      </InsightsFrame>
    );
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
}
