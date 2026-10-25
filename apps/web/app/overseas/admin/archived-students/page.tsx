import ArchivedStudentsPage, { pageOffset } from "@/components/ArchivedStudentsPage";

// ccrm-040 (DEC-SCOPE-275 AR7): every archived overseas student, with Restore.
export default async function Page({ searchParams }: { searchParams: Promise<{ offset?: string | string[] }> }) {
  return <ArchivedStudentsPage portal="admin" offset={pageOffset((await searchParams).offset)} />;
}
