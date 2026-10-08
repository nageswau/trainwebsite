import type { AgentPermissions } from "@/lib/types";
import { GROUP_LABELS, STATUS_GROUPS } from "./agentApplications";
import { VIEW_NAV_LABELS, VIEWS } from "./agentDocuments";
// `badge` (AGN-017): an unread count shown after the label; only the agency's Notifications item sets it.
export type NavItem = { label:string; href:string; children?:NavItem[]; badge?:number };

export const AGENT_NOTIFICATIONS_HREF = "/overseas/agent/notifications";

// AGN-017 (DEC-SCOPE-059 N8): the unread count on one nav item; no count (null, 0) leaves the nav as it was.
export function withBadge(nav: NavItem[], href: string, count: number | null): NavItem[] {
  return count ? nav.map((item) => (item.href === href ? { ...item, badge: count } : item)) : nav;
}

// Single source of truth for "which dashboard does this role land on" -- used by
// LoginForm (post-login redirect) and HeaderAuthActions (session-aware nav), so the
// mapping can't drift between the two (AUTH-001/AUTH-002).
export const ROLE_DASHBOARD_PATH: Record<string, string> = {
  it_student: "/it/student/dashboard",
  trainer: "/it/trainer/dashboard",
  placement_team: "/recruiter/dashboard", // rec-001 (DEC-SCOPE-116 R2, Q-29): the recruiter's own workspace
  placement_manager: "/recruiter/manager/team",
  hr_team: "/it/hr/dashboard",
  employer: "/it/employer/dashboard",
  it_admin: "/it/admin/dashboard",
  overseas_student: "/overseas/student/dashboard",
  counselor: "/overseas/counselor/dashboard",
  university_rep: "/overseas/university/dashboard",
  agent: "/overseas/agent/dashboard",
  overseas_admin: "/overseas/admin/dashboard",
  super_admin: "/admin",
  // SCH-001 -- all four School roles now have a real dashboard.
  school_coordinator: "/school/coordinator/dashboard",
  school_principal: "/school/principal/dashboard",
  school_teacher: "/school/teacher/dashboard",
  school_parent: "/school/parent/dashboard",
  // SCH-004/005/006 -- the three service-delivery roles.
  academic_team: "/school/academic-team/dashboard",
  career_counselor: "/school/career-counselor/dashboard",
  psychometric_team: "/school/psychometric-team/dashboard",
  // bdm-001 (DEC-SCOPE-055): the BDM CRM roles. bdm-014 / bdm-023 fill these pages in.
  bdm: "/bdm/my-day",
  bdm_manager: "/bdm/manager/dashboard",
  // tel-001 (DEC-SCOPE-073): the Telecaller CRM roles. tel-021 fills the dashboard in; managers land on their team (T23).
  telecaller: "/telecaller/dashboard",
  telecaller_manager: "/telecaller/manager/team",
  // upc-001 (DEC-SCOPE-118): the University Partnership CRM roles. upc-022 fills the dashboard in; heads land on their team (U3).
  partnership_manager: "/partnership/dashboard",
  partnership_head: "/partnership/head/team",
};

// tel-017 (DEC-SCOPE-076): a counselor belongs to IT or Overseas, so its landing depends on the division too. Every caller that
// knows the account's division uses this; the role map above stays the default.
export function dashboardPathFor(user: { role: string; division?: string | null }): string {
  if (user.role === "counselor" && user.division === "it") return "/it/counselor/dashboard";
  return ROLE_DASHBOARD_PATH[user.role] ?? "/";
}

