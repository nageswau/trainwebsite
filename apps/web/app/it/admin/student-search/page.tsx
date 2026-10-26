import StudentSearchPage from "@/components/StudentSearchPage";
import { PORTAL_NAV } from "@/lib/navigation";

// nehn-041 (DEC-SCOPE-291 S10): the IT Admin's student search (the API keeps it to IT students).
export default async function ItAdminStudentSearchPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return <StudentSearchPage base="/it/admin/student-search" role="it_admin" nav={PORTAL_NAV["it/admin"]} roleLabel="IT Administrator" loginHref="/it/login" searchParams={await searchParams} />;
}
