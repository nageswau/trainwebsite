"use client";
import { useState } from "react";

import { multiline } from "@/components/BdmOrganizationProfileDetails";
import { ApprovalDecision, SubmittedLine } from "@/components/RequirementApproval";
import { sendJson } from "@/lib/apiErrors";
import { type ApprovalRow, type ApprovalSettings, APPROVALS_URL, type JobSource, SOURCE_LABEL } from "@/lib/recruiterRequirements";

// hrc-007 (DEC-SCOPE-380 A9): the approver's queue -- every job waiting for approval, oldest first. A decided row leaves the list (the
// API's answer is the truth; nothing is re-filtered here). Own jobs show why they cannot be decided. super_admin also sets which job
// sources need approval (A4).
const SOURCES: JobSource[] = ["employer", "recruiter", "legacy"];

function Settings({ initial }: { initial: ApprovalSettings }) {
  const [settings, setSettings] = useState(initial.settings);
  const [busy, setBusy] = useState<JobSource | null>(null);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);

  async function toggle(source: JobSource, required: boolean) {
    const previous = settings;
    setSettings({ ...previous, [source]: required }); // QA-01: the box follows the click at once; the server's answer then wins
    setBusy(source);
    setMessage(null);
    const outcome = await sendJson(`${APPROVALS_URL}/settings`, "PUT", { [source]: required });
    setBusy(null);
    const next = outcome.ok ? (outcome.data as ApprovalSettings | null)?.settings : undefined;
    if (next) {
      setSettings(next);
      setMessage({ text: `${SOURCE_LABEL[source]} jobs ${required ? "now need" : "no longer need"} approval.`, failed: false });
    } else {
      setSettings(previous);
      setMessage({ text: outcome.ok ? "Unable to save the setting." : outcome.message, failed: true });
    }
  }

  return (
    <section className="action-card wide" aria-labelledby="approval-settings">
      <h3 id="approval-settings">Which jobs need approval</h3>
      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <legend className="muted">Jobs from these sources wait for approval before they first open. Turning one off never opens jobs already waiting.</legend>
        {SOURCES.map((source) => (
          <label key={source} style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
            <input type="checkbox" checked={settings[source]} disabled={!initial.can_edit || busy !== null}
              onChange={(e) => void toggle(source, e.target.checked)} />
            {SOURCE_LABEL[source]} jobs
          </label>
        ))}
      </fieldset>
      {!initial.can_edit && <p className="muted" style={{ margin: 0 }}>Only a super admin can change these settings.</p>}
      <div role="status" aria-live="polite" className={message ? (message.failed ? "form-error" : "form-message") : undefined}>
        {message?.text}
      </div>
    </section>
  );
}

export default function RequirementApprovalQueue({ rows: initial, total, settings }: { rows: ApprovalRow[]; total: number; settings: ApprovalSettings }) {
  const [rows, setRows] = useState(initial);
  const [notice, setNotice] = useState<string | null>(null);
  const decided = initial.length - rows.length;

  return (
    <>
      <div id="approval-notice" tabIndex={-1} role="status" aria-live="polite" className={notice ? "form-message" : undefined}>
        {notice}
      </div>
      <section className="action-card wide" aria-labelledby="approval-queue">
        <h3 id="approval-queue">Waiting for approval ({total - decided})</h3>
        {rows.length === 0 ? (
          <p style={{ margin: 0 }}>No job requirements are waiting for approval.</p>
        ) : (
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 16 }}>
            {rows.map((row) => (
              <li key={row.id} className="action-card" style={{ margin: 0 }} aria-labelledby={`approval-${row.id}-title`}>
                <div className="eyebrow">{row.code}</div>
                <h4 id={`approval-${row.id}-title`} style={{ margin: "4px 0" }}>
                  {row.title} <span className="badge">{SOURCE_LABEL[row.source]}</span>
                </h4>
                <p style={{ margin: 0 }}>
                  {row.company.name} · {row.location}
                  {row.vacancies != null && ` · ${row.vacancies} ${row.vacancies === 1 ? "vacancy" : "vacancies"}`}
                </p>
                <SubmittedLine by={row.submitted_by} at={row.submitted_at} />
                {row.description && <div style={{ marginTop: 8 }}>{multiline(row.description)}</div>}
                {row.can_decide ? (
                  <ApprovalDecision requirementId={row.id} title={row.code} onDone={(_, text) => {
                    setRows((current) => current.filter((r) => r.id !== row.id));
                    setNotice(text);
                    document.getElementById("approval-notice")?.focus();
                  }} />
                ) : (
                  <p className="muted" style={{ margin: "8px 0 0" }}>This is your own job requirement, so another approver must decide it.</p>
                )}
              </li>
            ))}
          </ul>
        )}
        {total > initial.length && <p className="muted">Showing the oldest {initial.length} of {total}. Decide these to see the rest.</p>}
      </section>
      <Settings initial={settings} />
    </>
  );
}