// bdm-001: BDM and BDM-manager sidebars, and the signed-out chooser (College BDMs sign in at /it, Agent/School BDMs at /overseas;
// managers at /admin). bdm-002 adds Organizations to both; bdm-006 adds Appointments to both.
// bdm-010: Travel (BDM), Approvals (manager), and each role's Notifications (QA10-01; the unread badge comes from lib/bdmNav).
// bdm-009: Activities in both. bdm-004: Pipeline in both. bdm-005: MoUs after Pipeline in both.
export const BDM_NOTIFICATIONS_HREF = "/bdm/notifications";
export const BDM_MANAGER_NOTIFICATIONS_HREF = "/bdm/manager/notifications";
export const BDM_NAV: NavItem[] = [
  { label: "My Day", href: "/bdm/my-day" }, { label: "Calendar", href: "/bdm/calendar" }, { label: "Organizations", href: "/bdm/organizations" },
  { label: "Pipeline", href: "/bdm/pipeline" },
  { label: "MoUs", href: "/bdm/mous" }, { label: "Appointments", href: "/bdm/appointments" }, { label: "Follow-ups", href: "/bdm/follow-ups" },
  { label: "Requests", href: "/bdm/meeting-requests" }, // tel-019
  { label: "Activities", href: "/bdm/activities" }, { label: "Daily report", href: "/bdm/daily-report" }, // bdm-015
  { label: "Travel", href: "/bdm/travel" },
  { label: "Notifications", href: BDM_NOTIFICATIONS_HREF }, { label: "Profile", href: "/bdm/profile" },
];
export const BDM_MANAGER_NAV: NavItem[] = [
  { label: "Dashboard", href: "/bdm/manager/dashboard" },
  { label: "Performance", href: "/bdm/manager/performance" }, { label: "Master view", href: "/bdm/manager/hierarchy" }, // bdm-024
  { label: "Team", href: "/bdm/manager/team" },
  { label: "Organizations", href: "/bdm/manager/organizations" }, { label: "Pipeline", href: "/bdm/manager/pipeline" },
  { label: "MoUs", href: "/bdm/manager/mous" }, { label: "Appointments", href: "/bdm/manager/appointments" },
  { label: "Requests", href: "/bdm/manager/meeting-requests" }, // tel-019
  { label: "Follow-ups", href: "/bdm/manager/follow-ups" },
  { label: "Calendar", href: "/bdm/manager/calendar" }, { label: "Activities", href: "/bdm/manager/activities" },
  { label: "Daily reports", href: "/bdm/manager/daily-reports" }, // bdm-015
  { label: "Targets", href: "/bdm/manager/targets" }, // bdm-016
  { label: "Approvals", href: "/bdm/manager/approvals" },
  { label: "Notifications", href: BDM_MANAGER_NOTIFICATIONS_HREF },
];
export const BDM_SIGN_IN = "/bdm/sign-in";

// tel-001: the telecaller and telecaller-manager sidebars and the signed-out chooser (IT telecallers sign in at /it, Overseas at
// /overseas, managers at /admin). Later tel items add their pages here.
// tel-008: My Leads (telecaller) and Leads (manager).
export const TELECALLER_NOTIFICATIONS_HREF = "/telecaller/notifications"; // tel-020: the §20 alerts
export const TELECALLER_NAV: NavItem[] = [
  { label: "Dashboard", href: "/telecaller/dashboard" }, { label: "My Leads", href: "/telecaller/leads" },
  { label: "Follow-ups", href: "/telecaller/follow-ups" }, // tel-011
  { label: "BDM requests", href: "/telecaller/meeting-requests" }, // tel-019
  { label: "Notifications", href: TELECALLER_NOTIFICATIONS_HREF },
  { label: "Profile", href: "/telecaller/profile" },
];
// tel-002: Products and Campaigns (the catalogue the manager maintains); tel-022: Targets; tel-007: Lead assignment and Distribution rules.
export const TELECALLER_MANAGER_NAV: NavItem[] = [
  { label: "Team", href: "/telecaller/manager/team" }, { label: "Leads", href: "/telecaller/manager/leads" },
  { label: "Follow-ups", href: "/telecaller/manager/follow-ups" }, // tel-011
  { label: "Lead assignment", href: "/telecaller/manager/assignment" }, { label: "Distribution rules", href: "/telecaller/manager/distribution" },
  { label: "Lead import", href: "/telecaller/manager/imports" }, // tel-006
  { label: "Targets", href: "/telecaller/manager/targets" },
  { label: "Performance", href: "/telecaller/manager/performance" }, // tel-023
  { label: "Reports", href: "/telecaller/manager/reports" }, // tel-024
  { label: "Alert settings", href: "/telecaller/manager/alerts" }, // tel-020
  { label: "Products", href: "/telecaller/manager/products" },
  { label: "Campaigns", href: "/telecaller/manager/campaigns" },
  // tel-012: the content library telecallers work from.
  { label: "Scripts", href: "/telecaller/manager/scripts" }, { label: "Templates", href: "/telecaller/manager/templates" },
  { label: "Brochures", href: "/telecaller/manager/brochures" },
];
export const TELECALLER_SIGN_IN = "/telecaller/sign-in";

