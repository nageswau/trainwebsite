import ArchivedStudentsPage, { pageOffset } from "@/components/ArchivedStudentsPage";

// ccrm-040 (DEC-SCOPE-275 AR7): the counselor's own archived students (read-only; the Overseas Admin restores).
export default async function Page({ searchParams }: { searchParams: Promise<{ offset?: string | string[] }> }) {
  return <ArchivedStudentsPage portal="counselor" offset={pageOffset((await searchParams).offset)} />;
}
