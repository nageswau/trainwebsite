import Link from "next/link";

import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { reasonLabel, type FollowUpPage } from "@/lib/telecallerFollowUps";
import { PRIORITY_LABEL } from "@/lib/telecallerLeads";

export const DASHBOARD_FOLLOW_UPS = 5;

// tel-011 (EVID-019 §7 "CRM should automatically show"): today's first follow-ups on the dashboard, with the day and overdue counts and a
// link to the full list. `null` = the read failed; the rest of the dashboard still renders (tel-022 G4's idiom).
export default function TelecallerFollowUpsCard({ page }: { page: FollowUpPage | null }) {
  return (
    <section className="card" aria-labelledby="my-follow-ups-title" style={{ marginTop: 16 }}>
      <h3 id="my-follow-ups-title">Today&apos;s follow-ups</h3>
      {page === null ? (
        <p className="muted" role="status">Follow-ups are unavailable right now.</p>
      ) : (
        <>
          <p style={{ margin: "4px 0 8px" }}>
            <strong>{page.counts.day}</strong> due today · <strong>{page.counts.overdue}</strong> overdue
          </p>
          {page.items.length === 0 ? (
            <p className="muted">Nothing due today.</p>
          ) : (
            <ul aria-label="Today's follow-ups" style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6 }}>
              {page.items.map((fu) => (
                <li key={fu.id}>
                  <Link href={`/telecaller/leads/${encodeURIComponent(fu.lead.id)}`} style={LINK_STYLE}>{fu.lead.name}</Link>
                  {" · "}{fu.next_action ?? reasonLabel(fu.reason)} · {formatSchoolDateTime(fu.due_at, true)} · {PRIORITY_LABEL[fu.lead.priority] ?? fu.lead.priority}
                  {fu.overdue && <> <span className="badge status error">Overdue</span></>}
                </li>
              ))}
            </ul>
          )}
          <p style={{ margin: "8px 0 0" }}><Link href="/telecaller/follow-ups" style={LINK_STYLE}>View all follow-ups</Link></p>
        </>
      )}
    </section>
  );
}
