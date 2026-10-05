export type Program = { id:string; slug:string; category:string; title:string; summary:string; duration:string; eligibility:string; fees:number; certification:string; curriculum:string[]; placement_assistance:string; trainer_name:string };
export type Country = { id:string; slug:string; name:string; overview:string; tuition:string; living_expenses:string; visa_process:string[]; work_opportunities:string; post_study_work:string; pr_opportunities:string; faq:{question:string;answer:string}[] };
export type University = { id:string; country_id:string; slug:string; name:string; city:string; overview:string; eligibility:string; requirements:string[]; deadlines:string[]; scholarships:string[] };
export type PortalPayload = {
  title:string; subtitle:string; metrics:{label:string;value:string|number}[];
  actions:{label:string;href:string}[]; columns:{key:string;label:string;type?:string}[];
  rows:Record<string, unknown>[]; panels:{title:string;items:string[]}[];
};
// AGN-003 (DEC-SCOPE-044): an agency member's effective optional permissions (GET /auth/me; a Master gets both true).
export type AgentPermissions = { can_verify_documents: boolean; can_view_reports: boolean };
export type User = {id:string; email:string; full_name:string; role:string; division:string; phone?:string; student_code?:string|null; profile:Record<string,unknown>; agent_member_role?:"master"|"staff"|null; agent_permissions?:AgentPermissions|null};

// AGN-020 (DEC-SCOPE-067; spec §5.3): GET /api/v1/workflows/overseas/agent/crm/reports/{kind} -- one column-driven shape for every report.
export type AgentReportCell = string | number | null;
export type AgentReportColumn = { key: string; label: string; numeric: boolean };
export type AgentReportOption = { value: string; label: string };
export type AgentReportOptions = Partial<Record<"members" | "countries" | "universities" | "intakes" | "statuses", AgentReportOption[]>>;
export type AgentReport = {
  kind: string; title: string; scope: "agency" | "own"; columns: AgentReportColumn[]; items: Record<string, AgentReportCell>[];
  totals: Record<string, AgentReportCell> | null; total: number; limit: number; offset: number; options: AgentReportOptions; as_of: string;
};

// ENH-014 (spec §5.1): GET/PUT /api/v1/account/notification-preferences.
export type NotificationPreferences = { whatsapp: boolean; sms: boolean; phone_valid: boolean };
export function isNotificationPreferences(value: unknown): value is NotificationPreferences {
  const v = value as Partial<NotificationPreferences> | null;
  return !!v && typeof v.whatsapp === "boolean" && typeof v.sms === "boolean" && typeof v.phone_valid === "boolean";
}

export type CareerPath = {id:string; division:string; slug:string; title:string; summary:string; skills:string[]; related_program_slugs:string[]; outcomes:string};
export type RealProject = {id:string; division:string; slug:string; title:string; summary:string; description:string; tech_stack:string[]};
export type Testimonial = {id:string; division:string; person_name:string; headline:string; quote:string; rating:number};
export type ContentPage = {id:string; slug:string; title:string; body:string; seo:Record<string,unknown>};
export type AvailableBatch = {id:string; name:string; program_id:string; program:string; schedule:string; timezone:string; capacity:number; available:number; start_date:string; end_date:string; mode:string};
export type LiveSessionInfo = {id:string; batch:string; title:string; starts_at:string; ends_at:string; provider:string; meeting_url:string|null; host_url:string|null; recording_url:string|null; recording_status:string; sync_status:string; status:string};
export type Webinar = {id:string; division:string; title:string; event_type:string; starts_at:string; location:string; description:string; is_past:boolean; registration_url?:string|null};
export type Scholarship = {id:string; title:string; eligibility:string; amount:string; deadline:string|null};

// --- ENH-016 analytics dashboards (docs/superpowers/specs/2026-09-28-enh-016-analytics-dashboards-design.md §7) ---
export type SchoolKpi = { key: string; label: string; value: number | null; tracked: boolean; note: string | null };

