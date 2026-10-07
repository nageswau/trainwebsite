// tel-021 (DEC-SCOPE-103): the telecaller dashboard and daily activity -- types, endpoints and labels. Every figure is computed by the
// API (services/telecaller_metrics.py, backlog Appendix B); the browser only lays them out.

export type KpiProgress = { kpi: string; achieved: number; target: number | null };
export type DashboardTiles = {
  new_leads: number; calls_today: { done: number; to_do: number }; follow_ups_due: number; hot_leads: number; appointments: number;
  connected: number; not_connected: number; converted: number; overdue: number; daily_target: { achieved: number; target: number | null };
};
export type DashboardAppointment = {
  kind: "counselling" | "bdm"; id: string; code: string; title: string; scheduled_at: string; status: string; lead_id: string | null;
};
export type TelecallerDashboard = {
  day: string; tiles: DashboardTiles; targets: { daily: KpiProgress[]; monthly: KpiProgress[] }; appointments: DashboardAppointment[];
};
export type ActivityCounts = Record<(typeof ACTIVITY)[number]["key"], number>;
export type TelecallerActivity = { day: string; user: { id: string; full_name: string }; counts: ActivityCounts; targets: KpiProgress[] };

export const DASHBOARD_URL = "/api/v1/telecaller/dashboard";
export const ACTIVITY_URL = "/api/v1/telecaller/activity";

// EVID-019 §1, in the source's order (Appendix B B1-B10).
export const TILES: { key: keyof DashboardTiles; label: string; hint: string }[] = [
  { key: "new_leads", label: "New Leads", hint: "Leads received today" },
  { key: "calls_today", label: "Calls Today", hint: "Done / to do" },
  { key: "follow_ups_due", label: "Follow-ups Due", hint: "Scheduled for today" },
  { key: "hot_leads", label: "Hot Leads", hint: "High-potential leads" },
  { key: "appointments", label: "Appointments", hint: "Counselling / BDM today" },
  { key: "connected", label: "Connected", hint: "Successfully contacted" },
  { key: "not_connected", label: "Not Connected", hint: "No answer / busy / switched off" },
  { key: "converted", label: "Converted", hint: "Leads converted today" },
  { key: "overdue", label: "Overdue", hint: "Missed calls / follow-ups" },
  { key: "daily_target", label: "Daily Target", hint: "Calls vs target" },
];

// EVID-019 §14, in the source's order (Appendix B D1-D13).
export const ACTIVITY = [
  { key: "leads_assigned", label: "Total leads assigned" },
  { key: "calls", label: "Total calls" },
  { key: "connected_calls", label: "Connected calls" },
  { key: "not_connected", label: "Not connected" },
  { key: "follow_ups_completed", label: "Follow-ups completed" },
  { key: "follow_ups_pending", label: "Follow-ups pending" },
  { key: "new_appointments", label: "New appointments" },
  { key: "counselor_appointments", label: "Counselor appointments" },
  { key: "bdm_appointments", label: "BDM appointments" },
  { key: "whatsapp_messages", label: "WhatsApp messages" },
  { key: "qualified_leads", label: "Qualified leads" },
  { key: "hot_leads", label: "Hot leads" },
  { key: "converted_leads", label: "Converted leads" },
] as const;

export const APPOINTMENT_KIND: Record<DashboardAppointment["kind"], string> = { counselling: "Counselling", bdm: "BDM meeting" };

/** "65 / 80" -- a missing target reads "not set". */
export const progressText = (achieved: number, target: number | null) => `${achieved} / ${target ?? "not set"}`;

export function tileValue(tiles: DashboardTiles, key: keyof DashboardTiles): string {
  const value = tiles[key];
  if (key === "calls_today") return `${tiles.calls_today.done} / ${tiles.calls_today.to_do}`;
  if (key === "daily_target") return progressText(tiles.daily_target.achieved, tiles.daily_target.target);
  return String(value);
}

/** The `?date=` a page passes on: a well-formed YYYY-MM-DD only (the API rules on the rest, e.g. a future day). */
export const dayParam = (raw: string | undefined) => (raw && /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : undefined);

export function activityUrl(day?: string, userId?: string): string {
  const params = new URLSearchParams();
  if (day) params.set("date", day);
  if (userId) params.set("user_id", userId);
  const query = params.toString();
  return query ? `${ACTIVITY_URL}?${query}` : ACTIVITY_URL;
}

/** A 422 (e.g. a future date) carries the API's sentence; anything else is a generic note. */
export const ACTIVITY_UNAVAILABLE = "Daily activity is unavailable right now.";
export function activityError(e: unknown): string {
  const { status, message } = (e ?? {}) as { status?: number; message?: unknown };
  return status === 422 && typeof message === "string" ? message : ACTIVITY_UNAVAILABLE;
}
