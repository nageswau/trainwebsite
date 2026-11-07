import { accessUnavailable } from "@/components/AccessUnavailable";
import CampusCalendarPage from "@/components/CampusCalendarPage";
import { serverApi } from "@/lib/api";
import { CAMPUS_SUMMARY_URL } from "@/lib/campusPlacement";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { COLLEGES_PATH } from "@/lib/recruiterColleges";
import type { User } from "@/lib/types";

type Search = Promise<{ month?: string | string[] }>;

// pob-015 (DEC-SCOPE-426 V8): the placement team's campus calendar (?month=YYYY-MM). The API is the gate: a role without college access
// gets its 403 message from the probe read alongside the session (the pob-013 pattern).
export default async function RecruiterCampusCalendarPage({ searchParams }: { searchParams: Search }) {
  const { month } = await searchParams;
  let user: User;
  try {
    [user] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi(CAMPUS_SUMMARY_URL)]);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <CampusCalendarPage month={typeof month === "string" ? month : undefined} nav={nav} roleLabel={roleLabel} userName={user.full_name}
      basePath="/recruiter/campus-calendar" collegePath={(id) => `${COLLEGES_PATH}/${encodeURIComponent(id)}`} />
  );
}