// rec-001 (DEC-SCOPE-116, Q-29): the recruiter's workspace, followed by the legacy placement screens it still works from; the
// placement manager's pages (managers sign in at /admin). Later rec items add their pages here.
const LEGACY_PLACEMENT = ["candidates", "company-requirements", "interviews", "offers", "reports"];
export const RECRUITER_NAV: NavItem[] = [
  { label: "Dashboard", href: "/recruiter/dashboard" }, { label: "Companies", href: "/recruiter/companies" }, { label: "Profile", href: "/recruiter/profile" }, { label: "Skills Master", href: "/recruiter/skills" },
  { label: "Candidate Master", href: "/recruiter/candidates" }, // rec-009
  ...LEGACY_PLACEMENT.map((x) => ({ label: x.replaceAll("-", " ").replace(/\b\w/g, (c) => c.toUpperCase()), href: `/it/placement/${x}` })),
];
export const RECRUITER_MANAGER_NAV: NavItem[] = [
  { label: "Team", href: "/recruiter/manager/team" }, { label: "Companies", href: "/recruiter/companies" }, { label: "Catalogues", href: "/recruiter/manager/catalogue" }, { label: "Skills Master", href: "/recruiter/manager/skills" },
  { label: "Candidate Master", href: "/recruiter/candidates" }, // rec-009: shared with recruiters (R11)
];

// upc-001 (PU8): the EVID-020 §32 main menu, in source order, each entry naming the item that builds its page. An entry joins the
// manager's sidebar once that item lands (it sets `live`); until then the dashboard lists it as coming soon, never as a dead link.
export type PartnershipMenuEntry = { label: string; href: string; item: string; live: boolean };
const menu = (label: string, path: string, item: string, live = false): PartnershipMenuEntry => ({ label, href: `/partnership/${path}`, item, live });
export const PARTNERSHIP_MENU: PartnershipMenuEntry[] = [
  menu("Dashboard", "dashboard", "upc-022", true), menu("Global University Database", "search", "upc-024"),
  menu("University Master", "universities", "upc-003", true), menu("Contact Management", "contacts", "upc-006"),
  menu("Partnership Pipeline", "pipeline", "upc-007", true), menu("Meetings", "meetings", "upc-009"), menu("University Visits", "visits", "upc-010", true),
  menu("MoU & Agreements", "agreements", "upc-014"), menu("Commercial Terms", "commercial-terms", "upc-016"),
  menu("Courses & Programs", "courses", "upc-017"), menu("Student Opportunities", "opportunities", "upc-018"),
  menu("University Performance", "performance", "upc-018"), menu("Follow-ups & Tasks", "tasks", "upc-020"), menu("Calendar", "calendar", "upc-011"),
  menu("Documents", "documents", "upc-026"), menu("Alerts", "alerts", "upc-015"), menu("Targets & Forecast", "targets", "upc-021"),
  menu("Global Partnership Map", "map", "upc-025"), menu("Reports", "reports", "upc-031"),
];
export const PARTNERSHIP_NAV: NavItem[] = [
  ...PARTNERSHIP_MENU.filter((e) => e.live).map(({ label, href }) => ({ label, href })),
  { label: "Profile", href: "/partnership/profile" },
];
export const PARTNERSHIP_HEAD_NAV: NavItem[] = [
  { label: "Team", href: "/partnership/head/team" }, { label: "University Master", href: "/partnership/universities" },
  { label: "Partnership Pipeline", href: "/partnership/pipeline" },
  { label: "University Visits", href: "/partnership/visits" }, { label: "Visit approvals", href: "/partnership/visits/approvals" }, // upc-010 (VS4)
];

