import ItAccountsPage from "@/components/ItAccountsPage";

// itc-017 (DEC-SCOPE-367 F1/F2): the accountant's (finance tier's) IT fee accounts workspace.
export default function ManagementItAccountsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return <ItAccountsPage shell="management" searchParams={searchParams} />;
}
