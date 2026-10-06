import { TYPE_LABEL } from "@/lib/bdmAppointments";
import { isCalendarDate } from "@/lib/formatDate";

// bdm-013 (DEC-SCOPE-078): the calendar's pure helpers -- ranges (K7), placing items on days (AC1), the §5 day headline (K6) and
// item links (K8). Dates are "YYYY-MM-DD" IST calendar dates; arithmetic runs in UTC so no viewer's zone can shift a day.
const CALENDAR_URL = "/api/v1/bdm/calendar";
const VIEWS = ["day", "week"] as const;
export type CalendarView = (typeof VIEWS)[number];

type OrgRef = { id: string; code: string; name: string; archived: boolean };
export type CalendarAppointment = {
  id: string; code: string; day: string; starts_at: string; duration_minutes: number; appointment_type: string; status: string;
  seminar: boolean; organization: OrgRef;
};
export type CalendarTrip = {
  id: string; code: string; travel_date: string; return_date: string; from_place: string; to_place: string; mode: string;
  approval_status: string; travel_status: string;
};
export type CalendarTask = { id: string; kind: string; title: string; due_on: string; status: string; overdue: boolean; organization: OrgRef | null };
export type CalendarData = {
  bdm: { id: string; full_name: string; active: boolean }; date_from: string; date_to: string; today: string; truncated: boolean;
  appointments: CalendarAppointment[]; trips: CalendarTrip[]; tasks: CalendarTask[];
};
export type TripRole = "departs" | "away" | "returns" | "day trip";
type DayItems = { trips: { trip: CalendarTrip; role: TripRole }[]; appointments: CalendarAppointment[]; tasks: CalendarTask[] };

const DAY_MS = 86_400_000;
const utc = (iso: string) => new Date(`${iso}T00:00:00Z`);
const fmt = (iso: string, options: Intl.DateTimeFormatOptions) => utc(iso).toLocaleDateString("en-GB", { timeZone: "UTC", ...options });

export const parseView = (value: unknown): CalendarView => (VIEWS as readonly unknown[]).includes(value) ? (value as CalendarView) : "week";
export const parseDate = (value: unknown, today: string): string => (typeof value === "string" && isCalendarDate(value) ? value : today);
export const addDays = (iso: string, n: number): string => new Date(utc(iso).getTime() + n * DAY_MS).toISOString().slice(0, 10);
export const weekStart = (iso: string): string => addDays(iso, -((utc(iso).getUTCDay() + 6) % 7)); // Monday

export function rangeOf(view: CalendarView, date: string): { from: string; to: string } {
  if (view === "day") return { from: date, to: date };
  const from = weekStart(date);
  return { from, to: addDays(from, 6) };
}

export function daysOf(from: string, to: string): string[] {
  const days: string[] = [];
  for (let d = from; d <= to; d = addDays(d, 1)) days.push(d);
  return days;
}

export const dayTitle = (iso: string): string => fmt(iso, { weekday: "long", day: "numeric", month: "short" }).replace(",", "");

export function rangeTitle(from: string, to: string): string {
  if (from === to) return fmt(from, { weekday: "long", day: "numeric", month: "short", year: "numeric" }).replace(",", "");
  const [fy, fm] = [from.slice(0, 4), from.slice(5, 7)];
  const end = fmt(to, { day: "numeric", month: "short", year: "numeric" });
  if (fy !== to.slice(0, 4)) return `${fmt(from, { day: "numeric", month: "short", year: "numeric" })} – ${end}`;
  if (fm !== to.slice(5, 7)) return `${fmt(from, { day: "numeric", month: "short" })} – ${end}`;
  return `${Number(from.slice(8))}–${end}`;
}

function tripRole(trip: CalendarTrip, day: string): TripRole | null {
  if (day < trip.travel_date || day > trip.return_date) return null;
  if (trip.travel_date === trip.return_date) return "day trip";
  return day === trip.travel_date ? "departs" : day === trip.return_date ? "returns" : "away";
}

export function dayItems(data: CalendarData, day: string): DayItems {
  return {
    trips: data.trips.flatMap((trip) => {
      const role = tripRole(trip, day);
      return role ? [{ trip, role }] : [];
    }),
    appointments: data.appointments.filter((a) => a.day === day),
    tasks: data.tasks.filter((t) => t.due_on === day),
  };
}

export const plural = (label: string): string => (label.endsWith("s") ? label : `${label}s`);

// The most frequent type; a tie goes to the type of the earliest appointment.
function dominantType(appointments: CalendarAppointment[]): string | null {
  const counts = new Map<string, number>();
  for (const a of appointments) counts.set(a.appointment_type, (counts.get(a.appointment_type) ?? 0) + 1);
  const byStart = [...appointments].sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at));
  let best: string | null = null;
  for (const a of byStart) if (best === null || counts.get(a.appointment_type)! > counts.get(best)!) best = a.appointment_type;
  return best;
}

// K6, the §5 line: "Vijayawada – College Meetings", "Return travel", "Follow-ups".
export function headline(data: CalendarData, day: string): string {
  const items = dayItems(data, day);
  const type = dominantType(items.appointments);
  const meetings = type ? plural(TYPE_LABEL[type] ?? type) : null;
  const away = items.trips.find((t) => t.role !== "returns");
  if (away) return meetings ? `${away.trip.to_place} – ${meetings}` : away.role === "away" ? away.trip.to_place : `Travel to ${away.trip.to_place}`;
  if (items.trips.length) return meetings ? `Return travel – ${meetings}` : "Return travel";
  if (meetings) return meetings;
  if (items.tasks.length) return items.tasks.every((t) => t.kind === "task") ? "Tasks" : "Follow-ups";
  return "Nothing planned";
}

// K8. `managerOf` is the BDM whose calendar a manager is reading (null on the BDM's own calendar).
export function itemHref(kind: "appointment" | "trip" | "task", item: { id: string; organization?: OrgRef | null }, managerOf: string | null): string {
  const base = managerOf ? "/bdm/manager" : "/bdm";
  if (kind === "appointment") return `${base}/appointments/${item.id}`;
  if (kind === "trip") return managerOf ? `${base}/trips/${item.id}` : `/bdm/travel/${item.id}`;
  if (item.organization) return `${base}/organizations/${item.organization.id}`;
  return managerOf ? `${base}/follow-ups?bdm=${encodeURIComponent(managerOf)}` : "/bdm/follow-ups";
}

export function pageHref(basePath: string, params: { view: CalendarView; date: string; bdm?: string }): string {
  const query = new URLSearchParams({ view: params.view, date: params.date });
  if (params.bdm) query.set("bdm", params.bdm);
  return `${basePath}?${query}`;
}

export function apiPath(from: string, to: string, bdm?: string): string {
  const query = new URLSearchParams({ date_from: from, date_to: to });
  if (bdm) query.set("bdm_user_id", bdm);
  return `${CALENDAR_URL}?${query}`;
}

export function isCalendarData(value: unknown): value is CalendarData {
  const v = value as CalendarData | null;
  return Boolean(v && typeof v === "object" && Array.isArray(v.appointments) && Array.isArray(v.trips) && Array.isArray(v.tasks) && v.bdm);
}
