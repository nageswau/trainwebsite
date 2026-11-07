import { accessUnavailable } from "@/components/AccessUnavailable";
import CampusCalendarPage from "@/components/CampusCalendarPage";
import { serverApi } from "@/lib/api";
import { bdmManagerNav, bdmNav } from "@/lib/bdmNav";
import { CAMPUS_SUMMARY_URL } from "@/lib/campusPlacement";
import { BDM_SIGN_IN } from "@/lib/navigation";
import type { User } from "@/lib/types";

type Search = Promise<{ month?: string | string[] }>;

// pob-015 (DEC-SCOPE-426 V8): the college BDMs' campus calendar (their bdm-002 scope; a BDM manager's team). Colleges open on the BDM
// organization page, where the placement and vacancy sections sit.
export default async function BdmCampusCalendarPage({ searchParams }: { searchParams: Search }) {
  const { month } = await searchParams;
  let user: User;
  try {
    [user] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi(CAMPUS_SUMMARY_URL)]);
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  const manager = user.role === "bdm_manager";
  const nav = await (manager ? bdmManagerNav() : bdmNav());
  const orgs = manager ? "/bdm/manager/organizations" : "/bdm/organizations";
  return (
    <CampusCalendarPage month={typeof month === "string" ? month : undefined} nav={nav} roleLabel={manager ? "BDM Manager" : "BDM"} userName={user.full_name}
      basePath="/bdm/campus-calendar" collegePath={(id) => `${orgs}/${encodeURIComponent(id)}`} />
  );
}
