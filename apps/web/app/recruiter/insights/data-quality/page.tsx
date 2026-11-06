import { accessUnavailable } from "@/components/AccessUnavailable";
import { DataQualityView, InsightsFrame, insightsShell } from "@/components/RecruitmentInsights";
import { serverApi } from "@/lib/api";
import { RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { type DataQuality, dataQualityUrl, type Drill, drillUrl, parseDrill } from "@/lib/recruitmentInsights";
import type { User } from "@/lib/types";

// hrc-034 (DEC-SCOPE-416 I5): `?figure=` opens what a figure counts; a figure the API does not know ignores the parameter.
export default async function DataQualityPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { figure, offset } = parseDrill(await searchParams);
  try {
    const [user, data] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<DataQuality>(dataQualityUrl)]);
    const drill = data.figures.some((f) => f.key === figure) ? await serverApi<Drill>(drillUrl(figure, offset)) : null;
    const shell = await insightsShell(user);
    return (
      <InsightsFrame current="data-quality" {...shell} userName={user.full_name}>
        <DataQualityView data={data} drill={drill} />
      </InsightsFrame>
    );
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
}
