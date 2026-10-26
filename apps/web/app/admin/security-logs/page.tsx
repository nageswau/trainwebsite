import AdminAuditLogPage from "@/components/AdminAuditLogPage";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

// nehn-042 (DEC-SCOPE-289 A7): the Super Admin's searchable audit log (was the [module] table of the newest 500), with the Export panel.
export default async function SecurityLogsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return <AdminAuditLogPage base="/admin/security-logs" role="super_admin" nav={SUPER_ADMIN_NAV} roleLabel="Super Administrator" loginHref="/admin/login" searchParams={await searchParams} />;
}
