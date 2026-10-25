import ReportDownloadButton from "@/components/ReportDownloadButton";

export const XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

// ccrm-035 (DEC-SCOPE-268 E1): Download CSV and Download Excel for one export `url` (its filters already in the query); the API adds
// `format`, checks the role, audits and throttles. `label` names the group, so six "Download CSV" buttons on one page stay distinct.
// Browser QA-01: the saved name carries today's India date (en-CA formats it YYYY-MM-DD), as the API's own filename does (E9).
export default function ExportButtons({ url, filename, label }: { url: string; filename: string; label: string }) {
  const join = url.includes("?") ? "&" : "?";
  const name = `${filename}-${new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date())}`;
  return (
    <div className="export-buttons" role="group" aria-label={label}>
      <ReportDownloadButton url={`${url}${join}format=csv`} label="Download CSV" filename={`${name}.csv`} contentType="text/csv" busyLabel="Preparing CSV…" />
      <ReportDownloadButton url={`${url}${join}format=xlsx`} label="Download Excel" filename={`${name}.xlsx`} contentType={XLSX_TYPE} busyLabel="Preparing Excel…" />
    </div>
  );
}