// SCH-001/SCH-003 -- School roles use their own dedicated pages (bespoke forms/actions,
// not the generic PortalPage/[section] `_payload()` dispatcher every other role's console
// uses) but still share PortalShell's chrome; this is their own nav source, separate from
// PORTAL_NAV below so the "coordinator"/"principal"/"teacher"/"parent" segments never risk
// colliding with an unrelated role of the same URL-segment name in another division
// (RBAC_MATRIX.md §2.12's role-name collision guard, SCH-001-AC05).
export const SCHOOL_NAV: Record<string, NavItem[]> = {
  coordinator: ["dashboard", "students", "promotion", "transfers", "activities", "feedback", "team", "reports", "global-education", "entitlements", "notifications"].map(x => ({ label: x.replaceAll("-", " ").replace(/\b\w/g, c => c.toUpperCase()), href: `/school/coordinator/${x}` })),
  principal: ["dashboard", "reports", "global-education", "feedback", "entitlements", "notifications"].map(x => ({ label: x.replaceAll("-", " ").replace(/\b\w/g, c => c.toUpperCase()), href: `/school/principal/${x}` })),
  teacher: ["dashboard", "attendance"].map(x => ({ label: x.replaceAll("-", " ").replace(/\b\w/g, c => c.toUpperCase()), href: `/school/teacher/${x}` })),
  parent: ["dashboard", "notifications"].map(x => ({ label: x.replaceAll("-", " ").replace(/\b\w/g, c => c.toUpperCase()), href: `/school/parent/${x}` })),
  // SCH-004/005/006 -- single-item nav, same shape as principal/teacher/parent above.
  "academic-team": ["dashboard"].map(x => ({ label: x.replaceAll("-", " ").replace(/\b\w/g, c => c.toUpperCase()), href: `/school/academic-team/${x}` })),
  // ENH-011: Skills (Soft Skills / Digital Skills batches). ENH-020: Funding (loan / scholarship / funding support cases).
  "career-counselor": ["dashboard", "skills", "funding"].map(x => ({ label: x.replaceAll("-", " ").replace(/\b\w/g, c => c.toUpperCase()), href: `/school/career-counselor/${x}` })),
  "psychometric-team": ["dashboard"].map(x => ({ label: x.replaceAll("-", " ").replace(/\b\w/g, c => c.toUpperCase()), href: `/school/psychometric-team/${x}` })),
};
export const IT_PUBLIC:NavItem[] = [
  {label:"Home",href:"/it"},{label:"About",href:"/it/about"},
  // Grouped under Programs (previously 4 flat top-level items) -- the header nav had grown to
  // 12 items and was wrapping awkwardly at common desktop widths; these four all describe the
  // training experience a program leads to, so they read naturally as a submenu of Programs.
  {label:"Programs",href:"/it/programs",children:[
    {label:"All Programs",href:"/it/programs"},{label:"Career Paths",href:"/it/career-paths"},{label:"Real Projects",href:"/it/real-projects"},
    {label:"Success Stories",href:"/it/success-stories"},{label:"Business Services",href:"/it/business-services"},{label:"Webinars",href:"/it/webinars"}
  ]},
  {label:"Placements",href:"/it/placements"},{label:"Online Learning",href:"/it/online-learning"},{label:"Corporate Hiring",href:"/it/corporate-hiring"},
  {label:"Careers",href:"/it/careers"},{label:"Contact",href:"/it/contact"}
];
export const OVERSEAS_PUBLIC:NavItem[] = [
  {label:"Home",href:"/overseas"},{label:"About",href:"/overseas/about"},{label:"Countries",href:"/overseas/countries"},{label:"Universities",href:"/overseas/universities"},
  {label:"Courses",href:"/overseas/courses"},{label:"Admission Process",href:"/overseas/admission-process"},{label:"Visa",href:"/overseas/visa-services"},
  {label:"Scholarships",href:"/overseas/scholarships"},{label:"Events",href:"/overseas/events"},{label:"Contact",href:"/overseas/contact"}
];

