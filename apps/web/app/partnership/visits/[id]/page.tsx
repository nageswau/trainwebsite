import Link from "next/link";
import type { ReactNode } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import OverlapNotice from "@/components/OverlapNotice";
import PortalShell from "@/components/PortalShell";
import VisitActions from "@/components/VisitActions";
import { serverApi } from "@/lib/api";
import type { User } from "@/lib/types";
import { shellFor, universityPath } from "@/lib/universities";
import { dateText, EVENT_ACTIONS, statusText, type Visit, VISIT_STATUSES, VISITS_PATH, visitPath } from "@/lib/visits";
import { loadVisit } from "@/lib/visitsServer";

// upc-010 (§8): one visit -- the plan, the people, the history, and the commands this reader may run (the API's `permissions`).
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

const when = (iso: string) => new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" });
const requirement = (required: boolean, notes: string | null) => (required ? `Required${notes ? `\n${notes}` : ""}` : notes ? `Not required\n${notes}` : "Not required");

export default async function VisitPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User, v: Visit;
  try {
    [user, v] = await Promise.all([serverApi<User>("/api/v1/auth/me"), loadVisit(id)]);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow"><Link href={VISITS_PATH}>University Visits</Link> · {v.code}</div>
            <h2>Visit to {v.university.name}</h2>
            <p className="muted">{v.city}, {v.university.country.name} · <span className="badge">{statusText(v)}</span></p>
          </div>
          {v.permissions.can_edit && <Link className="btn secondary" href={visitPath(v.id, true)}>Edit</Link>}
        </div>
        {v.approval_state === "returned" && v.rejection_reason && (
          <p className="notice" role="note" style={{ whiteSpace: "pre-line" }}><strong>Returned for changes:</strong> {v.rejection_reason}</p>
        )}
        {v.status === "closed" && v.close_reason && <p className="notice" role="note" style={{ whiteSpace: "pre-line" }}><strong>Closed:</strong> {v.close_reason}</p>}
        {v.status !== "closed" && <OverlapNotice overlaps={v.overlaps} />}
        <div className="action-grid">
          <section className="action-card wide" aria-labelledby="visit-actions">
            <h3 id="visit-actions">Status: {statusText(v)}</h3>
            <p className="muted" style={{ marginTop: 0 }}>
              Planned → Approved → Travel Booked → Visit Completed → Follow-up → Closed. The partnership head approves; a super admin when the head can&apos;t.
            </p>
            <VisitActions visit={v} />
          </section>
          <section className="action-card wide" aria-labelledby="visit-plan">
            <h3 id="visit-plan">Visit plan</h3>
            <Facts rows={[
              ["University", <Link key="u" href={universityPath(v.university.id)}>{v.university.name} ({v.university.university_code})</Link>],
              ["Country", v.university.country.name],
              ["City", v.city],
              ["Visit purpose", v.purpose],
              ["Partnership manager", `${v.lead.full_name}${v.lead.active ? "" : " (inactive)"}`],
              ["Other EduSphere employees", v.participants.map((p) => p.full_name).join(", ")],
              ["Proposed visit date", dateText(v.proposed_date)],
              ["Confirmed visit date", v.confirmed_date ? dateText(v.confirmed_date) : "Not confirmed yet"],
              ["Travel", requirement(v.travel_required, v.travel_notes)],
              ["Hotel", requirement(v.hotel_required, v.hotel_notes)],
              ["Meeting contacts", v.contacts.map((c) => (c.designation ? `${c.name} (${c.designation})` : c.name)).join("\n")],
              ["Agenda", v.agenda],
              ["Expected outcome", v.expected_outcome],
              ["Follow-up date", v.follow_up_date ? dateText(v.follow_up_date) : "Set when the visit is completed"],
              ["Planned by", v.created_by.full_name],
              ["Decided by", v.decided_by && v.decided_at ? `${v.decided_by.full_name}, ${when(v.decided_at)}` : null],
            ]} />
          </section>
          <section className="action-card wide" aria-labelledby="visit-history">
            <h3 id="visit-history">History</h3>
            {v.events.length === 0 ? <p className="muted">No history yet.</p> : (
              <ol className="list-clean" style={{ display: "grid", gap: 8, margin: 0, padding: 0, listStyle: "none" }}>
                {v.events.map((e, i) => (
                  <li key={i}>
                    <strong>{EVENT_ACTIONS[e.action] ?? e.action}</strong>
                    {e.from_status && e.to_status && e.from_status !== e.to_status && <span className="muted"> · {VISIT_STATUSES[e.from_status]} → {VISIT_STATUSES[e.to_status]}</span>}
                    <span className="muted"> · {e.actor.full_name} · {when(e.created_at)}</span>
                    {e.reason && <p style={{ margin: "2px 0 0", whiteSpace: "pre-line", overflowWrap: "anywhere" }}>{e.reason}</p>}
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      </div>
    </PortalShell>
  );
}
