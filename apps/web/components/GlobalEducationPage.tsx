import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import GlobalEducationFunnel from "@/components/GlobalEducationFunnel";
import GlobalEducationStudentTable from "@/components/GlobalEducationStudentTable";
import PortalShell from "@/components/PortalShell";
import SectionUnavailable from "@/components/SectionUnavailable";
import { ApiError, serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { GlobalEducationPipeline, User } from "@/lib/types";

// ENH-017 (SCR-SCH-038): one renderer for the Coordinator and Principal pages -- identical data, each page refusing the other
// role (QA-018-12 pattern). Only digit strings are forwarded from the URL, so a tampered ?grade= shows the unfiltered page
// rather than a 422 error card. A 401/403 is an access problem; any other failure keeps the shell and nav usable.
const ROLES = {
  coordinator: { role: "school_coordinator", label: "School Coordinator", denied: "School Coordinator role required" },
  principal: { role: "school_principal", label: "Principal", denied: "Principal role required" },
} as const;

const digits = (value: string | string[] | undefined) => (typeof value === "string" && /^\d+$/.test(value) ? value : "");

export async function renderGlobalEducationPage(key: keyof typeof ROLES, searchParams: Record<string, string | string[] | undefined>) {
  const { role, label, denied } = ROLES[key];
  const grade = digits(searchParams.grade);
  const offset = digits(searchParams.offset);
  const query = new URLSearchParams();
  if (grade) query.set("grade", grade);
  if (offset) query.set("offset", offset);
  const qs = query.toString();
  const url = `/api/v1/school/global-education/pipeline${qs ? `?${qs}` : ""}`;
  const [me, pipeline] = await Promise.allSettled([serverApi<User>("/api/v1/auth/me"), serverApi<GlobalEducationPipeline>(url)]);
  if (me.status === "rejected") return accessUnavailable(me.reason);
  const user = me.value;
  if (user.role !== role) return accessDenied(user, denied);
  if (pipeline.status === "rejected" && pipeline.reason instanceof ApiError && [401, 403].includes(pipeline.reason.status)) return accessUnavailable(pipeline.reason);
  return (
    <PortalShell nav={SCHOOL_NAV[key]} roleLabel={label} userName={user.full_name}>
      <div className="portal-content pipeline-page">
        <h1>Global education</h1>
        {pipeline.status === "fulfilled" ? (
          <>
            <GlobalEducationFunnel data={pipeline.value} />
            <GlobalEducationStudentTable page={pipeline.value.students} grade={grade} basePath={`/school/${key}/global-education`} />
          </>
        ) : (
          <SectionUnavailable title="Global education pipeline" />
        )}
      </div>
    </PortalShell>
  );
}
