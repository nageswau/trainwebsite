import type { Mou, MouStatus } from "@/lib/bdmMous";

export const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

export const mou = (status: MouStatus = "prospect", over: Partial<Mou> = {}): Mou => ({
  id: "m1",
  organization: { id: "o1", code: "ORG-000001", name: "St Mary", bdm_type: "college" },
  assigned_bdm: { id: "u1", full_name: "Asha BDM", active: true },
  status,
  status_label: { prospect: "Prospect", proposal_sent: "Proposal Sent", signed: "Signed", active: "Active", expired: "Expired", rejected: "Rejected" }[status as string] ?? status,
  status_changed_at: "2026-10-01T10:00:00Z",
  signed_on: null,
  valid_until: null,
  reference: "MOU-14",
  has_document: false,
  is_current: true,
  proposal_sent_on: null,
  valid_from: null,
  notes: "Met the dean",
  document: null,
  expired_on: null,
  created_by: { id: "u1", full_name: "Asha BDM" },
  permissions: { can_edit: true, can_upload: true, can_renew: false },
  pipeline_on_sign: { key: "mou_signed", label: "MoU Signed" },
  created_at: "2026-10-01T10:00:00Z",
  updated_at: "2026-10-01T10:00:00Z",
  ...over,
});
