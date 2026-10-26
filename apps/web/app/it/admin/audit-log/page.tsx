import AdminAuditLogPage from "@/components/AdminAuditLogPage";
import { PORTAL_NAV } from "@/lib/navigation";

// nehn-042 (DEC-SCOPE-288 A7): the IT Admin's audit log (the API keeps it to IT users' and system actions).
export default async function ItAdminAuditLogPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return <AdminAuditLogPage base="/it/admin/audit-log" role="it_admin" nav={PORTAL_NAV["it/admin"]} roleLabel="IT Administrator" loginHref="/it/login" searchParams={await searchParams} />;
}
