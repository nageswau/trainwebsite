"use client";

import { useId } from "react";
import ReportDownloadButton from "@/components/ReportDownloadButton";

export const XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

// ccrm-035 (DEC-SCOPE-268 E1): Download CSV and Download Excel for one export `url` (its filters already in the query); the API adds
// `format`, checks the role, audits and throttles. `label` names the group, so six "Download CSV" buttons on one page stay distinct.
// Browser QA-01: the saved name carries today's India date (en-CA formats it YYYY-MM-DD), as the API's own filename does (E9).
export default function ExportButtons({ url, filename, label }: { url: string; filename: string; label: string }) {
  const join = url.includes("?") ? "&" : "?";
  const name = `${filename}-${new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date())}`;
  return <Pair csv={`${url}${join}format=csv`} xlsx={`${url}${join}format=xlsx`} name={name} label={label} />;
}

// nehn-004 (DEC-SCOPE-280 X6): the same pair for the report routes whose format is the path's extension -- a `….csv` URL (filters in
// its query) and its `….xlsx` twin, saved under the CSV's filename with the Excel extension. `hint` describes the whole group.
export function SpreadsheetButtons({ csvUrl, filename, label, hint }: { csvUrl: string; filename: string; label: string; hint?: string }) {
  const xlsx = csvUrl.replace(/\.csv(?=\?|$)/, ".xlsx");
  return <Pair csv={csvUrl} xlsx={xlsx} name={filename.replace(/\.csv$/, "")} label={label} hint={hint} />;
}

function Pair({ csv, xlsx, name, label, hint }: { csv: string; xlsx: string; name: string; label: string; hint?: string }) {
  const hintId = useId();
  const group = (
    <div className="export-buttons" role="group" aria-label={label} aria-describedby={hint ? hintId : undefined}>
      <ReportDownloadButton url={csv} label="Download CSV" filename={`${name}.csv`} contentType="text/csv" busyLabel="Preparing CSV…" />
      <ReportDownloadButton url={xlsx} label="Download Excel" filename={`${name}.xlsx`} contentType={XLSX_TYPE} busyLabel="Preparing Excel…" />
    </div>
  );
  // Browser QA-01: one box with its hint, so a flex toolbar never pulls the hint away from the buttons.
  return hint ? <div>{group}<p id={hintId} className="field-hint">{hint}</p></div> : group;
}
