import { accessUnavailable } from "@/components/AccessUnavailable";
import { InsightsFrame, insightsShell, SkillDemandView } from "@/components/RecruitmentInsights";
import { serverApi } from "@/lib/api";
import { RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { parseSkill, type SkillDemand, skillDemandUrl, type Vacancies, vacanciesUrl } from "@/lib/recruitmentInsights";
import type { User } from "@/lib/types";

// hrc-034 (DEC-SCOPE-415 I2): the API decides who reads it; anyone else 403, shown as the access card.
export default async function SkillDemandPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = parseSkill(await searchParams);
  try {
    const [user, data, vacancies] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<SkillDemand>(skillDemandUrl(params)), serverApi<Vacancies>(vacanciesUrl(params))]);
    const shell = await insightsShell(user);
    return (
      <InsightsFrame current="skill-demand" {...shell} userName={user.full_name}>
        <SkillDemandView data={data} vacancies={vacancies} params={params} />
      </InsightsFrame>
    );
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
}
