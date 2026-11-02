// itc-020 (DEC-SCOPE-342): the batch timetable -- weekly slots (IT Admin) and the calendar of dated classes every IT role reads.
// Times are shown in IST: batches run on Asia/Kolkata (the API's default), and live sessions arrive in UTC.

export const TIMETABLE_API = "/api/v1/it/timetable";
export const slotsUrl = (batchId: string) => `/api/v1/it/batches/${batchId}/timetable`;
export const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;
export const ZONE = "Asia/Kolkata";

export type Mode = "online" | "offline";

export type Occurrence = {
  id: string;
  kind: "class" | "live_session";
  slot_id: string | null;
  batch_id: string;
  batch: string;
  program: string;
  date: string;
  starts_at: string;
  ends_at: string | null;
  mode: Mode;
  room: string | null;
  meeting_url: string | null;
  topic: string | null;
  status: "scheduled" | "cancelled";
  cancel_reason: string | null;
};

export type TimetableFeed = { from: string; to: string; can_edit: boolean; items: Occurrence[] };

export type Slot = {
  id: string;
  batch_id: string;
  weekday: number;
  day: string;
  start_time: string;
  end_time: string;
  mode: Mode;
  room: string | null;
  meeting_url: string | null;
  topic: string | null;
};

export type SlotInput = { weekday: number; start_time: string; end_time: string; mode: Mode; room: string; meeting_url: string; topic: string };

export const EMPTY_SLOT: SlotInput = { weekday: 0, start_time: "19:00", end_time: "21:00", mode: "online", room: "", meeting_url: "", topic: "" };

/** Today's date in IST as YYYY-MM-DD. */
export function todayIst(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: ZONE, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** The Monday of the week containing `iso`. */
export function mondayOf(iso: string): string {
  const weekday = (new Date(`${iso}T00:00:00Z`).getUTCDay() + 6) % 7;
  return addDays(iso, -weekday);
}

export function dayLabel(iso: string): string {
  return new Intl.DateTimeFormat("en-IN", { timeZone: "UTC", weekday: "long", day: "numeric", month: "short" }).format(new Date(`${iso}T00:00:00Z`));
}

export function timeLabel(value: string): string {
  return new Intl.DateTimeFormat("en-IN", { timeZone: ZONE, hour: "numeric", minute: "2-digit", hour12: true }).format(new Date(value));
}

export function timeRange(item: Pick<Occurrence, "starts_at" | "ends_at">): string {
  return item.ends_at ? `${timeLabel(item.starts_at)} – ${timeLabel(item.ends_at)}` : timeLabel(item.starts_at);
}

export function byDay(items: Occurrence[]): { date: string; items: Occurrence[] }[] {
  const days = new Map<string, Occurrence[]>();
  for (const item of items) days.set(item.date, [...(days.get(item.date) ?? []), item]);
  return [...days.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([date, list]) => ({ date, items: list }));
}

export function slotBody(input: SlotInput) {
  return { ...input, room: input.room.trim() || null, meeting_url: input.meeting_url.trim() || null, topic: input.topic.trim() || null };
}

export function slotInput(slot: Slot): SlotInput {
  return { weekday: slot.weekday, start_time: slot.start_time, end_time: slot.end_time, mode: slot.mode, room: slot.room ?? "", meeting_url: slot.meeting_url ?? "", topic: slot.topic ?? "" };
}
