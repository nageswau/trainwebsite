import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import Student360View from "@/components/Student360View";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import { loadStudent360, type Student360 } from "@/lib/student360";
import type { User } from "@/lib/types";

// ENH-013 -- Parent's Student 360° view, linked children only (enforced by the API:
// docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md §6.1/§6.3).
export default async function SchoolParentChild360Page({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ tab?: string }> }) {
  const [{ id }, { tab }] = await Promise.all([params, searchParams]);
  let user: User;
  let data: Student360;
  try {
    [user, data] = await Promise.all([serverApi<User>("/api/v1/auth/me"), loadStudent360(id)]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.parent} roleLabel="Parent" userName={user.full_name}>
      <Student360View data={data} initialTab={tab} backHref={`/school/parent/children/${id}`} backLabel="Back to my child" />
    </PortalShell>
  );
}
