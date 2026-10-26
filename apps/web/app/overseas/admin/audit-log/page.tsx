import AdminAuditLogPage from "@/components/AdminAuditLogPage";
import { PORTAL_NAV } from "@/lib/navigation";

// nehn-042 (DEC-SCOPE-289 A7): the Overseas Admin's audit log (the API keeps it to Overseas users' and system actions).
export default async function OverseasAdminAuditLogPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return <AdminAuditLogPage base="/overseas/admin/audit-log" role="overseas_admin" nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator" loginHref="/overseas/login" searchParams={await searchParams} />;
}
