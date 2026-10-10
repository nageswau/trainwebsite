import type { NotificationItem } from "@/components/SchoolNotificationList";
import { serverApi } from "@/lib/api";
import { withBadge, type NavItem } from "@/lib/navigation";

// upc-015 (DEC-SCOPE-162 AL12-AL14): the §32 Alerts list -- the caller's own agreement-expiry, delayed-milestone and overdue-digest
// alerts. The API is the gate and the scope (recipients only); the kind and page live in the URL.
export type AlertKind = "agreement_expiry" | "milestone_delayed" | "overdue_digest";
export type AlertTab = "all" | AlertKind;
export type AlertItem = NotificationItem & { kind: AlertKind };
export type AlertPage = { items: AlertItem[]; total: number; unread: number; limit: number; offset: number };

export const ALERTS_URL = "/api/v1/partnership/alerts";
export const ALERTS_PATH = "/partnership/alerts";
export const ALERT_READERS = new Set(["partnership_manager", "partnership_head", "super_admin"]);
export const PAGE_SIZE = 25;
export const KIND_TABS: { key: AlertTab; label: string }[] = [
  { key: "all", label: "All alerts" },
  { key: "agreement_expiry", label: "Agreement expiry" },
  { key: "milestone_delayed", label: "Delayed milestones" },
  { key: "overdue_digest", label: "Overdue follow-ups" },
];
const EMPTY: Record<AlertTab, string> = {
  all: "No alerts yet. Agreement expiries (90, 60, 30 and 7 days before), delayed milestones and overdue follow-ups appear here and by email.",
  agreement_expiry: "No agreement expiry alerts. An agreement is flagged 90, 60, 30 and 7 days before it expires.",
  milestone_delayed: "No delayed milestones. A milestone appears here the day after its target date passes without being achieved.",
  overdue_digest: "No overdue follow-ups. When a follow-up or task is past its due date you get one summary each morning.",
};

export function chosenKind(value: string | undefined): AlertTab {
  return KIND_TABS.some((t) => t.key === value) ? (value as AlertTab) : "all";
}

export function alertsHref(kind: AlertTab, offset = 0): string {
  const query = new URLSearchParams();
  if (kind !== "all") query.set("kind", kind);
  if (offset > 0) query.set("offset", String(offset));
  const text = query.toString();
  return text ? `${ALERTS_PATH}?${text}` : ALERTS_PATH;
}

export const emptyText = (kind: AlertTab) => EMPTY[kind];

/** AL14: the unread count on the sidebar's Alerts entry. A hint only: when it can't be read the nav renders without it. */
export async function withAlertBadge(nav: NavItem[]): Promise<NavItem[]> {
  try {
    const data = await serverApi<AlertPage>(`${ALERTS_URL}?limit=1`);
    return withBadge(nav, ALERTS_PATH, typeof data?.unread === "number" ? data.unread : null);
  } catch {
    return nav;
  }
}
