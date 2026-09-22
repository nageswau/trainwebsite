export type NavItem = { label:string; href:string; children?:NavItem[] };

// Single source of truth for "which dashboard does this role land on" -- used by
// LoginForm (post-login redirect) and HeaderAuthActions (session-aware nav), so the
// mapping can't drift between the two (AUTH-001/AUTH-002).
export const ROLE_DASHBOARD_PATH: Record<string, string> = {
  it_student: "/it/student/dashboard",
  trainer: "/it/trainer/dashboard",
  placement_team: "/it/placement/dashboard",
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
};

// SCH-001/SCH-003 -- School roles use their own dedicated pages (bespoke forms/actions,
// not the generic PortalPage/[section] `_payload()` dispatcher every other role's console
// uses) but still share PortalShell's chrome; this is their own nav source, separate from
// PORTAL_NAV below so the "coordinator"/"principal"/"teacher"/"parent" segments never risk
// colliding with an unrelated role of the same URL-segment name in another division
// (RBAC_MATRIX.md §2.12's role-name collision guard, SCH-001-AC05).
export const SCHOOL_NAV: Record<string, NavItem[]> = {
  coordinator: ["dashboard", "students", "promotion", "transfers", "activities", "team", "reports", "entitlements", "notifications"].map(x => ({ label: x.replaceAll("-", " ").replace(/\b\w/g, c => c.toUpperCase()), href: `/school/coordinator/${x}` })),
  principal: ["dashboard", "reports", "entitlements"].map(x => ({ label: x.replaceAll("-", " ").replace(/\b\w/g, c => c.toUpperCase()), href: `/school/principal/${x}` })),
  teacher: ["dashboard"].map(x => ({ label: x.replaceAll("-", " ").replace(/\b\w/g, c => c.toUpperCase()), href: `/school/teacher/${x}` })),
  parent: ["dashboard", "notifications"].map(x => ({ label: x.replaceAll("-", " ").replace(/\b\w/g, c => c.toUpperCase()), href: `/school/parent/${x}` })),
  // SCH-004/005/006 -- single-item nav, same shape as principal/teacher/parent above.
  "academic-team": ["dashboard"].map(x => ({ label: x.replaceAll("-", " ").replace(/\b\w/g, c => c.toUpperCase()), href: `/school/academic-team/${x}` })),
  // ENH-011: Skills (Soft Skills / Digital Skills batches).
  "career-counselor": ["dashboard", "skills"].map(x => ({ label: x.replaceAll("-", " ").replace(/\b\w/g, c => c.toUpperCase()), href: `/school/career-counselor/${x}` })),
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

export const PORTAL_NAV:Record<string,NavItem[]> = {
  "it/student": ["dashboard","profile","course","attendance","assignments","projects","examinations","certificates","feedback","questions","fees","interview-schedule","placement-status","job-applications","downloads","support"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/it/student/${x}`})),
  "it/trainer": ["dashboard","attendance","assignments","assessments","materials","live-sessions","student-progress","questions","support"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/it/trainer/${x}`})),
  "it/placement": ["dashboard","candidates","company-requirements","interviews","offers","reports"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/it/placement/${x}`})),
  "it/hr": ["dashboard","job-requirements","shortlists","candidates","interviews"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/it/hr/${x}`})),
  "it/admin": ["dashboard","users","students","trainers","employers","programs","batches","enrollments","certificates","resources","consent","payments","roles","leads","support","reports"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/it/admin/${x}`})),
  "overseas/student": ["dashboard","profile","applications","documents","offer-letters","visa-status","scholarships","university-communication","payments","appointments","counselor-chat","downloads"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/overseas/student/${x}`})),
  "overseas/counselor": ["dashboard","students","leads","documents","applications","school-applications","visa","appointments","counselor-chat","reports"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/overseas/counselor/${x}`})),
  "overseas/university": ["dashboard","applications","offer-letters","admission-updates","student-communication","reports"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/overseas/university/${x}`})),
  "overseas/admin": ["dashboard","users","students","counselors","agents","commissions","universities","schools","school-staff","school-applications","school-transfers","applications","leads","payments","reports"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/overseas/admin/${x}`})),
  "overseas/agent": ["dashboard","students","applications","documents","commissions","reports"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/overseas/agent/${x}`})),
};
export const SUPER_ADMIN_NAV:NavItem[] = ["dashboard","users","students","staff","programs","batches","universities","recruiters","content","blogs","gallery","events","leads","applications","payments","reports","notifications","roles","settings","security-logs","backups"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:x==="dashboard"?"/admin":`/admin/${x}`}));
