import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import DiscussionsShell from "@/components/DiscussionsShell";
import ManagementDiscussions from "@/components/ManagementDiscussions";
import { ApiError, serverApi } from "@/lib/api";
import { indiaToday } from "@/lib/bdmTravel";
import type { ManagementMe } from "@/lib/management";
import { DISCUSSIONS_HOME, discussionFilters, discussionsUrl, PENDING_URL, type DiscussionPage } from "@/lib/managementDiscussions";

const UNAVAILABLE = "Discussions are unavailable right now. Please try again.";

// mgmt-027 (EVID-017 §27, MD7/MD12): the discussions list with the Pending decisions panel. The API refuses everyone outside the
// operational tier (the accountant included, M13), and the page then shows the access card.
export default async function ManagementDiscussionsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const filters = discussionFilters(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: DiscussionPage | null = null;
  let pending: DiscussionPage["items"] = [];
  let error = "";
  try {
    [data, { items: pending }] = await Promise.all([serverApi<DiscussionPage>(discussionsUrl(filters)), serverApi<DiscussionPage>(PENDING_URL)]);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    data = null;
    error = UNAVAILABLE;
  }
  return (
    <DiscussionsShell me={me} title="Discussions & decisions" actions={<Link className="btn" href={`${DISCUSSIONS_HOME}/new`}>New discussion</Link>}
      intro="Management discussions and the decisions they reach. A person named responsible for a decision sees only that decision, its deadline and status.">
      <ManagementDiscussions data={data} pending={pending} error={error} filters={filters} today={indiaToday()} />
    </DiscussionsShell>
  );
}
