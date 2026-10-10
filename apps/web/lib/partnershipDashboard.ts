import { expectedHref, weightedText } from "@/lib/partnershipExpected";

// upc-022 (DEC-SCOPE-167, §22 + §20): the partnership manager dashboard -- Appendix B D1-D14 and the follow-up bands. The API computes
// every figure for the caller's scope; this file only names the tiles and the list each one opens (DB16: the closest existing filter).
export type PartnershipDashboard = {
  today: string;
  month: { first: string; last: string };
  overview: { total: number; partners: number; in_progress: number; targets: number; at_risk: number; lost: number };
  this_month: {
    contacted: number; meetings: number; visits: number; proposals: number; mous_negotiating: number; mous_signed: number; activated: number;
    expected_count: number; expected_weighted: number;
  };
  followups: { overdue: number; today: number; tomorrow: number; upcoming: number };
};
export type DashboardTile = { key: string; label: string; icon?: string; value: number; href: string; note?: string };

export const DASHBOARD_URL = "/api/v1/partnership/dashboard";
export const DASHBOARD_READERS = new Set(["partnership_manager", "partnership_head", "super_admin"]);

const tasks = (band: string) => `/partnership/tasks?band=${band}`;

/** A manager's university list opens on their own universities (the dashboard's scope); a head or super_admin reads the whole list. */
function universities(role: string, filters: Record<string, string> = {}): string {
  const query = new URLSearchParams(role === "partnership_manager" ? { ...filters, manager: "me" } : filters).toString();
  return query ? `/partnership/universities?${query}` : "/partnership/universities";
}

export function followupTiles(d: PartnershipDashboard): DashboardTile[] {
  const f = d.followups;
  return [
    { key: "overdue", icon: "🔴", label: "Overdue", value: f.overdue, href: tasks("overdue") },
    { key: "today", icon: "🟠", label: "Due Today", value: f.today, href: tasks("today") },
    { key: "tomorrow", icon: "🟡", label: "Due Tomorrow", value: f.tomorrow, href: tasks("tomorrow") },
    { key: "upcoming", icon: "🟢", label: "Upcoming", value: f.upcoming, href: tasks("upcoming") },
  ];
}

export function overviewTiles(d: PartnershipDashboard, role: string): DashboardTile[] {
  const o = d.overview;
  return [
    { key: "total", label: "Total Universities", value: o.total, href: universities(role), note: o.lost > 0 ? `Includes ${o.lost} lost / closed` : undefined },
    { key: "partners", icon: "🟢", label: "Active Partners", value: o.partners, href: "/partnership/pipeline?column=active_partners" },
    { key: "in_progress", icon: "🟡", label: "Partnership in Progress", value: o.in_progress, href: "/partnership/pipeline" },
    { key: "targets", icon: "🔵", label: "Target Universities", value: o.targets, href: "/partnership/pipeline?column=target" },
    { key: "at_risk", icon: "🔴", label: "At Risk", value: o.at_risk, href: universities(role, { relationship_strength: "at_risk" }) },
  ];
}

export function monthTiles(d: PartnershipDashboard): DashboardTile[] {
  const m = d.this_month;
  return [
    { key: "contacted", label: "New universities contacted", value: m.contacted, href: "/partnership/pipeline?column=contacted" },
    { key: "meetings", label: "Meetings", value: m.meetings, href: "/partnership/meetings?view=completed", note: "Completed" },
    { key: "visits", label: "University visits", value: m.visits, href: "/partnership/visits?status=visit_completed", note: "Completed" },
    { key: "proposals", label: "Proposals sent", value: m.proposals, href: "/partnership/pipeline?column=proposal_sent" },
    { key: "mous_negotiating", label: "MoUs under negotiation", value: m.mous_negotiating, href: "/partnership/agreements", note: "Sent, under review or in negotiation now" },
    { key: "mous_signed", label: "MoUs signed", value: m.mous_signed, href: "/partnership/agreements?status=signed" },
    { key: "activated", label: "New partnerships activated", value: m.activated, href: "/partnership/pipeline?column=signed" },
    { key: "expected", label: "Expected partnerships", value: m.expected_count, href: expectedHref("this_month"), note: `Weighted forecast: ${weightedText(m.expected_weighted)}` },
    { key: "overdue_followups", label: "Overdue follow-ups", value: d.followups.overdue, href: tasks("overdue") },
  ];
}
