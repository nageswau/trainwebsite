import ItReportsPage from "@/components/ItReportsPage";

// itc-032 (DEC-SCOPE-369 R6): management's IT reports (operational tier; the accountant sees Revenue only).
export default function ManagementItReportsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return <ItReportsPage shell="management" searchParams={searchParams} />;
}
