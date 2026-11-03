import ItAccountsPage from "@/components/ItAccountsPage";

// itc-017 (DEC-SCOPE-368 F2): the IT Admin's accounts workspace.
export default function ItAdminAccountsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return <ItAccountsPage shell="it" searchParams={searchParams} />;
}
