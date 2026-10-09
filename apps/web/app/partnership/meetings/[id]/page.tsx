import Link from "next/link";
import type { ReactNode } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import MeetingActions from "@/components/MeetingActions";
import OverlapNotice from "@/components/OverlapNotice";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import {
  contactText, EVENT_LABELS, LINK_MISSING_TEXT, type Meeting, MEETING_STATUSES, MEETING_TYPES, meetingPath, MEETINGS_PATH, meetingWhen, MODES,
} from "@/lib/meetings";
import { loadMeeting } from "@/lib/meetingsServer";
import { TASKS_PATH } from "@/lib/partnershipTasks";
import type { User } from "@/lib/types";
import { shellFor, universityPath } from "@/lib/universities";
import { dateText } from "@/lib/visits";

// upc-009 (§7): one meeting -- the plan, both sides' participants, the outcome and its follow-ups, the history, and the commands this
// reader may run (the API's `permissions`).
function Facts({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl style={{ display: "grid", gridTemplateColumns: "minmax(120px, max-content) 1fr", gap: "6px 16px", margin: 0 }}>
      {rows.map(([term, value]) => [
        <dt key={`${term}-t`} className="muted">{term}</dt>,
        <dd key={`${term}-d`} style={{ margin: 0, overflowWrap: "anywhere", whiteSpace: "pre-line" }}>{value || "—"}</dd>,
      ])}
    </dl>
  );
}

export default async function MeetingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User, m: Meeting;
  try {
    [user, m] = await Promise.all([serverApi<User>("/api/v1/auth/me"), loadMeeting(id)]);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const status = MEETING_STATUSES[m.status] ?? m.status;
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow"><Link href={MEETINGS_PATH}>Meetings</Link> · {m.code}</div>
            <h2>{MEETING_TYPES[m.meeting_type] ?? m.meeting_type} with {m.university.name}</h2>
            <p className="muted">{meetingWhen(m.starts_at)} IST · {MODES[m.mode] ?? m.mode} · <span className="badge">{status}</span></p>
          </div>
          {m.permissions.can_edit && <Link className="btn secondary" href={meetingPath(m.id, true)}>Edit</Link>}
        </div>
        {m.warnings.includes("link_missing") && <p className="form-warning" role="note">{LINK_MISSING_TEXT}</p>}
        {m.status === "scheduled" && <OverlapNotice overlaps={m.overlaps} />}
        <div className="action-grid">
          {/* QA-02: always rendered, so MeetingActions keeps its confirmation after the re-read removes the last action */}
          <section className="action-card wide" aria-labelledby="meeting-actions">
            <h3 id="meeting-actions">Status: {status}</h3>
            {m.status === "cancelled" && <p style={{ margin: 0, whiteSpace: "pre-line", overflowWrap: "anywhere" }}><strong>Cancelled:</strong> {m.cancel_reason}</p>}
            {m.status === "completed" && m.completed_by && m.completed_at && <p className="muted" style={{ margin: 0 }}>Outcome recorded by {m.completed_by.full_name}, {meetingWhen(m.completed_at)}.</p>}
            {m.status === "scheduled" && !m.permissions.can_edit && <p className="muted" style={{ margin: 0 }}>Only the responsible employee or the person who scheduled it can change this meeting.</p>}
            <MeetingActions meeting={m} />
          </section>
          <section className="action-card wide" aria-labelledby="meeting-plan">
            <h3 id="meeting-plan">Meeting</h3>
            <Facts rows={[
              ["Meeting ID", m.code],
              ["University", <Link key="u" href={universityPath(m.university.id)}>{m.university.name} ({m.university.university_code})</Link>],
              ["Contact person", contactText(m.contact)],
              ["Meeting type", MEETING_TYPES[m.meeting_type] ?? m.meeting_type],
              ["Date and time (IST)", meetingWhen(m.starts_at)],
              ["Online / offline", MODES[m.mode] ?? m.mode],
              ["Location", m.location],
              ["Meeting link", m.meeting_url && <a href={m.meeting_url} target="_blank" rel="noopener noreferrer">{m.meeting_url}</a>],
              ["Participants from EduSphere", m.participants.employees.map((p) => `${p.full_name}${p.active ? "" : " (inactive)"}`).join(", ")],
              ["University participants", m.participants.contacts.map((c) => (c.designation ? `${c.name} (${c.designation})` : c.name)).join("\n")],
              ["Agenda", m.agenda],
              ["Notes", m.notes],
              ["Responsible employee", `${m.responsible.full_name}${m.responsible.active ? "" : " (inactive)"}`],
              ["Scheduled by", m.created_by.full_name],
            ]} />
          </section>
          {m.status === "completed" && (
            <section className="action-card wide" aria-labelledby="meeting-outcome">
              <h3 id="meeting-outcome">Outcome</h3>
              <Facts rows={[
                ["Discussion points", m.discussion_points],
                ["Decisions", m.decisions],
                ["Next action", m.next_action && `${m.next_action} — due ${dateText(m.next_action_due_on)}`],
                ["Next meeting date", m.next_meeting_date && dateText(m.next_meeting_date)],
                ["Recorded by", m.completed_by && m.completed_at ? `${m.completed_by.full_name}, ${meetingWhen(m.completed_at)}` : null],
              ]} />
              {m.follow_ups.length > 0 && (
                <>
                  <h4 style={{ margin: "16px 0 8px" }}>Follow-ups created</h4>
                  <ul className="list-clean" style={{ display: "grid", gap: 6, margin: 0, padding: 0, listStyle: "none" }}>
                    {m.follow_ups.map((f) => (
                      <li key={f.id}>{f.title} · due {dateText(f.due_on)} · {f.assignee.full_name} <span className="badge">{f.status === "open" ? "Open" : f.status === "done" ? "Done" : "Cancelled"}</span></li>
                    ))}
                  </ul>
                  <div className="actions" style={{ marginTop: 8 }}><Link className="btn ghost small" href={TASKS_PATH}>Follow-ups &amp; tasks</Link></div>
                </>
              )}
            </section>
          )}
          <section className="action-card wide" aria-labelledby="meeting-history">
            <h3 id="meeting-history">History</h3>
            <ol className="list-clean" style={{ display: "grid", gap: 8, margin: 0, padding: 0, listStyle: "none" }}>
              {m.events.map((e, i) => (
                <li key={i}>
                  <strong>{EVENT_LABELS[e.event] ?? e.event}</strong>
                  {e.event === "rescheduled" && e.old_starts_at && e.new_starts_at && <span className="muted"> · {meetingWhen(e.old_starts_at)} → {meetingWhen(e.new_starts_at)}</span>}
                  <span className="muted"> · {e.actor.full_name} · {meetingWhen(e.created_at)}</span>
                  {e.reason && <p style={{ margin: "2px 0 0", whiteSpace: "pre-line", overflowWrap: "anywhere" }}>{e.reason}</p>}
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>
    </PortalShell>
  );
}
