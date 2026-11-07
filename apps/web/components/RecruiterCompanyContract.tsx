"use client";
import { type ReactNode, useEffect, useState } from "react";

import { DetailList, multiline } from "@/components/BdmOrganizationProfileDetails";
import RecruiterContractDocument from "@/components/RecruiterContractDocument";
import RecruiterContractForm from "@/components/RecruiterContractForm";
import RecruiterContractHistory from "@/components/RecruiterContractHistory";
import { sendRequest } from "@/lib/apiErrors";
import { display } from "@/lib/bdmOrganizations";
import { formatCalendarDate, formatSchoolDateTime } from "@/lib/formatDate";
import { type CompanyContracts, companyContractsUrl, type Contract, type ContractParty, CONTRACT_STATUSES, directionText, feeText, isCompanyContracts } from "@/lib/recruiterContracts";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Step = "done" | "current" | "upcoming";
const GLYPH: Record<Step, string> = { done: "✓", current: "•", upcoming: "–" };
const STATE: Record<Step, string> = { done: "Done", current: "Current", upcoming: "Upcoming" };
const UNABLE = "Unable to load the contract.";
const REFRESH_FAILED = "Unable to show the latest contract. Reload the page.";

function steps(c: Contract): { key: string; label: string; state: Step }[] {
  const at = CONTRACT_STATUSES.findIndex((s) => s.key === c.status);
  return CONTRACT_STATUSES.map((s, i) => ({ ...s, state: i < at ? "done" : i === at ? "current" : "upcoming" }));
}

const day = (value: string | null) => (value ? formatCalendarDate(value) : display(value));

function details(c: Contract): [string, ReactNode][] {
  // pob-001 (DEC-SCOPE-403 C5): without `commercials.client.view` the API leaves the terms out; so do the rows
  const terms: [string, ReactNode][] = c.permissions.can_view_terms
    ? [["Recruitment fee", feeText(c)], ["Payment terms", multiline(c.payment_terms ?? null)], ["Replacement policy", multiline(c.replacement_policy ?? null)]]
    : [];
  if (c.party === "vendor" && c.permissions.can_view_terms) terms.unshift(["Who pays whom", directionText(c.direction)], ["Confidentiality terms", multiline(c.confidentiality_terms ?? null)]); // pob-010 V8
  return [
    ["Agreement type", display(c.agreement_type)],
    ["Contract start date", day(c.start_date)],
    ["Contract end date", day(c.end_date)],
    ...terms,
    ["Status changed", formatSchoolDateTime(c.status_changed_at, true)],
  ];
}

