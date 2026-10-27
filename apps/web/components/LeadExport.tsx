"use client";

import { XLSX_TYPE } from "@/components/ExportButtons";
import ReportDownloadButton from "@/components/ReportDownloadButton";

/** nehn-012 (DEC-SCOPE-298): "Download Excel" of the filtered lead list -- every page, the API's row cap, audit and throttle. A refusal
 *  (403, 422 too many rows, 429) is shown under the button, never saved as a file. The name carries today's India date, as the API's. */
export default function LeadExport({ url, total }: { url: string; total: number }) {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
  return (
    <div style={{ marginTop: 12 }}>
      <ReportDownloadButton url={url} label="Download Excel" filename={`leads-${today}.xlsx`} contentType={XLSX_TYPE} busyLabel="Preparing Excel…"
        hint={`All ${total.toLocaleString("en-IN")} matching ${total === 1 ? "lead" : "leads"}, with contact details. Downloads are recorded.`} />
    </div>
  );
}
