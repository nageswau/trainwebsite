"use client";
import { type ReactNode, useState } from "react";

import BdmConfirm from "@/components/BdmConfirm";
import BdmMouDocument from "@/components/BdmMouDocument";
import BdmMouForm from "@/components/BdmMouForm";
import BdmMouHistory from "@/components/BdmMouHistory";
import BdmMouPrevious from "@/components/BdmMouPrevious";
import { DetailList, multiline } from "@/components/BdmOrganizationProfileDetails";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import { isMouBody, isOrgMou, type Mou, MOU_LADDER, mouConflict, type OrgMou, orgMouUrl } from "@/lib/bdmMous";
import { display } from "@/lib/bdmOrganizations";
import { formatCalendarDate, formatSchoolDateTime } from "@/lib/formatDate";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Step = "done" | "current" | "upcoming";
const GLYPH: Record<Step, string> = { done: "✓", current: "•", upcoming: "–" };
const STATE: Record<Step, string> = { done: "Done", current: "Current", upcoming: "Upcoming" };
const UNABLE = "Unable to load the MoU.";
const REFRESH_FAILED = "Unable to show the latest MoU. Reload the page.";

function steps(m: Mou): { key: string; label: string; state: Step }[] {
  const at = m.status === "expired" ? MOU_LADDER.length : MOU_LADDER.findIndex((s) => s.key === m.status);
  return MOU_LADDER.map((s, i) => ({ ...s, state: at < 0 ? "upcoming" : i < at ? "done" : i === at ? "current" : "upcoming" }));
}

function outcome(m: Mou): string | null {
  if (m.status === "expired") return `Expired on ${formatCalendarDate(m.expired_on)} (valid until ${formatCalendarDate(m.valid_until)}).`;
  return m.status === "rejected" ? "Rejected." : null;
}

const day = (value: string | null) => (value ? formatCalendarDate(value) : display(value));

