import { renderGlobalEducationPage } from "@/components/GlobalEducationPage";

// ENH-017 (DEC-SCOPE-036, SCR-SCH-038): the Coordinator's Global Education pipeline.
export default async function SchoolCoordinatorGlobalEducationPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return renderGlobalEducationPage("coordinator", await searchParams);
}
