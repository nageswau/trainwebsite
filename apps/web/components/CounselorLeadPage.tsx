import { notFound } from "next/navigation";

import { accessUnavailable } from "@/components/AccessUnavailable";
import CounselorLeadDetail from "@/components/CounselorLeadDetail";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { counselorLeadUrl, type CounselorLeadDetail as Detail } from "@/lib/leadHandover";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

/** tel-018 (spec §4): /{it|overseas}/counselor/leads/[id]. The API is the gate and the scope -- a lead not handed to this counselor is
 *  a 404, another role a 403 card. */
export default async function CounselorLeadPage({ division, id }: { division: "it" | "overseas"; id: string }) {
  let user: User;
  let lead: Detail;
  try {
    [user, lead] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Detail>(counselorLeadUrl(id))]);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    return accessUnavailable(e, `/${division}/login`);
  }
  return (
    <PortalShell nav={PORTAL_NAV[`${division}/counselor`] ?? []} roleLabel="Counselor" userName={user.full_name}>
      <div className="portal-content">
        <CounselorLeadDetail initial={lead} />
      </div>
    </PortalShell>
  );
}
