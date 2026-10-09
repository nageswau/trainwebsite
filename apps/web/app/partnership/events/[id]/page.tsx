import Link from "next/link";
import type { ReactNode } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import OverlapNotice from "@/components/OverlapNotice";
import PartnershipEventCancel from "@/components/PartnershipEventCancel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { CALENDAR_PATH, datesText, EVENT_STATUSES, eventPath, KIND_LABELS, pageHref, type PartnershipEvent } from "@/lib/partnershipCalendar";
import { loadEvent } from "@/lib/partnershipEventsServer";
import type { User } from "@/lib/types";
import { shellFor, universityPath } from "@/lib/universities";

// upc-011 (§9): one partnership event -- what, when, who, its overlaps with the same people's other plans (AC2), and the commands this
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

const named = (p: { full_name: string; active: boolean }) => `${p.full_name}${p.active ? "" : " (inactive)"}`;

export default async function EventPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User, e: PartnershipEvent;
  try {
    [user, e] = await Promise.all([serverApi<User>("/api/v1/auth/me"), loadEvent(id)]);
  } catch (err) {
    return accessUnavailable(err, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const status = EVENT_STATUSES[e.status] ?? e.status;
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow"><Link href={pageHref({ view: "week", date: e.starts_on })}>Calendar</Link> · {e.code}</div>
            <h2 style={{ overflowWrap: "anywhere" }}>{e.title}</h2>
            <p className="muted">{KIND_LABELS[e.kind] ?? e.kind} · {datesText(e.starts_on, e.ends_on)} · <span className="badge">{status}</span></p>
          </div>
          {e.permissions.can_edit && <Link className="btn secondary" href={eventPath(e.id, true)}>Edit</Link>}
        </div>
        {e.status === "scheduled" && <OverlapNotice overlaps={e.overlaps} />}
        <div className="action-grid">
          <section className="action-card wide" aria-labelledby="event-status">
            <h3 id="event-status">Status: {status}</h3>
            {e.status === "cancelled" && <p style={{ margin: 0, whiteSpace: "pre-line", overflowWrap: "anywhere" }}><strong>Cancelled:</strong> {e.cancel_reason}</p>}
            {e.status === "scheduled" && !e.permissions.can_edit && <p className="muted" style={{ margin: 0 }}>Only the event&apos;s owner or the person who added it can change it.</p>}
            <PartnershipEventCancel event={e} />
          </section>
          <section className="action-card wide" aria-labelledby="event-facts">
            <h3 id="event-facts">Event</h3>
            <Facts rows={[
              ["Event ID", e.code],
              ["Event type", KIND_LABELS[e.kind] ?? e.kind],
              ["Dates", datesText(e.starts_on, e.ends_on)],
              ["University", e.university && <Link key="u" href={universityPath(e.university.id)}>{e.university.name}</Link>],
              ["Location", e.location],
              ["Owner", named(e.owner)],
              ["Other employees", e.participants.map(named).join(", ")],
              ["Notes", e.notes],
              ["Added by", e.created_by.full_name],
            ]} />
          </section>
        </div>
        <p><Link href={CALENDAR_PATH}>Back to the calendar</Link></p>
      </div>
    </PortalShell>
  );
}
