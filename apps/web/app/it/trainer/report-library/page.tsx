import ReportLibraryPage from "@/components/ReportLibraryPage";
import { PORTAL_NAV } from "@/lib/navigation";

// nehn-009 (DEC-SCOPE-303): a trainer's report library -- the API keeps every row to the trainer's own batches.
export default function TrainerReportLibraryPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return (
    <ReportLibraryPage roles={["trainer"]} nav={PORTAL_NAV["it/trainer"]} roleLabel="Trainer" loginHref="/it/login"
      basePath="/it/trainer/report-library" searchParams={searchParams} />
  );
}
