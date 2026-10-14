import Link from "next/link";
import type { ReactNode } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import DiscussionsShell from "@/components/DiscussionsShell";
import ManagementMeetingChain from "@/components/ManagementMeetingChain";
import { ApiError, serverApi } from "@/lib/api";
import { formatDateTimeIn, SCHOOL_TIME_ZONE } from "@/lib/formatDate";
import type { ManagementMe } from "@/lib/management";
import { roleLabel, type DiscussionOptions } from "@/lib/managementDiscussions";
import { KIND_LABEL, MEETINGS_API, MEETINGS_HOME, safeLink, STATUS_LABEL, statusClass, type MeetingDetail } from "@/lib/managementMeetings";

const hasStarted = (startsAt: string) => Date.parse(startsAt) <= Date.now();

// mgmt-029 (MM2-MM10): one meeting -- when and where, who, the agenda, then the chain: minutes → decisions → tasks with their deadlines,
// statuses and the completion roll-up (AC).
export default async function MeetingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let me: ManagementMe;
  let options: DiscussionOptions;
  let meeting: MeetingDetail | null = null;
  try {
    [me, options] = await Promise.all([serverApi<ManagementMe>("/api/v1/management/me"), serverApi<DiscussionOptions>(`${MEETINGS_API}/options`)]);
  } catch (e) {
    if (e instanceof ApiError && e.status >= 500) throw e;
    return accessUnavailable(e, "/admin/login");
  }
  try {
    meeting = await serverApi<MeetingDetail>(`${MEETINGS_API}/${encodeURIComponent(id)}`);
  } catch (e) {
    if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) throw e;
  }
  if (!meeting) {
    return (
      <DiscussionsShell me={me} section="Meetings" title="Meeting not found">
        <p className="empty" role="status">This meeting does not exist. <Link className="kpi-link" href={MEETINGS_HOME}>Back to meetings</Link></p>
      </DiscussionsShell>
    );
  }
  const at = (value: string) => formatDateTimeIn(value, SCHOOL_TIME_ZONE, true);
  const link = safeLink(meeting.meeting_url);
  const rows: [string, ReactNode][] = [
    ["Kind", KIND_LABEL[meeting.kind]],
    ["Date and time", at(meeting.starts_at)],
    ["Mode", meeting.mode],
    ["Location", meeting.location ?? "—"],
    ["Meeting link", link ? <a key="l" className="kpi-link" href={link} target="_blank" rel="noopener noreferrer">{link}</a> : "—"],
    ["Status", <span key="s" className={statusClass(meeting.status)}>{STATUS_LABEL[meeting.status]}</span>],
    ["Participants", meeting.participants.length ? meeting.participants.map((p) => `${p.full_name} (${roleLabel(p.role)})`).join(", ") : "—"],
    ["Scheduled by", `${meeting.created_by?.full_name ?? "—"} · ${at(meeting.created_at)}`],
    ["Last changed by", `${meeting.updated_by?.full_name ?? "—"} · ${at(meeting.updated_at)}`],
  ];
  const actions = (
    <>
      {meeting.status !== "cancelled" && <Link className="btn" href={`${MEETINGS_HOME}/${meeting.id}/edit`}>Edit</Link>}
      <Link className="btn secondary" href={MEETINGS_HOME}>Back to meetings</Link>
    </>
  );
  return (
    <DiscussionsShell me={me} section="Meetings" title={meeting.title} actions={actions}>
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
      <section aria-labelledby="meeting-agenda" className="action-card">
        <h3 id="meeting-agenda">Agenda</h3>
        <p style={{ margin: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{meeting.agenda ?? <span className="muted">None recorded.</span>}</p>
      </section>
      <ManagementMeetingChain meeting={meeting} options={options} started={hasStarted(meeting.starts_at)} />
    </DiscussionsShell>
  );
}
