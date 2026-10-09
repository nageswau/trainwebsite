"use client";
import { type ReactNode, useEffect, useState } from "react";

import { DetailList, multiline } from "@/components/BdmOrganizationProfileDetails";
import RecruiterContractDocument from "@/components/RecruiterContractDocument";
import RecruiterContractForm from "@/components/RecruiterContractForm";
import RecruiterContractHistory from "@/components/RecruiterContractHistory";
import { sendRequest } from "@/lib/apiErrors";
import { display } from "@/lib/bdmOrganizations";
import { formatCalendarDate, formatSchoolDateTime } from "@/lib/formatDate";
import { type CompanyContracts, companyContractsUrl, type Contract, CONTRACT_STATUSES, feeText, isCompanyContracts } from "@/lib/recruiterContracts";
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
  return [
    ["Agreement type", display(c.agreement_type)],
    ["Contract start date", day(c.start_date)],
    ["Contract end date", day(c.end_date)],
    ["Recruitment fee", feeText(c)],
    ["Payment terms", multiline(c.payment_terms)],
    ["Replacement policy", multiline(c.replacement_policy)],
    ["Status changed", formatSchoolDateTime(c.status_changed_at, true)],
  ];
}

// rec-030 (spec §4): the company's contract / MoU -- status as text on a step list in source order (never colour alone; Expired is the
// last step, reached automatically), its terms, its two documents, its history, and the previous contracts. Edit, Start renewal and the
// uploads render from `permissions` / `can_start` only; the server enforces every rule. After each write the section re-reads the
// contracts and tells the page (`onChanged`), which re-reads the company's "Contract status" and announces the notice.
export default function RecruiterCompanyContract({ companyId, onChanged }: { companyId: string; onChanged: (notice: string) => void }) {
  const [data, setData] = useState<CompanyContracts | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const [mode, setMode] = useState<"view" | "edit" | "create">("view");
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (part: string) => `contract-card-${companyId}-${part}`;
  const current = data?.current ?? null;

  async function reload() {
    const outcome = await sendRequest(companyContractsUrl(companyId), { method: "GET" });
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
    setData((d) => ({ current: next, previous: d?.previous ?? [], can_start: false }));
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
      <RecruiterContractForm companyId={companyId} contract={mode === "edit" ? current : null} onCancel={close} onConflict={conflicted}
        onSaved={(c) => saved(c, mode === "edit" ? "Contract saved." : current ? "Renewal started." : "Contract started.")} />
    );
  } else if (current === null) {
    body = (
      <>
        <p className="muted">No contract yet.</p>
        {data.can_start && <button id={id("start")} type="button" className="btn small" onClick={() => setMode("create")}>Start contract</button>}
      </>
    );
  } else {
    body = (
      <>
        <p>Status: <span className="badge">{current.status_label}</span></p>
        <ol className="jny-steps" aria-label="Contract statuses">
          {steps(current).map((s) => (
            <li key={s.key} className={`jny-step jny-${s.state}`} aria-current={s.state === "current" ? "step" : undefined}>
              <span className="jny-glyph" aria-hidden="true">{GLYPH[s.state]}</span>
              <span className="jny-name">{s.label}</span>
              <span className="jny-state">{STATE[s.state]}</span>
            </li>
          ))}
        </ol>
        {current.status === "expired" && current.expired_on && (
          <p className="form-message">Expired on {formatCalendarDate(current.expired_on)} (the contract ended on {formatCalendarDate(current.end_date)}).</p>
        )}
        <div className="actions">
          {current.permissions.can_edit && <button id={id("edit")} type="button" className="btn secondary small" onClick={() => setMode("edit")}>Edit contract</button>}
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
    <section id="company-contract" className="action-card wide" aria-labelledby={id("title")}>
      <h3 id={id("title")}>Contract / MoU</h3>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {body}
      {mode === "view" && data && data.previous.length > 0 && (
        <details>
          <summary>Previous contracts ({data.previous.length})</summary>
          <ul style={{ margin: 0, paddingLeft: 18 }} aria-label="Previous contracts">
            {data.previous.map((p) => (
              <li key={p.id}>
                <span className="badge">{p.status_label}</span> {day(p.start_date)} – {day(p.end_date)} · {feeText(p)}
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
