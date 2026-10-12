import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import DiscussionForm from "@/components/DiscussionForm";
import DiscussionsShell from "@/components/DiscussionsShell";
import { ApiError, serverApi } from "@/lib/api";
import { indiaToday } from "@/lib/bdmTravel";
import type { ManagementMe } from "@/lib/management";
import { DISCUSSIONS_API, DISCUSSIONS_HOME, type DiscussionDetail, type DiscussionOptions } from "@/lib/managementDiscussions";

// mgmt-027 (MD7/MD9): change a discussion. A new responsible person, or a changed decision line, notifies the person responsible.
export default async function EditDiscussionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let me: ManagementMe;
  let options: DiscussionOptions;
  let discussion: DiscussionDetail | null = null;
  try {
    [me, options] = await Promise.all([serverApi<ManagementMe>("/api/v1/management/me"), serverApi<DiscussionOptions>(`${DISCUSSIONS_API}/options`)]);
  } catch (e) {
    if (e instanceof ApiError && e.status >= 500) throw e;
    return accessUnavailable(e, "/admin/login");
  }
  try {
    discussion = await serverApi<DiscussionDetail>(`${DISCUSSIONS_API}/${encodeURIComponent(id)}`);
  } catch (e) {
    if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) throw e;
  }
  if (!discussion) {
    return (
      <DiscussionsShell me={me} title="Discussion not found">
        <p className="empty" role="status">This discussion does not exist. <Link className="kpi-link" href={DISCUSSIONS_HOME}>Back to discussions</Link></p>
      </DiscussionsShell>
    );
  }
  return (
    <DiscussionsShell me={me} title={`Edit: ${discussion.topic}`}>
      <DiscussionForm options={options} today={indiaToday()} discussion={discussion} />
    </DiscussionsShell>
  );
}