// bdm-005 (spec §8): the organization's current MoU -- status as text on a step list (never colour alone), its dates and notes, and
// for the assigned BDM / super_admin (permissions) Start, Edit and Start renewal. The server enforces every rule; after each write the
// card re-reads the MoU, and a status change -- a Signed that moved the pipeline (D28), or one that changes whether onboarding can be
// requested (bdm-018) -- asks the page to re-read the organization (`onPipelineChanged`).
// Success notices go to the page's one live region (`onNotice`).
export default function BdmOrganizationMou({ orgId, initial, onNotice, onPipelineChanged, readOnlyNote }: {
  orgId: string; initial: OrgMou | null; onNotice: (text: string) => void; onPipelineChanged: () => void;
  readOnlyNote?: string; // QA5-06: why the card offers no writes (a Lost or archived organization), from the page
}) {
  const [data, setData] = useState<OrgMou | null>(initial);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<"view" | "edit" | "create">("view");
  const [renewing, setRenewing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (part: string) => `mou-card-${orgId}-${part}`;
  const current = data?.current ?? null;

  async function reload() {
    setLoading(true);
    const outcome = await sendRequest(orgMouUrl(orgId), { method: "GET" });
    setLoading(false);
    if (outcome.ok && isOrgMou(outcome.data)) return setData(outcome.data);
    if (data !== null) setFailure(REFRESH_FAILED); // a first load that fails again keeps its own "Try again"
  }

  function saved(next: Mou, text: string) {
    const before = current;
    const moved = next.status === "signed" && before?.status !== "signed";
    setMode("view");
    setRenewing(false);
    setFailure(null);
    setData({ current: next, can_start: false });
    onNotice(moved && before?.pipeline_on_sign && !next.pipeline_on_sign ? `${text} The pipeline moved to ${before.pipeline_on_sign.label}.` : text);
    if (next.status !== before?.status) onPipelineChanged(); // bdm-018: Signed / Active also decide whether onboarding can be requested
    focus(id("edit"));
    void reload();
  }

  function conflicted(text: string) {
    setMode("view");
    setFailure(text);
    void reload();
  }

  async function renew() {
    setBusy(true);
    const outcome = await sendJson(orgMouUrl(orgId), "POST", {});
    setBusy(false);
    if (outcome.ok && isMouBody(outcome.data)) return saved(outcome.data.mou, "Renewal started.");
    setRenewing(false);
    conflicted(outcome.ok ? "Unable to start the renewal." : (mouConflict(outcome.detail) ?? outcome.message));
  }

  const close = () => {
    setMode("view");
    focus(id(current ? "edit" : "start"));
  };

  let body: ReactNode;
  if (data === null) {
    body = (
      <div role="alert">
        <p className="form-error">{UNABLE}</p>
        <button type="button" className="btn secondary small" onClick={() => void reload()} disabled={loading}>{loading ? "Loading…" : "Try again"}</button>
      </div>
    );
  } else if (mode !== "view") {
    body = <BdmMouForm orgId={orgId} mou={mode === "edit" ? current : null} onSaved={(m) => saved(m, mode === "edit" ? "MoU saved." : "MoU started.")} onCancel={close} onConflict={conflicted} />;
  } else if (current === null) {
    body = (
      <>
        <p className="muted">No MoU yet.</p>
        {data.can_start && <button id={id("start")} type="button" className="btn small" onClick={() => setMode("create")}>Start MoU</button>}
      </>
    );
  } else {
    const end = outcome(current);
    const rows: [string, ReactNode][] = [
      ["Reference", display(current.reference)],
      ["Proposal sent", day(current.proposal_sent_on)],
      ["Signed on", day(current.signed_on)],
      ["Valid from", day(current.valid_from)],
      ["Valid until (renewal date)", day(current.valid_until)],
      ["Notes", multiline(current.notes)],
      ["Status changed", formatSchoolDateTime(current.status_changed_at, true)],
    ];
    body = (
      <>
        <p>Status: <span className="badge">{current.status_label}</span></p>
        <ol className="jny-steps" aria-label="MoU statuses">
          {steps(current).map((s) => (
            <li key={s.key} className={`jny-step jny-${s.state}`} aria-current={s.state === "current" ? "step" : undefined}>
              <span className="jny-glyph" aria-hidden="true">{GLYPH[s.state]}</span>
              <span className="jny-name">{s.label}</span>
              <span className="jny-state">{STATE[s.state]}</span>
            </li>
          ))}
        </ol>
        {end && <p className="form-message">{end}</p>}
        {/* QA5-05: the actions sit with the status they change, before the details */}
        <div className="actions">
          {current.permissions.can_edit && <button id={id("edit")} type="button" className="btn secondary small" onClick={() => setMode("edit")}>Edit MoU</button>}
          {current.permissions.can_renew && data.can_start && !renewing && (
            <button id={id("renew")} type="button" className="btn small" onClick={() => setRenewing(true)}>Start renewal</button>
          )}
        </div>
        {renewing && (
          <BdmConfirm label="Confirm renewal" className="action-card" confirmText="Yes, start renewal" busyText="Starting…" busy={busy} onConfirm={() => void renew()} onCancel={() => { setRenewing(false); focus(id("renew")); }}>
            Start a new MoU for this organization? The current one is kept in its history.
          </BdmConfirm>
        )}
        <DetailList rows={rows} />
        <BdmMouDocument orgId={orgId} mou={current} onUploaded={(m) => saved(m, "Document saved.")} />
        <BdmMouHistory key={current.updated_at} mou={current} />
        <BdmMouPrevious orgId={orgId} />
      </>
    );
  }

  return (
    <section className="action-card wide" aria-label="MoU">
      <h3>MoU</h3>
      {readOnlyNote && <p className="muted">{readOnlyNote}</p>}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {body}
    </section>
  );
}
