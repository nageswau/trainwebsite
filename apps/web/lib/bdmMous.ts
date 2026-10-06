import { type BdmType, PAGE_SIZE } from "@/lib/bdm";
import { ORGS_URL, type OrgPerson } from "@/lib/bdmOrganizations";

// bdm-005 (DEC-SCOPE-074): an organization's MoU. The API owns every rule (dates, Expired, D28, scope); these helpers only shape
// requests and read responses. The status list is the source's, in its order (EVID-016 §10; AC5).
export type MouStatus =
  | "prospect" | "discussion_started" | "proposal_sent" | "under_negotiation" | "draft_shared" | "signed" | "active" | "expired" | "rejected";
export const MOU_STATUSES: { key: MouStatus; label: string }[] = [
  { key: "prospect", label: "Prospect" },
  { key: "discussion_started", label: "Discussion Started" },
  { key: "proposal_sent", label: "Proposal Sent" },
  { key: "under_negotiation", label: "Under Negotiation" },
  { key: "draft_shared", label: "Draft Shared" },
  { key: "signed", label: "Signed" },
  { key: "active", label: "Active" },
  { key: "expired", label: "Expired" },
  { key: "rejected", label: "Rejected" },
];
/** M2: Expired is derived from valid_until, never chosen. */
export const SETTABLE_MOU_STATUSES = MOU_STATUSES.filter((s) => s.key !== "expired");
/** The ladder the card draws; Expired and Rejected are outcomes beside it. */
export const MOU_LADDER = MOU_STATUSES.filter((s) => s.key !== "expired" && s.key !== "rejected");

export type MouPerson = Pick<OrgPerson, "id" | "full_name">;
export type MouRow = {
  id: string; organization: { id: string; code: string; name: string; bdm_type: BdmType }; assigned_bdm: OrgPerson; status: MouStatus;
  status_label: string; status_changed_at: string; signed_on: string | null; valid_until: string | null; reference: string | null;
  has_document: boolean; is_current: boolean;
};
export type Mou = MouRow & {
  proposal_sent_on: string | null; valid_from: string | null; notes: string | null;
  document: { name: string | null; content_type: string; uploaded_at: string } | null; expired_on: string | null; created_by: MouPerson;
  permissions: { can_edit: boolean; can_upload: boolean; can_renew: boolean }; pipeline_on_sign: { key: string; label: string } | null;
  created_at: string; updated_at: string;
};
export type OrgMou = { current: Mou | null; can_start: boolean };
export type MouEvent = {
  id: string; kind: "created" | "status" | "updated" | "document" | "renewed"; from_status: MouStatus | null; from_label: string | null;
  to_status: MouStatus; to_label: string; changed: string[]; actor: MouPerson; created_at: string;
};
export type MouFields = { proposal_sent_on: string; signed_on: string; valid_from: string; valid_until: string; reference: string; notes: string };
export type MousParams = { status?: MouStatus; organization?: string; current?: boolean; offset?: number };

export const MOUS_URL = "/api/v1/bdm/mous";
export const MOU_HISTORY_PAGE = 20;
export const FIELD_LABEL: Record<keyof MouFields | "status" | "document", string> = {
  status: "Status", proposal_sent_on: "Proposal sent date", signed_on: "Signed date", valid_from: "Valid from", valid_until: "Valid until",
  reference: "Reference", notes: "Notes", document: "Document",
};

export const orgMouUrl = (orgId: string) => `${ORGS_URL}/${orgId}/mou`;
export const mouDocumentUrl = (mouId: string) => `${MOUS_URL}/${mouId}/document`;
export const mouHistoryUrl = (mouId: string, offset = 0) => `${MOUS_URL}/${mouId}/history?limit=${MOU_HISTORY_PAGE}&offset=${offset}`;
export const statusLabel = (key: MouStatus) => MOU_STATUSES.find((s) => s.key === key)?.label ?? key;

export function mousQuery(params: MousParams): string {
  const q = new URLSearchParams();
  if (params.status) q.set("status", params.status);
  if (params.organization) q.set("organization", params.organization);
  if (params.current === false) q.set("current", "false");
  q.set("limit", String(PAGE_SIZE));
  q.set("offset", String(params.offset ?? 0));
  return q.toString();
}

export function isMouBody(data: unknown): data is { mou: Mou } {
  const mou = (data as { mou?: { id?: unknown } } | null)?.mou;
  return !!mou && typeof mou.id === "string";
}

export function isOrgMou(data: unknown): data is OrgMou {
  const d = data as Partial<OrgMou> | null;
  return !!d && typeof d === "object" && "current" in d && typeof d.can_start === "boolean";
}

/** The MoU 409s that carry a code (someone changed it, it expired, it exists, the organization is lost): their message, else null. */
export function mouConflict(detail: unknown): string | null {
  const d = detail as { code?: unknown; message?: unknown } | null;
  if (!d || typeof d !== "object" || typeof d.message !== "string") return null;
  if (d.code === "mou_status_changed") return `${d.message}.`;
  return ["mou_expired", "mou_exists", "organization_lost"].includes(String(d.code)) ? d.message : null;
}
