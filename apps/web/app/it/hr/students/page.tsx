import HrStudentsPage from "@/components/HrStudentsPage";

// nehn-017 (DEC-SCOPE-310): HR's read-only student list (a static route wins over [section]).
export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return <HrStudentsPage searchParams={await searchParams} />;
}