// AGN-018 (DEC-SCOPE-062 G4): "All applications" first (EVID-015 §4 "All"), then the AGN-008 filters. All is the bare path -- the
// list's own default view (spec §6.3) -- so it is the current link wherever no filter is set (browser QA18-07).
const AGENT_APPLICATION_FILTERS: NavItem[] = STATUS_GROUPS.map((g) => ({ label: GROUP_LABELS[g], href: g === "all" ? "/overseas/agent/applications" : `/overseas/agent/applications?status=${g}` }));
// AGN-018 (G4): EVID-015 §4 wording where the generated title-case label differs.
const AGENT_NAV_LABELS: Record<string, string> = { tasks: "Tasks & Follow-ups", performance: "Staff Performance" };
// AGN-009 (DEC-SCOPE-052 G9): EVID-015 §4 Documents -> Pending / Uploaded / Additional Documents, for Masters and staff.
const AGENT_DOCUMENT_VIEWS: NavItem[] = VIEWS.map((v) => ({ label: VIEW_NAV_LABELS[v], href: `/overseas/agent/documents?view=${v}` }));

export const PORTAL_NAV:Record<string,NavItem[]> = {
  "it/student": ["dashboard","profile","course","attendance","assignments","projects","examinations","certificates","feedback","questions","fees","interview-schedule","placement-status","job-applications","downloads","support"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/it/student/${x}`})),
  "it/trainer": ["dashboard","attendance","assignments","assessments","materials","live-sessions","student-progress","questions","support"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/it/trainer/${x}`})),
  "it/placement": [...["dashboard","candidates","company-requirements","interviews","offers","reports"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/it/placement/${x}`})),{label:"Recruiter Workspace",href:"/recruiter/dashboard"}], // rec-001: the way back
  "it/hr": [...["dashboard","job-requirements","shortlists","candidates","interviews"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/it/hr/${x}`})),{label:"Candidate Master",href:"/recruiter/candidates"}], // rec-009: read only
  // bdm-001: "BDMs" is written out -- the generated label would read "Bdms".
  // tel-017 (DEC-SCOPE-076 C1): an IT counselor works leads only; tel-016 added Appointments (lead bookings), tel-018 the student link.
  "it/counselor": ["dashboard","leads","appointments"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/it/counselor/${x}`})),
  "it/admin": [...["dashboard","users","students","trainers","counselors","employers","programs","batches","enrollments","certificates","resources","consent","payments","roles","leads","support","reports"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/it/admin/${x}`})),{label:"BDMs",href:"/it/admin/bdms"},{label:"Telecallers",href:"/it/admin/telecallers"},{label:"Telecaller Performance",href:"/it/admin/telecaller-performance"},{label:"Telecaller Reports",href:"/it/admin/telecaller-reports"},{label:"Recruiter Staff",href:"/it/admin/recruiter-staff"}],
  "overseas/student": ["dashboard","profile","applications","documents","offer-letters","visa-status","scholarships","university-communication","payments","appointments","counselor-chat","downloads"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/overseas/student/${x}`})),
  "overseas/counselor": ["dashboard","students","leads","documents","applications","school-applications","visa","appointments","counselor-chat","reports"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/overseas/counselor/${x}`})),
  "overseas/university": ["dashboard","applications","offer-letters","admission-updates","student-communication","reports"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/overseas/university/${x}`})),
  "overseas/admin": [...["dashboard","users","students","counselors","agents","commissions","universities","schools","school-staff","school-applications","school-transfers","activity-feedback","school-analytics","applications","leads","payments","reports"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/overseas/admin/${x}`})),{label:"BDMs",href:"/overseas/admin/bdms"},{label:"Telecallers",href:"/overseas/admin/telecallers"},{label:"Telecaller Performance",href:"/overseas/admin/telecaller-performance"},{label:"Telecaller Reports",href:"/overseas/admin/telecaller-reports"},{label:"Partnership managers",href:"/overseas/admin/partnership-managers"},{label:"Agent deposits",href:"/overseas/admin/agent-deposits"},{label:"Agent network",href:"/overseas/admin/agent-network"}], // AGN-011: its own page (DEC-SCOPE-058); AGN-022: its own page (DEC-SCOPE-064)
  // AGN-007 (DEC-SCOPE-049): Universities is the agency's own university list. AGN-008 (DEC-SCOPE-050 A7): Applications carries
  // the EVID-015 §4 sidebar filters as sub-links (same page, ?status=). AGN-016 (DEC-SCOPE-053 T5): Tasks, for Masters and staff,
  // after Documents (the EVID-015 §4 sidebar order). AGN-017 (DEC-SCOPE-059 N8): Notifications, for Masters and staff, after Tasks.
  "overseas/agent": ["dashboard","students","universities","applications","documents","tasks","notifications","commissions","reports","performance","team"].map(x=>({label:AGENT_NAV_LABELS[x]??x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/overseas/agent/${x}`,...(x==="applications"?{children:AGENT_APPLICATION_FILTERS}:x==="documents"?{children:AGENT_DOCUMENT_VIEWS}:{})})),
};
// AGN-002 (DEC-SCOPE-040 S1): an agency's staff work on students and applications; Team and Commissions stay Master-only (the
// server refuses them regardless -- this only keeps dead links out of the sidebar). AGN-019 (DEC-SCOPE-066 P7): Staff Performance too.
const STAFF_HIDDEN = new Set(["/overseas/agent/team", "/overseas/agent/commissions", "/overseas/agent/performance"]);
const STAFF_REPORTS = "/overseas/agent/reports";
// AGN-003 (DEC-SCOPE-044 P1): Reports is optional for staff -- shown only once their Master switches it on (the server refuses it
// regardless; this keeps a dead link out of the sidebar). Masters are never limited.
// AGN-018 (DEC-SCOPE-062 G4): the EVID-015 §4 staff sidebar -- "My Students" with All and Add (Add opens the existing form). No
// Journey link until a route exists. Nothing is removed, so no access changes.
const STAFF_STUDENTS: NavItem = {
  label: "My Students",
  href: "/overseas/agent/students",
  children: [
    { label: "All", href: "/overseas/agent/students" },
    { label: "Add", href: "/overseas/agent/students?new=1" },
  ],
};
export function agentNavFor(nav: NavItem[], memberRole?: string | null, permissions?: AgentPermissions | null): NavItem[] {
  if (memberRole !== "staff") return nav;
  return nav
    .filter((item) => !STAFF_HIDDEN.has(item.href) && (item.href !== STAFF_REPORTS || permissions?.can_view_reports === true))
    .map((item) => (item.href === STAFF_STUDENTS.href ? STAFF_STUDENTS : item));
}
// ENH-016: the cross-school School Analytics page lives under /overseas/admin (D1: Overseas and Super Admins).
export const SUPER_ADMIN_NAV:NavItem[] = [...["dashboard","users","students","staff","programs","batches","universities","recruiters","content","blogs","gallery","events","leads","applications","payments","reports","notifications","roles","settings","security-logs","backups"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:x==="dashboard"?"/admin":`/admin/${x}`})),{label:"BDMs",href:"/admin/bdms"},{label:"BDM Travel Approvals",href:"/admin/bdm-travel-approvals"},{label:"BDM Dashboard",href:"/bdm/manager/dashboard"},{label:"BDM Performance",href:"/bdm/manager/performance"},{label:"BDM Master View",href:"/bdm/manager/hierarchy"},{label:"Telecallers",href:"/admin/telecallers"},{label:"Telecaller Performance",href:"/admin/telecaller-performance"},{label:"Telecaller Reports",href:"/admin/telecaller-reports"},{label:"Recruiter Staff",href:"/admin/recruiter-staff"},{label:"Recruiter Companies",href:"/recruiter/companies"},{label:"Partnership managers",href:"/admin/partnership-managers"},{label:"Partnership Visit Approvals",href:"/partnership/visits/approvals"},{label:"Candidate Master",href:"/recruiter/candidates"},{label:"School Analytics",href:"/overseas/admin/school-analytics"}];
