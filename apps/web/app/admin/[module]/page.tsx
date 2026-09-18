import PortalShell from "@/components/PortalShell";
import PortalSection from "@/components/PortalSection";
import ReportPreview from "@/components/ReportPreview";
import WorkflowPanel from "@/components/WorkflowPanel";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import { serverApi } from "@/lib/api";
import type { User, PortalPayload } from "@/lib/types";

const info: Record<string, { title: string; subtitle: string }> = {
  users: { title: "User Management", subtitle: "Create, activate, and scope accounts across both divisions." },
  students: { title: "Student Management", subtitle: "Cross-division student overview with operational ownership." },
  staff: { title: "Staff Management", subtitle: "Trainers, counselors, placement, HR, university, agent, and administrator accounts." },
  programs: { title: "Course Management", subtitle: "IT catalogue, curriculum, fees, and publication status." },
  batches: { title: "Batch Management", subtitle: "Schedules, capacity, enrollment availability, and trainer assignment." },
  universities: { title: "University Management", subtitle: "Partner university catalogue and country ownership." },
  recruiters: { title: "Recruiter Management", subtitle: "Corporate hiring partners and job requirements." },
  content: { title: "Content Management", subtitle: "Division-aware landing pages and publication state." },
  blogs: { title: "Blog & News Management", subtitle: "Editorial content, categories, and publishing." },
  gallery: { title: "Gallery Management", subtitle: "Training, events, and student activity photos, division-aware and publication-gated." },
  events: { title: "Event Management", subtitle: "Education fairs, webinars, workshops, and seminars." },
  leads: { title: "Leads Management", subtitle: "Website enquiries, owners, pipeline state, and CRM synchronization." },
  applications: { title: "Application Management", subtitle: "Overseas university and IT placement application pipelines." },
  payments: { title: "Payment Management", subtitle: "Provider, amount, due date, status, and reconciliation records." },
  reports: { title: "Reports & Analytics", subtitle: "Cross-division user, lead, and collected-revenue reporting." },
  notifications: { title: "Notification Management", subtitle: "In-app and provider delivery history." },
  roles: { title: "Role & Permission Management", subtitle: "The API-enforced, deny-by-default RBAC matrix." },
  settings: { title: "Integration Settings", subtitle: "Non-secret provider readiness and environment state." },
  "security-logs": { title: "Security & Audit Logs", subtitle: "Authentication and privileged workflow events." },
  backups: { title: "Backup & Restore", subtitle: "Production recovery remains an AWS RDS/S3 operator workflow." },
};

type TableData = { rows: Record<string, unknown>[]; columns: { key: string; label: string }[]; panels?: { title: string; items: string[] }[] };
const columns = (items: [string, string][]) => items.map(([key, label]) => ({ key, label }));
const userColumns = () => columns([["id", "reference"], ["name", "Name"], ["email", "Email"], ["division", "Division"], ["role", "Role"], ["active", "Active"], ["provisioning_status", "Setup"]]);
const getRows = (path: string) => serverApi<Record<string, unknown>[]>(path);

// ENH-003: humane labels for the derived setup status (DataTable would otherwise print `pending_setup`).
const SETUP_LABEL: Record<string, string> = { active: "Password set", pending_setup: "Awaiting setup", link_expired: "Link expired" };
const withSetupLabels = (rows: Record<string, unknown>[]) => rows.map((row) => ({ ...row, provisioning_status: SETUP_LABEL[String(row.provisioning_status)] ?? row.provisioning_status }));

