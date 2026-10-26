import StudentSearchPage from "@/components/StudentSearchPage";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

// nehn-041 (DEC-SCOPE-291 S10): the Super Admin's unified student search -- every kind of student.
export default async function SuperAdminStudentSearchPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return <StudentSearchPage base="/admin/student-search" role="super_admin" nav={SUPER_ADMIN_NAV} roleLabel="Super Administrator" loginHref="/admin/login" searchParams={await searchParams} />;
}
