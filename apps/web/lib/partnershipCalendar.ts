import { addDays, daysOf, weekStart } from "@/lib/bdmCalendar";
import { isCalendarDate } from "@/lib/formatDate";
import type { ManagerRef } from "@/lib/telecaller";

// upc-011 (DEC-SCOPE-152): the §9 calendar's words, URLs, ranges and placing items on days, plus partnership events. Dates are
// "YYYY-MM-DD" IST calendar dates (bdm-013's helpers do the arithmetic in UTC, so no viewer's zone can shift a day).

// CL1: the eight §9 kinds, in source order and wording. The last six are `partnership_events.kind` (= app/partnership_event_kinds.py).
export const KIND_LABELS: Record<string, string> = {
  university_meeting: "University meeting", university_visit: "University visit", conference: "Conference", education_fair: "Education fair",
  partner_meeting: "Partner meeting", mou_signing: "MoU signing", webinar: "Webinar", university_presentation: "University presentation",
};
export const EVENT_KINDS = ["conference", "education_fair", "partner_meeting", "mou_signing", "webinar", "university_presentation"] as const;
export const EVENT_STATUSES: Record<string, string> = { scheduled: "Scheduled", cancelled: "Cancelled" };
export const EVENT_LIMITS = { title: 200, location: 200, notes: 2000, reason: 1000, employees: 10 } as const;

export type Source = "meeting" | "visit" | "event";
export type ItemRef = { source: Source; id: string; code: string; title: string };
export type Overlap = { employee: ManagerRef; item: ItemRef };
export type CalendarItem = ItemRef & {
  kind: string; starts_on: string; ends_on: string; starts_at: string | null; status: string; university: { id: string; name: string } | null;
  people: ManagerRef[]; overlaps: Overlap[];
};
export type PartnershipCalendarData = {
  date_from: string; date_to: string; today: string; employee: ManagerRef | null; truncated: boolean; items: CalendarItem[];
};
export type PartnershipEvent = {
  id: string; code: string; kind: string; title: string; university: { id: string; name: string } | null; starts_on: string; ends_on: string;
  location: string | null; notes: string | null; status: string; owner: ManagerRef; created_by: ManagerRef; participants: ManagerRef[];
  cancelled_at: string | null; cancel_reason: string | null; overlaps: Overlap[]; permissions: { can_edit: boolean; can_cancel: boolean };
  created_at: string; updated_at: string;
};

export const CALENDAR_URL = "/api/v1/partnership/calendar";
export const CALENDAR_PATH = "/partnership/calendar";
export const EVENTS_URL = "/api/v1/partnership/events";
export const EVENTS_PATH = "/partnership/events";
export const eventUrl = (id: string, action?: string) => `${EVENTS_URL}/${id}${action ? `/${action}` : ""}`;
export const eventPath = (id: string, edit = false) => `${EVENTS_PATH}/${id}${edit ? "/edit" : ""}`;
export const NEW_EVENT_PATH = `${EVENTS_PATH}/new`;
export const EVENT_CREATORS = new Set(["partnership_manager", "partnership_head"]);

// CL13: week (Mon-Sun, every day listed) or month (the calendar month, days with items only).
const VIEWS = ["week", "month"] as const;
export type CalendarView = (typeof VIEWS)[number];
export const parseView = (value: unknown): CalendarView => (VIEWS as readonly unknown[]).includes(value) ? (value as CalendarView) : "week";
export const parseDate = (value: unknown, today: string): string => (typeof value === "string" && isCalendarDate(value) ? value : today);

const monthStart = (iso: string) => `${iso.slice(0, 7)}-01`;
const monthEnd = (iso: string) => addDays(`${addDays(monthStart(iso), 31).slice(0, 7)}-01`, -1);

export function rangeOf(view: CalendarView, date: string): { from: string; to: string } {
  if (view === "month") return { from: monthStart(date), to: monthEnd(date) };
  const from = weekStart(date);
  return { from, to: addDays(from, 6) };
}

/** The date one step before or after (`step` = -1 | 1) in this view. */
export function stepDate(view: CalendarView, date: string, step: -1 | 1): string {
  if (view === "week") return addDays(date, 7 * step);
  return step < 0 ? monthStart(addDays(monthStart(date), -1)) : addDays(monthEnd(date), 1);
}

export const rangeDays = (view: CalendarView, date: string): string[] => {
  const { from, to } = rangeOf(view, date);
  return daysOf(from, to);
};

/** The items on one IST day: a multi-day event appears on each of its days. */
export const itemsOn = (items: CalendarItem[], day: string): CalendarItem[] => items.filter((i) => i.starts_on <= day && day <= i.ends_on);

export function itemHref(item: { source: Source; id: string }): string {
  if (item.source === "meeting") return `/partnership/meetings/${item.id}`;
  if (item.source === "visit") return `/partnership/visits/${item.id}`;
  return eventPath(item.id);
}

export function pageHref(params: { view: CalendarView; date: string; employee?: string }): string {
  const query = new URLSearchParams({ view: params.view, date: params.date });
  if (params.employee) query.set("employee", params.employee);
  return `${CALENDAR_PATH}?${query}`;
}

export function apiPath(from: string, to: string, employee?: string): string {
  const query = new URLSearchParams({ date_from: from, date_to: to });
  if (employee) query.set("user_id", employee);
  return `${CALENDAR_URL}?${query}`;
}

export function isCalendarData(value: unknown): value is PartnershipCalendarData {
  const v = value as PartnershipCalendarData | null;
  return Boolean(v && typeof v === "object" && Array.isArray(v.items) && typeof v.today === "string");
}

/** "Asha Rao is also at VIS-000003 (Oxford, Oxford)". */
export const overlapText = (o: Overlap): string => `${o.employee.full_name} is also at ${o.item.code} (${o.item.title})`;

/** "12 Oct 2026" or "12–14 Oct 2026" / "30 Oct – 2 Nov 2026" for a multi-day event. */
export function datesText(startsOn: string, endsOn: string): string {
  const fmt = (iso: string, o: Intl.DateTimeFormatOptions) => new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", { timeZone: "UTC", ...o });
  const full = { day: "numeric", month: "short", year: "numeric" } as const;
  if (startsOn === endsOn) return fmt(startsOn, full);
  if (startsOn.slice(0, 7) === endsOn.slice(0, 7)) return `${Number(startsOn.slice(8))}–${fmt(endsOn, full)}`;
  if (startsOn.slice(0, 4) === endsOn.slice(0, 4)) return `${fmt(startsOn, { day: "numeric", month: "short" })} – ${fmt(endsOn, full)}`;
  return `${fmt(startsOn, full)} – ${fmt(endsOn, full)}`;
}
