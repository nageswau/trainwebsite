import { isPage, type Page } from "@/lib/apiErrors";
import { ORGS_URL, type OrgType } from "@/lib/bdmOrganizations";
import type { PersonRef } from "@/lib/bdmTravel";
import { isCalendarDate } from "@/lib/formatDate";

// bdm-009 (DEC-SCOPE-069): activity types, labels and endpoints for the organization timeline and the activity pages. The API decides
// every rule; `permissions.can_change` only tells the UI whether to offer Edit / Delete.
export const CHANNELS = ["call", "whatsapp", "email", "visit", "meeting", "other"] as const;
export type Channel = (typeof CHANNELS)[number];
export type Direction = "outbound" | "inbound";
export const CHANNEL_LABEL: Record<Channel, string> = { call: "Call", whatsapp: "WhatsApp", email: "Email", visit: "Visit", meeting: "Meeting", other: "Other" };
export const DIRECTION_LABEL: Record<Direction, string> = { outbound: "Outgoing", inbound: "Incoming" };
export const needsDirection = (channel: Channel) => channel === "call" || channel === "whatsapp" || channel === "email";
export const NOTE_MAX = 500;
export const BACKDATE_DAYS = 7; // V4 (the API decides; used in the When hint)
export const TIMELINE_PAGE = 20;
export const DAY_PAGE = 50;

export type Activity = {
  id: string;
  organization: { id: string; code: string; name: string; org_type: OrgType };
  bdm: PersonRef; // bdm-010's shape (spec §12.1 A1)
  contact_id: string | null; contact_name: string | null; contact_removed: boolean;
  channel: Channel; direction: Direction | null; occurred_at: string; note: string | null;
  created_at: string; updated_at: string; permissions: { can_change: boolean };
};
export type DayCounts = { day: string; by_channel: Record<Channel, number>; calls_made: number; organizations_contacted: number };
export type ActivityDayPage = Page<Activity> & { counts: DayCounts };

export const ACTIVITIES_URL = "/api/v1/bdm/activities";
export const TEAM_ACTIVITIES_URL = "/api/v1/bdm/manager/activities";
export const activityUrl = (id: string) => `${ACTIVITIES_URL}/${id}`;
export const orgActivitiesUrl = (orgId: string, offset = 0) => `${ORGS_URL}/${orgId}/activities?limit=${TIMELINE_PAGE}&offset=${offset}`;

export function isActivity(data: unknown): data is Activity {
  const d = data as Partial<Activity> | null;
  return !!d && typeof d.id === "string" && !!d.organization && typeof d.occurred_at === "string";
}

export function isDayPage(data: unknown): data is ActivityDayPage {
  if (!isPage(data)) return false;
  const counts = (data as { counts?: unknown }).counts;
  return !!counts && typeof counts === "object";
}

export function contactText(a: Activity): string | null {
  if (!a.contact_name) return null;
  return a.contact_removed ? `${a.contact_name} (removed)` : a.contact_name;
}

/** The IST day a page shows for a raw `?date=`: an invalid or future day becomes today, with a note the page prints (QA9B-01). */
export function activityDay(raw: string | undefined, today: string): { day: string; note: string | null } {
  if (!raw) return { day: today, note: null };
  if (!isCalendarDate(raw)) return { day: today, note: "That isn't a valid date — showing today." };
  if (raw > today) return { day: today, note: "Dates after today can't be shown — showing today." };
  return { day: raw, note: null };
}

/** The API answers its time and contact rules as one sentence; put each on the field it is about (the bdm-010 dateRuleField idea). */
export function activityRuleField(detail: unknown): Record<string, string> {
  if (typeof detail !== "string") return {};
  if (detail.startsWith("When") || detail.startsWith("Activities can be logged") || detail.startsWith("An activity can only be moved")) return { occurred_at: detail };
  if (detail.startsWith("Choose a contact")) return { contact_id: detail };
  return {};
}

/** A saved activity in a newest-first list: replaced if present, otherwise inserted in time order. */
export function placeNewest(items: Activity[], activity: Activity): Activity[] {
  const rest = items.filter((x) => x.id !== activity.id);
  return [...rest, activity].sort((x, y) => (x.occurred_at === y.occurred_at ? y.id.localeCompare(x.id) : y.occurred_at.localeCompare(x.occurred_at)));
}

/** Newest-first list plus a page read later: rows already shown are not repeated (a write can shift the page boundary). */
export function appendUnique(current: Activity[], incoming: Activity[]): Activity[] {
  return [...current, ...incoming.filter((a) => !current.some((c) => c.id === a.id))];
}

/** The API refused a change as "no longer yours / not today": keep the row, drop its Edit and Delete. */
export function lockActivity(items: Activity[], id: string): Activity[] {
  return items.map((x) => (x.id === id ? { ...x, permissions: { can_change: false } } : x));
}

/** India's calendar date (YYYY-MM-DD) of a moment: the day an activity belongs to. */
export const indiaDate = (value: string | Date) => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(value));
