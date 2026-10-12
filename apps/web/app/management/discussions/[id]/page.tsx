import Link from "next/link";
import type { ReactNode } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import DiscussionAttachments from "@/components/DiscussionAttachments";
import DiscussionsShell from "@/components/DiscussionsShell";
import { ApiError, serverApi } from "@/lib/api";
import { formatDateTimeIn, SCHOOL_TIME_ZONE } from "@/lib/formatDate";
import type { ManagementMe } from "@/lib/management";
import { DISCUSSIONS_API, DISCUSSIONS_HOME, formatDay, roleLabel, STATUS_LABEL, statusClass, type DiscussionDetail } from "@/lib/managementDiscussions";

// mgmt-027 (MD1-MD10): one discussion -- its 11 fields, attachments, and who recorded and last changed it.
export default async function DiscussionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let me: ManagementMe;
  let discussion: DiscussionDetail | null = null;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  try {
    discussion = await serverApi<DiscussionDetail>(`${DISCUSSIONS_API}/${encodeURIComponent(id)}`);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) throw e;
  }
  if (!discussion) {
    return (
      <DiscussionsShell me={me} title="Discussion not found">
        <p className="empty" role="status">This discussion does not exist. <Link className="kpi-link" href={DISCUSSIONS_HOME}>Back to discussions</Link></p>
      </DiscussionsShell>
    );
  }
  const at = (value: string) => formatDateTimeIn(value, SCHOOL_TIME_ZONE, true);
  const day = (value: string | null) => (value ? formatDay(value) : "—");
  const rows: [string, ReactNode][] = [
    ["Date", formatDay(discussion.discussion_date)],
    ["Department", discussion.department ?? "—"],
    ["Participants", discussion.participants.length ? discussion.participants.map((p) => `${p.full_name} (${roleLabel(p.role)})`).join(", ") : "—"],
    ["Decision", discussion.decision ?? "No decision yet"],
    ["Person responsible", discussion.responsible ? `${discussion.responsible.full_name} (${roleLabel(discussion.responsible.role)})` : "—"],
    ["Deadline", day(discussion.deadline)],
    ["Status", <span key="s" className={statusClass(discussion.status)}>{STATUS_LABEL[discussion.status]}</span>],
    ["Follow-up date", day(discussion.follow_up_date)],
    ["Recorded by", `${discussion.created_by?.full_name ?? "—"} · ${at(discussion.created_at)}`],
    ["Last changed by", `${discussion.updated_by?.full_name ?? "—"} · ${at(discussion.updated_at)}`],
  ];
  const actions = (
    <>
      <Link className="btn" href={`${DISCUSSIONS_HOME}/${discussion.id}/edit`}>Edit</Link>
      <Link className="btn secondary" href={DISCUSSIONS_HOME}>Back to discussions</Link>
    </>
  );
  return (
    <DiscussionsShell me={me} title={discussion.topic} actions={actions}>
      <div className="action-card">
        <dl className="form-grid" style={{ margin: 0 }}>
          {rows.map(([label, value]) => (
            <div key={label} style={{ minWidth: 0, overflowWrap: "anywhere" }}>
              <dt className="muted" style={{ fontSize: 13 }}>{label}</dt>
              <dd style={{ margin: 0, fontWeight: 600 }}>{value}</dd>
            </div>
          ))}
        </dl>
      </div>
      <section aria-labelledby="discussion-points" className="action-card">
        <h3 id="discussion-points">Discussion points</h3>
        <p style={{ margin: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{discussion.points ?? <span className="muted">None recorded.</span>}</p>
        <p className="muted" style={{ fontSize: 13, marginBottom: 0 }}>Management only: the responsible person never sees these notes.</p>
      </section>
      <DiscussionAttachments discussion={discussion} />
    </DiscussionsShell>
  );
}
