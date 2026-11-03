import ItReportsPage from "@/components/ItReportsPage";

// itc-032 (DEC-SCOPE-369 R6): the IT Admin's view of the management IT reports.
export default function ItAdminManagementReportsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return <ItReportsPage shell="it" searchParams={searchParams} />;
}
