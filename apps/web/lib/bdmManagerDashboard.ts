import { timeText, tripDateText } from "@/lib/bdmMyDay";
import { SCHOOL_TIME_ZONE } from "@/lib/formatDate";

// bdm-023 (DEC-SCOPE-104): the management dashboard's types and wording. The API computes every figure and names every tile and
// alert; the web owns the links (R9) and the words around the times.
const URL = "/api/v1/bdm/manager/dashboard";

export type DashboardTile = { key: string; label: string; definition: string; value: number };
export type DashboardAlertItem = { id: string; title: string; bdm: { id: string; full_name: string }; at: string; organization_id: string | null };
export type DashboardAlert = {
  key: string; label: string; tone: "danger" | "warning" | "success"; record: "appointment" | "trip" | "task" | "mou" | "daily_report";
  count: number; items: DashboardAlertItem[];
};
export type ManagerDashboard = {
  today: string; month: string; manager: { id: string; full_name: string } | null; tiles: DashboardTile[]; alerts: DashboardAlert[];
};

export const dashboardUrl = (managerId?: string): string => (managerId ? `${URL}?manager_user_id=${encodeURIComponent(managerId)}` : URL);

/** Colour is never the only signal (AC4): each tone has a word. */
export const TONE: Record<DashboardAlert["tone"], { className: string; text: string }> = {
  danger: { className: "status error", text: "Urgent" },
  warning: { className: "status pending", text: "Attention" },
  success: { className: "status", text: "Done" },
};

export function alertHref(alert: DashboardAlert, item: DashboardAlertItem): string {
  switch (alert.record) {
    case "appointment": return `/bdm/manager/appointments/${item.id}`;
    case "trip": return `/bdm/manager/trips/${item.id}`;
    case "daily_report": return `/bdm/manager/daily-reports/${item.id}?date=${item.at}`;
    default: return item.organization_id ? `/bdm/manager/organizations/${item.organization_id}` : "/bdm/manager/follow-ups";
  }
}

const LISTS: Record<string, string> = {
  "AL-1": "/bdm/manager/appointments", "AL-2": "/bdm/manager/approvals", "AL-3": "/bdm/manager/follow-ups", "AL-4": "/bdm/manager/mous",
  "AL-5": "/bdm/manager/appointments", "AL-6": "/bdm/manager/appointments", "AL-7": "/bdm/manager/daily-reports",
};

/** The full list behind an alert. A super_admin decides trips from the admin queue, not a manager's. */
export const alertListHref = (key: string, superAdmin: boolean): string =>
  key === "AL-2" && superAdmin ? "/admin/bdm-travel-approvals" : (LISTS[key] ?? "/bdm/manager/dashboard");

/** "8 Oct" for an instant (its IST day) or a "YYYY-MM-DD" date. */
const dayText = (at: string): string =>
  tripDateText(at.length === 10 ? at : new Date(at).toLocaleDateString("en-CA", { timeZone: SCHOOL_TIME_ZONE }));

export function alertWhen(key: string, at: string): string {
  switch (key) {
    case "AL-1": return `Starts ${dayText(at)}, ${timeText(at)}`;
    case "AL-2": return `Travels ${dayText(at)}`;
    case "AL-3": return `Due ${dayText(at)}`;
    case "AL-4": return `Waiting since ${dayText(at)}`;
    case "AL-5": return `Completed ${timeText(at)}`;
    case "AL-6": return `Started ${dayText(at)}, ${timeText(at)}`;
    default: return `Report for ${dayText(at)}`;
  }
}

export function isManagerDashboard(value: unknown): value is ManagerDashboard {
  const v = value as ManagerDashboard | null;
  return Boolean(v && typeof v === "object" && typeof v.today === "string" && Array.isArray(v.tiles) && Array.isArray(v.alerts));
}
