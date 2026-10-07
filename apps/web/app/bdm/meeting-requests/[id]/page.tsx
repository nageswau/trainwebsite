import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import MeetingRequestDecide from "@/components/MeetingRequestDecide";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { bdmNav } from "@/lib/bdmNav";
import { linkableTrips } from "@/lib/bdmTripChoices";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { type MeetingRequest, requestUrl, STATUS_CLASS, STATUS_LABEL } from "@/lib/meetingRequests";
import { BDM_SIGN_IN } from "@/lib/navigation";

// tel-019 (AC2, AC3): one meeting request -- what the telecaller asked for, and accept / decline while it is pending. A request outside
// the BDM's scope (another module, someone else's, taken from the pool) is the API's 404 here.
export default async function BdmMeetingRequestPage({ params }: { params: Promise<{ id: string }> }) {
  const nav = bdmNav();
  const choices = linkableTrips(); // bdm-011: the Trip choice of the booking form, read alongside (never rejects)
  const { id } = await params;
  let me: BdmMe;
  let request: MeetingRequest;
  try {
    [me, request] = await Promise.all([serverApi<BdmMe>("/api/v1/bdm/me"), serverApi<MeetingRequest>(requestUrl(id))]);
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  const type = me.bdm_profile.bdm_type;
  const rows: [string, React.ReactNode][] = [
    ["Type", request.type_label],
    ["Organization", request.organization_name],
    ["Person", request.person_name],
    ["Phone", <a key="p" href={`tel:${request.contact_phone.replace(/[^\d+]/g, "")}`} style={LINK_STYLE}>{request.contact_phone}</a>],
    ["Email", request.contact_email ?? "—"],
    ["Proposed time (IST)", formatSchoolDateTime(request.proposed_at, true)],
    ["Mode", request.mode],
    ["Meeting link or location", request.location ?? "—"],
    ["Purpose", request.purpose],
    ["Remarks", request.remarks ?? "—"],
    ["Requested by", `${request.requester.full_name} · ${formatSchoolDateTime(request.created_at, true)}`],
    ["For", request.bdm ? request.bdm.full_name : `Any ${BDM_TYPE_LABEL[request.bdm_type]} BDM`],
  ];
  return (
    <PortalShell nav={await nav} roleLabel={`${BDM_TYPE_LABEL[type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Requests</div>
            <h2>
              {request.code} <span className={STATUS_CLASS[request.status]}>{STATUS_LABEL[request.status]}</span>
            </h2>
            <p className="muted"><Link href="/bdm/meeting-requests" style={LINK_STYLE}>Back to requests</Link></p>
          </div>
        </div>
        <section className="action-card wide" aria-label="Request details">
          <dl style={{ display: "grid", gridTemplateColumns: "minmax(9rem, max-content) 1fr", gap: "6px 16px", margin: 0, overflowWrap: "anywhere" }}>
            {rows.map(([label, value]) => (
              <div key={label} style={{ display: "contents" }}>
                <dt className="muted">{label}</dt>
                <dd style={{ margin: 0, whiteSpace: label === "Purpose" || label === "Remarks" ? "pre-wrap" : undefined }}>{value}</dd>
              </div>
            ))}
          </dl>
          {request.appointment && (
            <p style={{ marginBottom: 0 }}>
              Accepted by {request.bdm?.full_name}:{" "}
              <Link href={`/bdm/appointments/${request.appointment.id}`} style={LINK_STYLE}>{request.appointment.code}</Link>{" "}
              · {formatSchoolDateTime(request.appointment.starts_at, true)}
            </p>
          )}
          {request.status === "declined" && (
            <p style={{ marginBottom: 0 }}>Declined by {request.bdm?.full_name}: {request.decline_reason}</p>
          )}
        </section>
        <MeetingRequestDecide request={request} bdmType={type} initialOrganization={null} {...await choices} />
      </div>
    </PortalShell>
  );
}