// rec-030 (spec §4): the company's contract / MoU -- status as text on a step list in source order (never colour alone; Expired is the
// last step, reached automatically), its terms, its two documents, its history, and the previous contracts. Edit, Start renewal and the
// uploads render from `permissions` / `can_start` only; the server enforces every rule. After each write the section re-reads the
// contracts and tells the page (`onChanged`), which re-reads the company's "Contract status" and announces the notice.
// pob-010 V8: `party="vendor"` is the same section for the vendor agreement, under its own ids.
export default function RecruiterCompanyContract({ companyId, onChanged, party = "client" }: { companyId: string; onChanged: (notice: string) => void; party?: ContractParty }) {
  const [data, setData] = useState<CompanyContracts | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const [mode, setMode] = useState<"view" | "edit" | "create">("view");
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const vendor = party === "vendor";
  const noun = vendor ? "agreement" : "contract";
  const Noun = vendor ? "Agreement" : "Contract";
  const id = (part: string) => `contract-card-${companyId}-${party}-${part}`;
  const current = data?.current ?? null;

  async function reload() {
    const outcome = await sendRequest(companyContractsUrl(companyId, party), { method: "GET" });
    if (outcome.ok && isCompanyContracts(outcome.data)) {
      setData(outcome.data);
      return setState("ready");
    }
    if (data === null) setState("failed");
    else setFailure(REFRESH_FAILED);
  }

  useEffect(() => {
    void reload();
  }, [companyId]); // eslint-disable-line react-hooks/exhaustive-deps -- load once per company; writes call reload()

  function saved(next: Contract, text: string) {
    setMode("view");
    setFailure(null);
    setData((d) => ({
      current: next, previous: d?.previous ?? [], can_start: false,
      can_view_terms: next.permissions.can_view_terms, can_edit_terms: d?.can_edit_terms ?? next.permissions.can_edit_terms,
    }));
    onChanged(text);
    focus(id("edit"));
    void reload();
  }

  function conflicted(text: string) {
    setMode("view");
    setFailure(text);
    void reload();
  }

  const close = () => {
    setMode("view");
    focus(id(current ? "edit" : "start"));
  };

  let body: ReactNode;
  if (state === "loading") {
    body = <p className="muted" aria-live="polite">Loading…</p>;
  } else if (state === "failed" || data === null) {
    body = (
      <div role="alert">
        <p className="form-error">{UNABLE}</p>
        <button type="button" className="btn secondary small" onClick={() => { setState("loading"); void reload(); }}>Try again</button>
      </div>
    );
  } else if (mode !== "view") {
    body = (
      <RecruiterContractForm companyId={companyId} party={party} contract={mode === "edit" ? current : null} onCancel={close} onConflict={conflicted}
        terms={mode === "edit" ? !!current?.permissions.can_edit_terms : data.can_edit_terms}
        onSaved={(c) => saved(c, mode === "edit" ? `${Noun} saved.` : current ? "Renewal started." : `${Noun} started.`)} />
    );
  } else if (current === null) {
    body = (
      <>
        <p className="muted">No {noun} yet.</p>
        {data.can_start && <div className="actions"><button id={id("start")} type="button" className="btn small" onClick={() => setMode("create")}>Start {noun}</button></div>}
      </>
    );
  } else {
    body = (
      <>
        <p>Status: <span className="badge">{current.status_label}</span></p>
        <ol className="jny-steps" aria-label={`${Noun} statuses`}>
          {steps(current).map((s) => (
            <li key={s.key} className={`jny-step jny-${s.state}`} aria-current={s.state === "current" ? "step" : undefined}>
              <span className="jny-glyph" aria-hidden="true">{GLYPH[s.state]}</span>
              <span className="jny-name">{s.label}</span>
              <span className="jny-state">{STATE[s.state]}</span>
            </li>
          ))}
        </ol>
        {current.status === "expired" && current.expired_on && (
          <p className="form-message">Expired on {formatCalendarDate(current.expired_on)} (the {noun} ended on {formatCalendarDate(current.end_date)}).</p>
        )}
        <div className="actions">
          {current.permissions.can_edit && <button id={id("edit")} type="button" className="btn secondary small" onClick={() => setMode("edit")}>Edit {noun}</button>}
          {current.permissions.can_renew && data.can_start && (
            <button id={id("renew")} type="button" className="btn small" onClick={() => setMode("create")}>Start renewal</button>
          )}
        </div>
        <DetailList rows={details(current)} />
        <RecruiterContractDocument companyId={companyId} contract={current} kind="contract" onUploaded={(c) => saved(c, "Contract document saved.")} />
        <RecruiterContractDocument companyId={companyId} contract={current} kind="mou" onUploaded={(c) => saved(c, "MoU saved.")} />
        <RecruiterContractHistory key={current.updated_at} contract={current} />
      </>
    );
  }

  return (
    <section id={vendor ? "company-vendor-agreement" : "company-contract"} className="action-card wide" aria-labelledby={id("title")}>
      <h3 id={id("title")}>{vendor ? "Vendor agreement" : "Contract / MoU"}</h3>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {body}
      {mode === "view" && data && data.previous.length > 0 && (
        <details>
          <summary>Previous {noun}s ({data.previous.length})</summary>
          <ul style={{ margin: 0, paddingLeft: 18 }} aria-label={`Previous ${noun}s`}>
            {data.previous.map((p) => (
              <li key={p.id}>
                <span className="badge">{p.status_label}</span> {day(p.start_date)} – {day(p.end_date)}{p.permissions.can_view_terms && ` · ${feeText(p)}`}
                <RecruiterContractDocument companyId={companyId} contract={p} kind="contract" onUploaded={() => undefined} />
                <RecruiterContractDocument companyId={companyId} contract={p} kind="mou" onUploaded={() => undefined} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
