import Link from "next/link";

import { BDM_TYPE_LABEL } from "@/lib/bdm";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { type MeetingRequest, REQUEST_STATUSES, type RequestPage, type RequestStatus, STATUS_CLASS, STATUS_LABEL } from "@/lib/meetingRequests";

type Viewer = "telecaller" | "bdm" | "manager";

/** tel-019: the request list every viewer shares -- a status filter, the table and paging, all links (server-rendered, no client state).
 *  `basePath` is the page itself; a BDM's codes open the request (where they accept or decline), and an accepted request links its
 *  appointment for the BDM (the telecaller and the manager see its code and time only). */
export default function MeetingRequestList({ page, basePath, status, viewer, defaultStatus }: {
  page: RequestPage; basePath: string; status: RequestStatus | null; viewer: Viewer; defaultStatus?: RequestStatus;
}) {
  // With a default filter (the BDM inbox opens on Pending), "All" needs its own value in the URL.
  const href = (s: RequestStatus | null, offset = 0) => {
    const q = new URLSearchParams();
    if (s !== (defaultStatus ?? null)) q.set("status", s ?? "all");
    if (offset) q.set("offset", String(offset));
    const text = q.toString();
    return text ? `${basePath}?${text}` : basePath;
  };
  const filters: [RequestStatus | null, string][] = [[null, "All"], ...REQUEST_STATUSES.map((s): [RequestStatus, string] => [s, STATUS_LABEL[s]])];
  const end = page.offset + page.items.length;
  return (
    <section className="action-card wide" aria-label="Meeting requests">
      <nav aria-label="Filter by status" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {filters.map(([s, label]) => (
          <Link key={label} href={href(s)} className={`btn small${s === status ? "" : " secondary"}`} aria-current={s === status ? "page" : undefined}>
            {label}
          </Link>
        ))}
      </nav>
      {page.items.length === 0 ? (
        <p className="muted" role="status">{status ? `No ${STATUS_LABEL[status].toLowerCase()} requests.` : "No meeting requests yet."}</p>
      ) : (
        <div className="table-wrap" role="region" aria-label="Meeting requests" tabIndex={0}>
          <table style={{ overflowWrap: "anywhere" }}>
            <thead>
              <tr>
                <th scope="col">Request</th>
                <th scope="col">Proposed (IST)</th>
                <th scope="col">Organization</th>
                <th scope="col">Type</th>
                <th scope="col">Status</th>
                <th scope="col">{viewer === "telecaller" ? "BDM" : "Requested by"}</th>
              </tr>
            </thead>
            <tbody>{page.items.map((r) => <Row key={r.id} r={r} viewer={viewer} />)}</tbody>
          </table>
        </div>
      )}
      {page.total > page.limit && (
        <nav aria-label="Pages" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <span className="muted">{page.offset + 1}–{end} of {page.total}</span>
          {page.offset > 0 && <Link className="btn secondary small" href={href(status, Math.max(0, page.offset - page.limit))}>Previous</Link>}
          {end < page.total && <Link className="btn secondary small" href={href(status, end)}>Next</Link>}
        </nav>
      )}
    </section>
  );
}

function Row({ r, viewer }: { r: MeetingRequest; viewer: Viewer }) {
  const forBdm = viewer === "bdm";
  return (
    <tr>
      <td style={{ whiteSpace: "nowrap" }}>
        {forBdm ? <Link href={`/bdm/meeting-requests/${r.id}`} style={LINK_STYLE}>{r.code}</Link> : r.code}
      </td>
      <td style={{ minWidth: 140 }}>{formatSchoolDateTime(r.proposed_at, true)}<div className="muted">{r.mode}</div></td>
      <td style={{ minWidth: 140 }}>{r.organization_name}<div className="muted">{r.person_name}</div></td>
      <td>{r.type_label}</td>
      <td style={{ minWidth: 150 }}>
        <span className={STATUS_CLASS[r.status]}>{STATUS_LABEL[r.status]}</span>
        {r.appointment && (
          <div className="muted">
            {forBdm ? <Link href={`/bdm/appointments/${r.appointment.id}`} style={LINK_STYLE}>{r.appointment.code}</Link> : r.appointment.code}
            {" · "}{formatSchoolDateTime(r.appointment.starts_at, true)}
          </div>
        )}
        {r.decline_reason && <div className="muted">Reason: {r.decline_reason}</div>}
      </td>
      <td>
        {viewer === "telecaller" ? (r.bdm?.full_name ?? `Any ${BDM_TYPE_LABEL[r.bdm_type]} BDM`) : r.requester.full_name}
        {viewer === "manager" && <div className="muted">{r.bdm ? `For ${r.bdm.full_name}` : `Any ${BDM_TYPE_LABEL[r.bdm_type]} BDM`}</div>}
      </td>
    </tr>
  );
}