// --- AGN-018 agency dashboard (DEC-SCOPE-062; spec §5.3): one shape for Masters and staff, Master-only fields null for staff ---
export type CurrencyTotal = { currency: string; count: number; amount: number };
export type AgentBreakdown = { items: { label: string; count: number }[]; other: number };
export type AgentStaffRow = { code: string; name: string; active: boolean; students: number; applications: number; offers: number; enrollments: number };
export type AgentDashboard = {
  scope: "agency" | "own";
  member_code: string | null;
  students: number;
  applications: number;
  offers: number;
  visa_applications: number;
  visa_approvals: number;
  enrollments: number;
  pending_documents: number;
  pending_actions: number;
  by_country: AgentBreakdown;
  by_university: AgentBreakdown;
  staff: AgentStaffRow[] | null;
  unassigned_students: number | null;
  commission: { claimable: CurrencyTotal[]; claims: number; revenue: CurrencyTotal[] } | null;
  reports_available: boolean;
  as_of: string;
};
export type MetricCell = { count: number; pct: number | null };
export type GradeMetricRow = { key: string; label: string; is_proxy: boolean; definition: string | null; cells: Record<string, MetricCell> };
export type GradePerformance = { grades: string[]; students: Record<string, number>; metrics: GradeMetricRow[] };
export type AverageRow = { key: string; label: string; average_pct: number | null; count: number };
export type PerformerRow = { school_student_id: string; full_name: string; grade: string; average_pct: number; result_count: number };
export type StudentDevelopment = {
  headcounts: { students: number; teachers: number; parents: number };
  activities: { key: string; label: string; completed: number; pending: number }[];
  by_grade: AverageRow[];
  by_subject: AverageRow[];
  by_term: AverageRow[];
  at_risk: { items: PerformerRow[]; total: number };
  top_performers: { items: PerformerRow[]; total: number };
  at_risk_below: number;
  top_from: number;
};
export type ScorecardState = "completed" | "in_progress" | "not_started" | "not_in_plan" | "not_tracked";
export type ScorecardArea = { key: string; label: string; state: ScorecardState };
export type Scorecard = { school_student_id: string; full_name: string; grade: string; portfolio_completion_pct: number; areas: ScorecardArea[] };
export type ScorecardPage = { items: Scorecard[]; total: number; limit: number; offset: number };
export type TrackedValue = { value: number | null; tracked: boolean; note: string | null };
export type ServiceTotals = { services_included: number; delivered: number; pending: number; not_tracked: number; utilization_pct: number | null };
export type CrossSchoolSummary = {
  schools: { total: number; active: number; new: number; renewal_due: number };
  students: { total: number; by_grade: Record<string, number>; career_guidance: number; psychometric: number; counselling: number; global_education: number };
  services: ServiceTotals;
  outcomes: Record<string, TrackedValue>;
};
export type SchoolUtilizationRow = ServiceTotals & {
  school_id: string;
  name: string;
  tier: string | null;
  tier_valid_until: string | null;
  is_active: boolean;
  is_new: boolean;
  renewal_due: boolean;
  students: number;
  student_participation: number;
  pending_activities: number;
};
export type SchoolUtilizationPage = { items: SchoolUtilizationRow[]; total: number; limit: number; offset: number };

// ENH-017 (DEC-SCOPE-036): GET /school/global-education/pipeline -- high-level stage only (School CRM.md §19).
export type PipelineStudentRow = { school_student_id: string; full_name: string; student_code: string; grade: string; furthest_stage: string; furthest_stage_label: string; visa_stage_label: string | null; application_count: number };
export type GlobalEducationPipeline = {
  grade: number | null;
  students_in_scope: number;
  bridged_students: number;
  funnel: { key: string; label: string; count: number }[];
  not_tracked: { key: string; label: string; note: string }[];
  students: { items: PipelineStudentRow[]; total: number; limit: number; offset: number };
};
