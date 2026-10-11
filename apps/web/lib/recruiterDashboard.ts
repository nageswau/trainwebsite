// rec-032 (DEC-SCOPE-179): the recruiter dashboard -- types, endpoint, tiles, quick actions and the skill search box. Every figure is
// computed by the API (services/recruiter_metrics.py, backlog Appendix B D1-D14); the browser only lays them out and links each to its list.
import { distinctTerms } from "@/lib/recruiterCandidateSearch";

export type TileKey =
  | "new_leads" | "contacts_pending" | "hot_companies" | "meetings_scheduled" | "active_companies" | "new_requirements"
  | "candidates_sourced" | "profiles_shared" | "interviews_scheduled" | "candidates_selected" | "candidates_joined"
  | "candidates_rejected" | "follow_ups_due" | "requirements_expiring";
export type DashboardTiles = Record<TileKey, number> & { requirements_expired: number };
export type RecruiterDashboard = {
  day: string; period: { from: string; to: string }; recruiter: { id: string; full_name: string } | null; tiles: DashboardTiles;
};

export const DASHBOARD_URL = "/api/v1/recruiter/dashboard";
export const DASHBOARD_PATH = "/recruiter/dashboard";
export const FIND_CANDIDATES_PATH = "/recruiter/find-candidates";

// EVID-018 §1, in the source's order. `list` is the list the tile opens (DB8); `assigned` lists also narrow to a filtered recruiter.
type Tile = { key: TileKey; label: string; hint: string; list: string; assigned?: boolean };
export const TILES: Tile[] = [
  { key: "new_leads", label: "New Recruiter Leads", hint: "New Lead companies added in the last 7 days", list: "/recruiter/pipeline?stage=new_lead" },
  { key: "contacts_pending", label: "Calls/Contacts Pending", hint: "New Lead companies with no call logged yet", list: "/recruiter/pipeline?stage=new_lead" },
  { key: "hot_companies", label: "Hot Recruiters", hint: "Open companies marked Hot", list: "/recruiter/companies?priority=hot", assigned: true },
  { key: "meetings_scheduled", label: "Meetings Scheduled", hint: "In the next 7 days", list: "/recruiter/meetings?view=upcoming" },
  { key: "active_companies", label: "Active Companies", hint: "With a live job requirement", list: "/recruiter/companies", assigned: true },
  { key: "new_requirements", label: "New Job Requirements", hint: "Added in the last 7 days", list: "/recruiter/requirements", assigned: true },
  { key: "candidates_sourced", label: "Candidates Sourced", hint: "Added to requirements this month", list: "/recruiter/requirements", assigned: true },
  { key: "profiles_shared", label: "Profiles Shared", hint: "Sent to companies this month", list: "/recruiter/requirements", assigned: true },
  { key: "interviews_scheduled", label: "Interviews Scheduled", hint: "Upcoming", list: "/recruiter/interviews?view=upcoming" },
  { key: "candidates_selected", label: "Candidates Selected", hint: "This month", list: "/recruiter/requirements", assigned: true },
  { key: "candidates_joined", label: "Candidates Joined", hint: "This month", list: "/recruiter/joinings?view=joined" },
  { key: "candidates_rejected", label: "Rejected Candidates", hint: "This month", list: "/recruiter/requirements", assigned: true },
  { key: "follow_ups_due", label: "Follow-ups Due", hint: "Due today or overdue", list: "/recruiter/follow-ups?due=today" },
  { key: "requirements_expiring", label: "Requirements About to Expire", hint: "Deadline within 7 days or passed", list: "/recruiter/requirements?deadline=expiring", assigned: true },
];

/** The list a tile opens; with a recruiter filter, the Companies and Requirements lists open on that recruiter too. */
export function tileHref(tile: Tile, recruiterId: string | null): string {
  if (!recruiterId || !tile.assigned) return tile.list;
  const [path, query = ""] = tile.list.split("?");
  const params = new URLSearchParams(query);
  params.set("assigned", recruiterId);
  return `${path}?${params}`;
}

// EVID-018 §1 quick actions (DB9). Meetings are scheduled from a company and interviews from a candidate on a requirement, so those two
// open the list to pick from; managers only read meetings and interviews, so they don't get them.
const CREATORS = ["placement_team", "placement_manager", "super_admin"];
const SCHEDULERS = ["placement_team", "super_admin"];
export const QUICK_ACTIONS: { label: string; href: string; roles: string[] }[] = [
  { label: "+ Add Recruiter", href: "/recruiter/companies/new?with=contact", roles: CREATORS }, // rec-004: a company and its first contact
  { label: "+ Add Company", href: "/recruiter/companies/new", roles: CREATORS },
  { label: "+ Add Job Requirement", href: "/recruiter/requirements/new", roles: CREATORS },
  { label: "+ Add Candidate", href: "/recruiter/candidates/new", roles: CREATORS },
  { label: "+ Schedule Meeting", href: "/recruiter/companies", roles: SCHEDULERS },
  { label: "+ Schedule Interview", href: "/recruiter/requirements", roles: SCHEDULERS },
];
export const quickActionsFor = (role: string) => QUICK_ACTIONS.filter((a) => a.roles.includes(role));

/** S2-§9 (DB10): comma-separated skills, each a required skill on Find Candidates (rec-013); null when nothing usable was typed. */
export function skillSearchHref(text: string): string | null {
  const skills = distinctTerms(text.split(","));
  if (!skills.length) return null;
  const params = new URLSearchParams();
  skills.forEach((s) => params.append("all", s));
  return `${FIND_CANDIDATES_PATH}?${params}`;
}

export const dashboardUrl = (recruiterId: string | null) => (recruiterId ? `${DASHBOARD_URL}?recruiter=${encodeURIComponent(recruiterId)}` : DASHBOARD_URL);
