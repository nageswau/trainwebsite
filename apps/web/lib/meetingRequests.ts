// tel-019 (DEC-SCOPE-098, API §12S): BDM meeting requests -- a telecaller files one, a BDM of the type accepts it into an appointment or
// declines it with a reason.
import { istInputToIso } from "@/lib/bdmAppointments";
import type { BdmType } from "@/lib/bdm";

export const TEL_REQUESTS_URL = "/api/v1/telecaller/meeting-requests";
export const TEL_REQUEST_OPTIONS_URL = `${TEL_REQUESTS_URL}/options`;
export const BDM_REQUESTS_URL = "/api/v1/bdm/meeting-requests";
export const requestUrl = (id: string) => `${BDM_REQUESTS_URL}/${encodeURIComponent(id)}`;
export const acceptUrl = (id: string) => `${requestUrl(id)}/accept`;
export const declineUrl = (id: string) => `${requestUrl(id)}/decline`;

export type RequestType = "college" | "agent" | "school" | "corporate";
export type RequestStatus = "pending" | "accepted" | "declined";
export const REQUEST_STATUSES: RequestStatus[] = ["pending", "accepted", "declined"];
export const STATUS_LABEL: Record<RequestStatus, string> = { pending: "Pending", accepted: "Accepted", declined: "Declined" };
// Always text in the pill; colour only reinforces it (bdm-006 R-F2).
export const STATUS_CLASS: Record<RequestStatus, string> = { pending: "status pending", accepted: "status", declined: "status error" };
// MR9: the bdm-006 appointment type an accept starts from (every BDM module offers the common types).
export const APPOINTMENT_TYPE_FOR: Record<RequestType, string> = {
  college: "college_meeting", agent: "agent_meeting", school: "school_meeting", corporate: "corporate_meeting",
};

type Person = { id: string; full_name: string };
export type MeetingRequest = {
  id: string; code: string; request_type: RequestType; type_label: string; bdm_type: BdmType; organization_name: string; person_name: string;
  contact_phone: string; contact_email: string | null; proposed_at: string; mode: string; location: string | null; purpose: string;
  remarks: string | null; status: RequestStatus; requester: Person; bdm: Person | null;
  appointment: { id: string; code: string; starts_at: string; status: string } | null;
  decline_reason: string | null; decided_at: string | null; created_at: string;
  permissions: { can_accept: boolean; can_decline: boolean };
};
export type RequestPage = { items: MeetingRequest[]; total: number; limit: number; offset: number };
export type RequestOptions = {
  types: { key: RequestType; label: string; bdm_type: BdmType }[];
  bdms: Record<BdmType, Person[]>;
  modes: string[];
};

export type RequestDraft = {
  request_type: RequestType | ""; bdm_user_id: string; organization_name: string; person_name: string; contact_phone: string;
  contact_email: string; when: string; mode: string; location: string; purpose: string; remarks: string;
};
export const EMPTY_DRAFT: RequestDraft = {
  request_type: "", bdm_user_id: "", organization_name: "", person_name: "", contact_phone: "", contact_email: "", when: "", mode: "In person",
  location: "", purpose: "", remarks: "",
};

/** The API body: the IST input as an ISO time, blank optional text left out (the API stores it as none). */
export function requestBody(draft: RequestDraft): Record<string, string> {
  const body: Record<string, string> = {
    request_type: draft.request_type, organization_name: draft.organization_name.trim(), person_name: draft.person_name.trim(),
    contact_phone: draft.contact_phone.trim(), proposed_at: istInputToIso(draft.when), mode: draft.mode, purpose: draft.purpose.trim(),
  };
  if (draft.bdm_user_id) body.bdm_user_id = draft.bdm_user_id;
  for (const key of ["contact_email", "location", "remarks"] as const) {
    const text = draft[key].trim();
    if (text) body[key] = text;
  }
  return body;
}

/** A list page's `?status=&offset=` -> the status filter (unknown values dropped) and the API query string. */
export function listParams(params: { status?: string; offset?: string }): { status: RequestStatus | null; query: string } {
  const status = REQUEST_STATUSES.find((s) => s === params.status) ?? null;
  const offset = Number.parseInt(params.offset ?? "", 10);
  const q = new URLSearchParams({ limit: "25" });
  if (status) q.set("status", status);
  if (Number.isFinite(offset) && offset > 0) q.set("offset", String(offset));
  return { status, query: q.toString() };
}