async function tableData(module: string): Promise<TableData> {
  if (module === "users") return { rows: withSetupLabels(await getRows("/api/v1/admin/users")), columns: userColumns() };
  if (module === "students") {
    const [it, overseas] = await Promise.all([serverApi<Record<string, unknown>[]>("/api/v1/admin/users?role=it_student"), serverApi<Record<string, unknown>[]>("/api/v1/admin/users?role=overseas_student")]);
    return { rows: withSetupLabels([...it, ...overseas]), columns: userColumns() };
  }
  if (module === "staff") {
    const rows = await serverApi<Record<string, unknown>[]>("/api/v1/admin/users");
    return { rows: withSetupLabels(rows.filter(row => !["it_student", "overseas_student", "super_admin"].includes(String(row.role)))), columns: userColumns() };
  }
  if (module === "programs") return { rows: await getRows("/api/v1/admin/programs"), columns: columns([["id", "reference"], ["title", "Program"], ["category", "Category"], ["duration", "Duration"], ["fees", "Fees"], ["active", "Active"]]) };
  if (module === "batches") return { rows: await getRows("/api/v1/admin/batches"), columns: columns([["id", "reference"], ["program", "Program"], ["name", "Batch"], ["trainer_id", "Trainer reference"], ["schedule", "Schedule"], ["capacity", "Capacity"], ["enrolled", "Enrolled"], ["status", "Status"]]) };
  if (module === "universities") return { rows: await getRows("/api/v1/admin/universities"), columns: columns([["id", "reference"], ["name", "University"], ["country", "Country"], ["city", "City"], ["slug", "Slug"]]) };
  if (module === "recruiters") return { rows: await getRows("/api/v1/admin/companies"), columns: columns([["id", "reference"], ["name", "Company"], ["website", "Website"], ["partner_type", "Type"]]) };
  if (module === "content") return { rows: await getRows("/api/v1/cms/manage/pages"), columns: columns([["id", "reference"], ["division", "Division"], ["slug", "Slug"], ["title", "Title"], ["published", "Published"], ["updated_at", "Updated"]]) };
  if (module === "blogs") return { rows: await getRows("/api/v1/cms/manage/posts"), columns: columns([["id", "reference"], ["division", "Division"], ["title", "Title"], ["category", "Category"], ["published", "Published"], ["updated_at", "Updated"]]) };
  if (module === "gallery") return { rows: await getRows("/api/v1/cms/manage/gallery"), columns: columns([["id", "reference"], ["division", "Division"], ["title", "Title"], ["image_url", "Image URL"], ["category", "Category"], ["published", "Published"], ["updated_at", "Updated"]]) };
  if (module === "events") return { rows: await getRows("/api/v1/cms/events"), columns: columns([["id", "reference"], ["division", "Division"], ["title", "Event"], ["event_type", "Type"], ["starts_at", "Starts"], ["location", "Location"]]) };
  if (module === "leads") return { rows: await getRows("/api/v1/admin/leads"), columns: columns([["id", "reference"], ["name", "Name"], ["division", "Division"], ["subject", "Interest"], ["status", "Status"], ["crm_sync_status", "CRM Sync"]]) };
  if (module === "applications") return { rows: await getRows("/api/v1/admin/applications"), columns: columns([["id", "reference"], ["division", "Division"], ["student", "Student"], ["target", "University / Job"], ["reference", "Reference"], ["status", "Status"], ["updated_at", "Updated"]]) };
  if (module === "payments") return { rows: await getRows("/api/v1/admin/payments"), columns: columns([["id", "reference"], ["user_id", "User reference"], ["student", "User"], ["division", "Division"], ["amount", "Amount"], ["currency", "Currency"], ["provider", "Provider"], ["status", "Status"]]) };
  if (module === "notifications") return { rows: await getRows("/api/v1/admin/notifications"), columns: columns([["id", "reference"], ["user_id", "User reference"], ["recipient", "Recipient"], ["division", "Division"], ["title", "Title"], ["read", "Read"], ["deliveries", "Deliveries"], ["created_at", "Created"]]) };
  if (module === "security-logs") return { rows: await getRows("/api/v1/admin/audit"), columns: columns([["id", "reference"], ["user_id", "User reference"], ["action", "Action"], ["entity_type", "Entity"], ["entity_id", "Entity reference"], ["outcome", "Outcome"], ["created_at", "Created"]]) };
  if (module === "settings") return { rows: await getRows("/api/v1/admin/system-status"), columns: columns([["service", "Service"], ["status", "Status"]]) };
  if (module === "reports") {
    const report = await serverApi<Record<string, Record<string, unknown>>>("/api/v1/admin/reports/summary");
    return { rows: Object.entries(report).map(([division, values]) => ({ division, ...values })), columns: columns([["division", "Division"], ["users", "Users"], ["leads", "Leads"], ["revenue", "Revenue"]]) };
  }
  if (module === "roles") return { rows: [
    { role: "super_admin", division: "global", scope: "All operations" }, { role: "it_admin", division: "it", scope: "IT administration" }, { role: "trainer", division: "it", scope: "Assigned learning batches" }, { role: "placement_team", division: "it", scope: "Placement operations" }, { role: "hr_team", division: "it", scope: "Employer hiring" }, { role: "it_student", division: "it", scope: "Own learning record" }, { role: "overseas_admin", division: "overseas", scope: "Overseas administration" }, { role: "counselor", division: "overseas", scope: "Assigned applications" }, { role: "university_rep", division: "overseas", scope: "Own university applications" }, { role: "agent", division: "overseas", scope: "Linked students and commissions" }, { role: "overseas_student", division: "overseas", scope: "Own application record" },
  ], columns: columns([["role", "Role"], ["division", "Division"], ["scope", "Enforced scope"]]) };
  if (module === "backups") return { rows: [{ component: "PostgreSQL", control: "RDS automated backups and pre-release snapshots", owner: "AWS operations" }, { component: "Documents", control: "Private S3 versioning and lifecycle", owner: "AWS operations" }, { component: "Restore", control: "Staged restore drill before production", owner: "Release owner" }], columns: columns([["component", "Component"], ["control", "Recovery control"], ["owner", "Owner"]]), panels: [{ title: "Safety", items: ["No destructive restore is exposed from the web portal.", "Follow docs/DEPLOYMENT_AWS.md for backup and recovery."] }] };
  return { rows: [], columns: [] };
}

export default async function Module({ params }: { params: Promise<{ module: string }> }) {
  const { module } = await params;
  let user: User;
  try { user = await serverApi<User>("/api/v1/auth/me"); }
  catch { return <div className="section"><div className="container card"><h1>Administrator access required</h1></div></div>; }
  if (user.role !== "super_admin") return <div className="section"><div className="container card"><h1>Super Administrator access required</h1></div></div>;
  const cfg = info[module] || { title: module.replaceAll("-", " ").replace(/\b\w/g, character => character.toUpperCase()), subtitle: "Administrative workspace." };
  let table: TableData;
  try { table = await tableData(module); }
  catch (error) { table = { rows: [], columns: [], panels: [{ title: "Data error", items: [error instanceof Error ? error.message : "Unable to load this module"] }] }; }
  const data: PortalPayload = { title: cfg.title, subtitle: cfg.subtitle, metrics: [], actions: [], columns: table.columns, rows: table.rows, panels: table.panels || [] };
  return <PortalShell nav={SUPER_ADMIN_NAV} roleLabel="Super Administrator" userName={user.full_name}><PortalSection data={data}/><WorkflowPanel user={user} section={module}/>{module === "reports" && <div className="portal-content" style={{ paddingTop: 0 }}><ReportPreview/></div>}</PortalShell>;
}
