import StudentSearchPage from "@/components/StudentSearchPage";
import { PORTAL_NAV } from "@/lib/navigation";

// nehn-041 (DEC-SCOPE-291 S10): the Overseas Admin's student search (overseas students and agency students with no login).
export default async function OverseasAdminStudentSearchPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return <StudentSearchPage base="/overseas/admin/student-search" role="overseas_admin" nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator" loginHref="/overseas/login" searchParams={await searchParams} />;
}
