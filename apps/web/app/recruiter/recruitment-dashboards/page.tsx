import { redirect } from "next/navigation";

import { DASHBOARDS_PATH } from "@/lib/recruitmentDashboards";

// hrc-033: the menu's entry; the funnel is the first board.
export default function RecruitmentDashboardsHome() {
  redirect(`${DASHBOARDS_PATH}/funnel`);
}
