import { detailMessage } from "@/lib/apiErrors";
import type { AppointmentStatus } from "@/lib/bdmAppointments";

// bdm-010 (DEC-SCOPE-063): trip types, labels and endpoints shared by the BDM, manager and admin travel screens.
export type TripMode = "flight" | "train" | "bus" | "car" | "cab" | "local";
export type ApprovalStatus = "draft" | "submitted" | "approved" | "rejected";
export type TravelStatus = "planned" | "in_progress" | "completed" | "cancelled";
export type ExpenseCategory = "travel" | "stay" | "food" | "local" | "other";
export type PersonRef = { id: string; full_name: string };
export type TripExpense = { id: string; category: ExpenseCategory; amount: string; expense_date: string; note: string | null };
export type TripRow = {
  id: string; code: string; bdm: PersonRef; travel_date: string; return_date: string; from_place: string; to_place: string; mode: TripMode;
  accommodation_required: boolean; estimated_cost: string; actual_cost: string; currency: "INR"; approval_status: ApprovalStatus;
  travel_status: TravelStatus; submitted_at: string | null;
};
// bdm-011 (DEC-SCOPE-085): the appointments linked to a trip and the figures computed from them. A null figure has nothing to be
// computed from (no estimate given, nothing completed); `actual_revenue` is always null for now -- not tracked (D17).
export type ItineraryItem = {
  id: string; code: string; starts_at: string; duration_minutes: number; appointment_type: string; status: AppointmentStatus;
  organization: { id: string; name: string }; expected_leads: number | null; expected_revenue: string | null;
};
export type TripMetrics = {
  meetings_planned: number; meetings_completed: number; estimated_cost: string; actual_cost: string; cost_per_completed_meeting: string | null;
  expected_leads: number | null; expected_revenue: string | null; actual_leads: number; actual_revenue: string | null;
};
export type Trip = TripRow & {
  itinerary: ItineraryItem[]; metrics: TripMetrics;
  purpose: string; remarks: string | null; rejection_reason: string | null; decided_by: PersonRef | null; decided_at: string | null;
  completed_at: string | null; cancelled_at: string | null; expenses: TripExpense[];
  can_edit: boolean; can_submit: boolean; can_withdraw: boolean; can_start: boolean; can_complete: boolean; can_cancel: boolean;
  can_add_expense: boolean; can_decide: boolean;
};

export const MODE_LABEL: Record<TripMode, string> = { flight: "Flight", train: "Train", bus: "Bus", car: "Car", cab: "Cab", local: "Local travel" };
export const APPROVAL_LABEL: Record<ApprovalStatus, string> = { draft: "Draft", submitted: "Submitted", approved: "Approved", rejected: "Rejected" };
export const TRAVEL_LABEL: Record<TravelStatus, string> = { planned: "Planned", in_progress: "In progress", completed: "Completed", cancelled: "Cancelled" };
export const CATEGORY_LABEL: Record<ExpenseCategory, string> = { travel: "Travel", stay: "Stay", food: "Food", local: "Local", other: "Other" };

export const TRIPS_URL = "/api/v1/bdm/trips";
export const TEAM_TRIPS_URL = "/api/v1/bdm/manager/trips";
/** QA10-04: a trip link is a UUID; anything else is "Trip not found" before the API is asked (it would answer 422). */
export const isUuid = (id: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
export const tripUrl = (id: string) => `${TRIPS_URL}/${id}`;
export const teamTripUrl = (id: string) => `${TEAM_TRIPS_URL}/${id}`;
/** bdm-011: the page paths for one trip, as its BDM ("owner") or their manager sees it. The travel reminder (bdm-012) deep-links to
 * the trip page's sections: #trip-appointments (View Appointments), #trip-costs (View Expenses), #trip-remarks (Add Remarks). */
export const tripPagePath = (view: "owner" | "manager", id: string) => (view === "owner" ? `/bdm/travel/${id}` : `/bdm/manager/trips/${id}`);
export const appointmentPagePath = (view: "owner" | "manager", id: string) =>
  view === "owner" ? `/bdm/appointments/${id}` : `/bdm/manager/appointments/${id}`;
const IST_TIME = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "numeric", minute: "2-digit", hour12: true });
const IST_DAY = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short" });
/** An itinerary row's time in India ("10:00 am"); with its day ("18 Sep, 10:00 am") when the trip spans several days. */
export const itineraryWhen = (iso: string, withDay: boolean) =>
  withDay ? `${IST_DAY.format(new Date(iso))}, ${IST_TIME.format(new Date(iso))}` : IST_TIME.format(new Date(iso));
export const PAST_DAYS = 30;
/** Rupees with up to 2 decimals (the API's TRIP_AMOUNT_FORMAT); the API decides. */
export const AMOUNT_PATTERN = /^\d+(\.\d{1,2})?$/;

export { formatInr } from "@/lib/agentApplications"; // one rupee formatter (AGN-011)

export const MAX_SPAN_DAYS = 30; // return - travel <= 30, i.e. at most 31 days (T14)
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
/** QA10-08: YYYY-MM-DD with a 4-digit year (Chrome lets a year run to 6 digits) and a real calendar day. */
export const isIsoDate = (value: string) => ISO_DATE.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`));
export function addDays(day: string, days: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** QA10-07: the API answers its T14 date rules as a sentence; put each on the field it is about. */
export function dateRuleField(detail: unknown): Record<string, string> {
  if (typeof detail !== "string") return {};
  if (detail.startsWith("Travel date")) return { travel_date: detail };
  if (detail.startsWith("Return date") || detail.startsWith("A trip can last")) return { return_date: detail };
  return {};
}

/** T14: the earliest travel date the API accepts, from today's India date (YYYY-MM-DD). */
export function travelDateBounds(today: string): { min: string } {
  return { min: addDays(today, -PAST_DAYS) };
}

/** §12.2 F3: a FastAPI 422 list mapped to its fields, so each message sits next to its input. */
export function fieldErrors(detail: unknown): Record<string, string> {
  if (!Array.isArray(detail)) return {};
  const out: Record<string, string> = {};
  for (const item of detail as { loc?: unknown[]; msg?: string }[]) {
    const field = item.loc && item.loc.length > 1 ? String(item.loc[item.loc.length - 1]) : "";
    if (field && !out[field]) out[field] = detailMessage([item]); // the shared 422 wording (drops "Value error, ")
  }
  return out;
}

/** India's calendar date, for the T14 hints (the API decides). */
export const indiaToday = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
