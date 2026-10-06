"use client";

import { ChangeEvent, FormEvent, useCallback, useEffect, useRef, useState } from "react";

import BulkColumnReference from "@/components/BulkColumnReference";
import { detailMessage } from "@/lib/apiErrors";
import { newIdempotencyKey } from "@/lib/idempotencyKey";
import { SOURCE_LABEL, activeCampaigns, type Campaign } from "@/lib/telecallerCatalogue";
import { IMPORTS_URL, IMPORT_COLUMNS, IMPORT_MAX_BYTES, IMPORT_MAX_ROWS, IMPORT_TEMPLATE_URL, RESULT_LABEL, importCounts, type ImportReport } from "@/lib/telecallerImport";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

const FILE_ID = "lead-import-file";
const NETWORK_ERROR = "The connection dropped. Import again — the same file won't be added twice.";
const BUSY_MESSAGE = "Importing — checking each row for duplicates and distributing new leads.";

function precheck(campaignId: string, file: File | undefined): string | null {
  if (!campaignId) return "Choose a campaign first.";
  if (!file) return "Choose a filled-in CSV file first.";
  if (!file.name.toLowerCase().endsWith(".csv")) return "Choose a .csv file.";
  if (file.size > IMPORT_MAX_BYTES) return "The file is larger than 1 MB.";
  return null;
}

function summary(report: ImportReport): Feedback {
  if (report.created_count + report.attached_count === 0) return { text: "No leads were imported. Fix the rows below and upload again.", tone: "error" };
  if (report.rejected_count === 0) return { text: `${importCounts(report)}.`, tone: "success" };
  return { text: `${importCounts(report)}. Fix the rejected rows and upload just those.`, tone: "warning" };
}

function ImportResult({ report }: { report: ImportReport }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), [report]);
  const note = summary(report);
  return (
    <div style={{ marginTop: 16 }}>
      <h4 ref={heading} tabIndex={-1}>Import result</h4>
      <p className={toneClass[note.tone]}>{note.text}</p>
      <div className="table-wrap">
        <table className="table bulk-report">
          <thead>
            <tr><th>Row</th><th>Result</th><th>Lead ID</th><th>Detail</th></tr>
          </thead>
          <tbody>
            {report.rows.map((r) => (
              <tr key={r.row_number}>
                <td data-label="Row">{r.row_number}</td>
                <td data-label="Result">{RESULT_LABEL[r.status]}</td>
                <td data-label="Lead ID">{r.lead_code ?? "-"}</td>
                <td data-label="Detail">{r.error ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// tel-006 (IM1): pick an active campaign (its source and product tag every lead), download the template, upload. Each row is created,
// added to the existing lead of a known person, or rejected with its line. The Idempotency-Key belongs to the chosen file and campaign:
// a retry after a dropped connection replays the first result instead of importing twice; any new choice is a new upload.
export default function TelecallerLeadImportPanel({ onImported }: { onImported?: () => void }) {
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null);
  const [campaignsFailed, setCampaignsFailed] = useState(false);
  const [campaignId, setCampaignId] = useState("");
  const [division, setDivision] = useState("");
  const [chosen, setChosen] = useState<{ file: File; key: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const inFlight = useRef(false); // `busy` disables the button only after a re-render; a double click must not upload twice
  const input = useRef<HTMLInputElement>(null);

  const loadCampaigns = useCallback(() => {
    setCampaignsFailed(false);
    activeCampaigns().then(setCampaigns).catch(() => setCampaignsFailed(true));
  }, []);
  useEffect(loadCampaigns, [loadCampaigns]);

  const selected = campaigns?.find((c) => c.id === campaignId);
  const needsDivision = selected?.product.group === "other";
  const renewKey = () => setChosen((c) => (c ? { ...c, key: newIdempotencyKey() } : c));

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    setChosen(file ? { file, key: newIdempotencyKey() } : null);
    setError(null);
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    const problem = precheck(campaignId, chosen?.file);
    if (problem || !chosen) {
      setError(problem);
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setError(null);
    setReport(null);
    const body = new FormData();
    body.append("file", chosen.file);
    body.append("campaign_id", campaignId);
    if (needsDivision && division) body.append("division", division);
    try {
      const response = await fetch(IMPORTS_URL, { method: "POST", headers: { "Idempotency-Key": chosen.key }, body });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(detailMessage(data.detail, "Unable to import this file."));
        return;
      }
      setReport(data);
      setChosen(null);
      if (input.current) input.current.value = "";
      onImported?.();
    } catch {
      setError(NETWORK_ERROR);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <div className="action-card lead-import">
      <h3>Import leads (CSV)</h3>
      <p className="muted">Add the leads from an ad platform or an event in one go. A person who is already a lead gets this enquiry added to their lead instead of a duplicate; new leads are distributed like any other.</p>
      <form className="form" onSubmit={upload} aria-busy={busy} noValidate>
        <h4>1. Choose the campaign</h4>
        <div className="field">
          <label htmlFor="lead-import-campaign">Campaign</label>
          {campaignsFailed ? (
            <p className="form-error" role="alert">Campaigns could not be loaded. <button type="button" className="btn secondary" onClick={loadCampaigns}>Retry</button></p>
          ) : (
            <select id="lead-import-campaign" value={campaignId} disabled={busy || !campaigns} aria-describedby="lead-import-campaign-help"
              onChange={(e) => { setCampaignId(e.target.value); setDivision(""); renewKey(); }}>
              <option value="">{campaigns ? "Choose a campaign" : "Loading campaigns…"}</option>
              {campaigns?.map((c) => <option key={c.id} value={c.id}>{c.name} — {SOURCE_LABEL[c.source] ?? c.source} → {c.product.name}</option>)}
            </select>
          )}
          <p id="lead-import-campaign-help" className="muted field-help">Every lead in the file gets this campaign, its source and its product. Only active campaigns are listed.</p>
        </div>
        {needsDivision && (
          <div className="field">
            <label htmlFor="lead-import-division">Division</label>
            <select id="lead-import-division" value={division} disabled={busy} aria-describedby="lead-import-division-help"
              onChange={(e) => { setDivision(e.target.value); renewKey(); }}>
              <option value="">The product&apos;s team</option>
              <option value="it">IT</option>
              <option value="overseas">Overseas</option>
            </select>
            <p id="lead-import-division-help" className="muted field-help">Needed only when this product has no team.</p>
          </div>
        )}
        <h4>2. Download the template</h4>
        <a className="btn secondary" href={IMPORT_TEMPLATE_URL} download>Download the template (.csv)</a>
        <BulkColumnReference columns={IMPORT_COLUMNS} />
        <h4 style={{ marginTop: 16 }}>3. Upload the filled-in file</h4>
        <div className="field">
          <label htmlFor={FILE_ID}>Filled-in leads file</label>
          <input ref={input} id={FILE_ID} type="file" accept=".csv,text/csv" onChange={chooseFile} disabled={busy} aria-describedby={`${FILE_ID}-help`} />
          <p id={`${FILE_ID}-help`} className="muted field-help">CSV, up to 1 MB and {IMPORT_MAX_ROWS} leads. One lead per row; name and phone are required.</p>
        </div>
        <button className="btn" disabled={busy}>{busy ? "Importing…" : "Import leads"}</button>
      </form>
      <p className="visually-hidden" role="status" aria-live="polite">{busy ? BUSY_MESSAGE : ""}</p>
      {error && <div className="form-error" role="alert" style={{ marginTop: 8 }}>{error}</div>}
      {report && <ImportResult report={report} />}
    </div>
  );
}
