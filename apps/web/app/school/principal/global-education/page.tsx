import { renderGlobalEducationPage } from "@/components/GlobalEducationPage";

// ENH-017 (DEC-SCOPE-036, SCR-SCH-038): the Principal's read-only Global Education pipeline -- same data as the Coordinator's.
export default async function SchoolPrincipalGlobalEducationPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return renderGlobalEducationPage("principal", await searchParams);
}
