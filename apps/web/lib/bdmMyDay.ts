import { ORG_TYPE_LABEL, type OrgType } from "@/lib/bdmOrganizations";
import { SCHOOL_TIME_ZONE } from "@/lib/formatDate";

// bdm-014 (DEC-SCOPE-097): My Day's types and its §15 wording. The API computes every figure and names every tile (K2).
export const MY_DAY_URL = "/api/v1/bdm/my-day";

export type MyDayAppointment = {
  id: string; code: string; starts_at: string; duration_minutes: number; appointment_type: string; status: string;
  organization: { id: string; code: string; name: string; org_type: string; archived: boolean };
};
export type MyDayTrip = {
  id: string; code: string; travel_date: string; return_date: string; from_place: string; to_place: string; approval_status: string;
  travel_status: string; appointment_count: number;
};
export type FollowUpGroup = { key: string; count: number }; // an org_type, "mou" or "none"
export type MyDayTile = { key: string; label: string; tracked: boolean; value: number | null; note: string | null };
export type MyDay = {
  today: string; bdm_type: string;
  appointments: { count: number; truncated: boolean; items: MyDayAppointment[] };
  trips: { total: number; items: MyDayTrip[] };
  follow_ups: { total: number; groups: FollowUpGroup[] };
  tiles: MyDayTile[];
};

/** "10:00 AM", in IST whatever the viewer's zone. */
export const timeText = (iso: string): string =>
  new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: SCHOOL_TIME_ZONE });

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "18 Sep" for a "YYYY-MM-DD" calendar date: the source's wording (newer ICU writes "Sept" for en-GB), read in UTC so no zone shifts it. */
export function tripDateText(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}

export const tripAppointmentsText = (n: number): string =>
  n === 0 ? "No appointments scheduled" : `${n} appointment${n === 1 ? "" : "s"} scheduled`;

export function followUpText({ key, count }: FollowUpGroup): string {
  const noun = `follow-up${count === 1 ? "" : "s"}`;
  if (key === "none") return `${count} ${noun} without an organization`;
  const label = key === "mou" ? "MoU" : (ORG_TYPE_LABEL[key as OrgType] ?? key);
  return `${count} ${label} ${noun}`;
}

export function isMyDay(value: unknown): value is MyDay {
  const v = value as MyDay | null;
  return Boolean(v && typeof v === "object" && v.appointments && Array.isArray(v.appointments.items) && v.trips && Array.isArray(v.trips.items)
    && v.follow_ups && Array.isArray(v.follow_ups.groups) && Array.isArray(v.tiles));
}
