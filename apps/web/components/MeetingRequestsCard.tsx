import Link from "next/link";

import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { formatSchoolDateTime } from "@/lib/formatDate";
import type { RequestPage } from "@/lib/meetingRequests";

/** tel-019: the BDM's "Requests" inbox on My Day -- how many requests are pending and the next five by proposed time. `null` means the
 *  read failed: My Day still renders, with a link to the inbox. */
export default function MeetingRequestsCard({ page }: { page: RequestPage | null }) {
  return (
    <section className="action-card wide" aria-labelledby="my-day-requests">
      <h3 id="my-day-requests">Meeting requests</h3>
      {page === null ? (
        <p className="muted">Unable to load your meeting requests right now.</p>
      ) : page.total === 0 ? (
        <p className="muted">No pending meeting requests.</p>
      ) : (
        <>
          <p>{page.total === 1 ? "1 pending request" : `${page.total} pending requests`} — accept or decline from the request.</p>
          <ul style={{ margin: 0, paddingLeft: "1.2rem", display: "grid", gap: 4 }}>
            {page.items.map((r) => (
              <li key={r.id}>
                <Link href={`/bdm/meeting-requests/${r.id}`} style={LINK_STYLE}>{r.code}</Link> · {r.type_label} · {r.organization_name} ·{" "}
                {formatSchoolDateTime(r.proposed_at, true)}{r.bdm ? " · for you" : ""}
              </li>
            ))}
          </ul>
        </>
      )}
      <p style={{ marginBottom: 0 }}><Link href="/bdm/meeting-requests" style={LINK_STYLE}>Open requests</Link></p>
    </section>
  );
}
