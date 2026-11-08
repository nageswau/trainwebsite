// pob-024 (DEC-SCOPE-432): the placement closure record -- types, endpoints and labels. The API decides scope, every rule (dates, the
// draft's state, the commercial gate) and what the viewer may do (`permissions`); the UI only offers what it allows.
import { isPage, type Page } from "@/lib/apiErrors";
import type { Invoice } from "@/lib/recruiterRevenue";

export const PLACEMENTS_URL = "/api/v1/recruiter/placements";
export const PLACEMENTS_PATH = "/recruiter/placements";
export const PLACEMENTS_LIMIT = 25;
export const placementUrl = (id: string, tail = "") => `${PLACEMENTS_URL}/${encodeURIComponent(id)}${tail ? `/${tail}` : ""}`;
export const placementPath = (id: string) => `${PLACEMENTS_PATH}/${encodeURIComponent(id)}`;

export type PlacementView = "pending" | "joined" | "did_not_join" | "invoice_drafts";
export const PLACEMENT_TABS: [PlacementView, string][] = [
  ["pending", "Joining pending"], ["joined", "Joined"], ["invoice_drafts", "Invoice drafts"], ["did_not_join", "Did not join"],
];
export const isPlacementView = (v: string | null): v is PlacementView => PLACEMENT_TABS.some(([key]) => key === v);
export const placementsUrl = (view: PlacementView, offset: number) =>
  `${PLACEMENTS_URL}?${new URLSearchParams({ view, limit: String(PLACEMENTS_LIMIT), ...(offset ? { offset: String(offset) } : {}) })}`;

export const VIA_OPTIONS: [string, string][] = [["call", "Call"], ["email", "Email"], ["whatsapp", "WhatsApp"], ["in_person", "In person"], ["other", "Other"]];

type Ref = { id: string; code: string; name?: string; title?: string };
type Person = { id: string; full_name: string; active: boolean } | null;
export type Confirmation = { by: string | null; on: string; via: string; via_label: string } | null;

export type PlacementItem = {
  id: string; status: string; status_label: string; role: string; joined_on: string | null;
  candidate: Ref; requirement: Ref; company: { id: string; name: string };
  invoice_status: string | null; invoice_status_label: string | null;
};
export type PlacementListPage = Page<PlacementItem> & { counts: Record<PlacementView, number> };
export const isPlacementListPage = (d: unknown): d is PlacementListPage => isPage(d) && typeof (d as { counts?: unknown }).counts === "object";

export type PlacementInvoice = {
  status: "none" | "draft" | "issued" | "discarded"; status_label: string; draft_amount: string | null; draft_due_date: string | null;
  draft_created_at: string | null; discard_reason: string | null; invoice: Invoice | null;
};
// pob-026 (DEC-SCOPE-435 S10): one side's satisfaction survey; null until the daily sweep has handled it (S1).
export const SURVEY_AFTER_DAYS = 30;
export const surveyUrl = (token: string) => `/api/v1/public/placement-surveys/${encodeURIComponent(token)}`;
export type Survey = {
  status: "sent" | "responded" | "skipped"; status_label: string; sent_at: string | null; resent_at: string | null; responded_at: string | null;
  rating: number | null; comment: string | null; skip_reason: string | null; skip_reason_label: string | null;
} | null;
export type Placement = {
  id: string; status: string; status_label: string; role: string; offer_id: string;
  application: { id: string; code: string }; candidate: Ref; requirement: Ref; company: { id: string; name: string }; vendor: { id: string; name: string } | null;
  recruiter: Person; po_owner: Person; source: string | null; package: { compensation: string; currency: string } | null;
  joining: { expected_joining_date: string | null; actual_joining_date: string | null };
  candidate_confirmation: Confirmation; client_confirmation: Confirmation;
  commercials: { expected_fee: string | null; invoice: PlacementInvoice } | null;
  satisfaction?: { client: Survey; candidate: Survey };
  permissions: { can_edit: boolean; can_change_owner: boolean; can_invoice: boolean };
};
export const placementOf = (data: unknown): Placement | null => {
  const p = (data as { placement?: Placement } | null)?.placement;
  return p && typeof p === "object" && typeof p.id === "string" ? p : null;
};
