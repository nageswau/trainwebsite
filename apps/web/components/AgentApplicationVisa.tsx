"use client";

import Link from "next/link";
import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import AgentVisaDetailsForm, { DETAIL_FIELDS, VisaDetails } from "./AgentVisaDetailsForm";
import { SIGN_IN_PATH } from "@/lib/activityFeedback";
import { sendJson } from "@/lib/apiErrors";
import {
  AgentApplicationDetail,
  APPLICATIONS_URL,
  canStartVisa,
  checklistStatusLabel,
  nextVisaStages,
  SECTION_EXPIRED as EXPIRED,
  SECTION_SERVER_ERROR as SERVER_ERROR,
  stageLabel,
  VISA_DECISION_LABELS,
  VISA_DECISIONS,
  VisaDecision,
  visaChecklistEditable,
} from "@/lib/agentApplications";
import { fieldErrors } from "@/lib/agentStudents";
import { formatDateTimeIn, viewerTimeZone } from "@/lib/formatDate";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Props = {
  detail: AgentApplicationDetail;
  onSaved: (d: AgentApplicationDetail, message: string) => void;
  onFailed: (message: string, status?: number) => void;
  onOpenChange?: (open: boolean) => void;
};
type Mode = "details" | "move" | "decide" | null;

const FIELDS = [...DETAIL_FIELDS, "to_stage", "decision"] as const;
type Field = (typeof FIELDS)[number];

// AGN-012 (DEC-SCOPE-057): Step 8. Master and Staff start the visa case from an offer onwards, keep its dates and document checklist,
// move it forward (a skip is confirmed) and record the authority's decision once (confirmed; final). The displayed stage travels as
// `expected_stage`, so a stale screen gets a 409 and the detail reloads. Read-only for a withdrawn/archived/enrolled application.
export default function AgentApplicationVisa({ detail, onSaved, onFailed, onOpenChange }: Props) {
  const visa = detail.visa ?? null;
  const [mode, setMode] = useState<Mode>(null);
  const [target, setTarget] = useState("");
  const [decision, setDecision] = useState<VisaDecision | "">("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ text: string; expired?: boolean } | null>(null);
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const inFlight = useRef(false); // a same-tick second click sends nothing
  const focusAfter = useFocusAfterRender();
  const id = (part: string) => `visa-${part}-${detail.id}`;

  const writable = !detail.read_only_reason && detail.status !== "enrolled" && !visa?.decision;
  if (!visa && (!writable || !canStartVisa(detail.status))) return null;
  const forward = visa ? nextVisaStages(visa.stage) : [];
  const skipped = forward.indexOf(target);

  function open(next: Exclude<Mode, null>, focus: string) {
    setMode(next);
    onOpenChange?.(true); // the detail hides Enrollment and the status form while this form is open
    focusAfter(id(focus));
  }
  function reset() {
    setMode(null);
    setTarget("");
    setDecision("");
    setConfirming(false);
    setFailure(null);
    setErrors({});
  }
  function close(opener: string) {
    reset();
    onOpenChange?.(false);
    focusAfter(id(opener));
  }
  async function send(body: Record<string, unknown>, message: string) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    setErrors({});
    const outcome = await sendJson(`${APPLICATIONS_URL}/${detail.id}/visa`, visa ? "PATCH" : "POST", body); // never throws
    inFlight.current = false;
    setBusy(false);
    setConfirming(false);
    if (!outcome.ok) {
      if (outcome.status === 409 || outcome.status === 404) {
        setMode(null); // stale input must not stay on screen; the detail reloads the real state
        return onFailed(outcome.message, outcome.status);
      }
      const onFields = outcome.status === 422 ? fieldErrors(outcome.detail, FIELDS) : null;
      if (onFields) {
        setErrors(onFields);
        return focusAfter(id(FIELDS.find((f) => onFields[f])!));
      }
      const status = outcome.status ?? 0;
      setFailure(status === 401 ? { text: EXPIRED, expired: true } : { text: status >= 500 ? SERVER_ERROR : outcome.message });
      return focusAfter(id("failure"));
    }
    const next = (outcome.data as { application?: AgentApplicationDetail }).application;
    if (!next) return onFailed("The change could not be confirmed. Reload to see the current visa case.");
    reset(); // a save that keeps the stage does not remount this section (its key is stage-based), so close the form here (review I-1)
    onSaved(next, message);
  }
  function saveDetails({ checklist, ...dates }: VisaDetails) {
    if (!visa) return send({ expected_status: detail.status, checklist: checklist ?? [], ...dates }, "Visa case started.");
    send({ expected_stage: visa.stage, ...dates, ...(checklist ? { checklist } : {}) }, "Visa details saved.");
  }
  const move = () => send({ expected_stage: visa!.stage, to_stage: target }, `Visa case moved to ${stageLabel(target)}.`);
  const decide = () => send({ expected_stage: visa!.stage, decision }, "Visa decision recorded.");
  function submitMove(event: FormEvent) {
    event.preventDefault();
    if (skipped > 0) setConfirming(true); // a skip is confirmed first
    else move();
  }
  function submitDecision(event: FormEvent) {
    event.preventDefault();
    setConfirming(true);
  }
  function back(focus: string) {
    setConfirming(false);
    focusAfter(id(focus));
  }
  const invalid = (field: Field) => (errors[field] ? { "aria-invalid": true as const, "aria-describedby": id(`${field}-error`) } : {});
  const fieldError = (field: Field) =>
    errors[field] && (
      <p id={id(`${field}-error`)} className="form-error">
        {errors[field]}
      </p>
    );
  const failureNode = failure && (
    <p id={id("failure")} tabIndex={-1} className="form-error" role="alert">
      {failure.text}
      {failure.expired && (
        <>
          {" "}
          <Link href={SIGN_IN_PATH} target="_blank" rel="noopener">
            Sign in again
          </Link>
        </>
      )}
    </p>
  );
  const confirmGroup = (label: string, text: string, yes: string, onYes: () => void, backTo: string) => (
    <div role="group" aria-label={label} onKeyDown={(event: KeyboardEvent) => event.key === "Escape" && back(backTo)}>
      <p>{text}</p>
      <div className="actions">
        <button type="button" className="btn small" disabled={busy} onClick={onYes} autoFocus>
          {busy ? "Saving…" : yes}
        </button>
        <button type="button" className="btn ghost small" onClick={() => back(backTo)}>
          Go back
        </button>
      </div>
    </div>
  );
  const submitRow = (submitId: string, label: string, disabled: boolean, opener: string) => (
    <div className="actions">
      <button id={id(submitId)} className="btn small" disabled={busy || disabled}>
        {busy ? "Saving…" : label}
      </button>
      <button type="button" className="btn ghost small" onClick={() => close(opener)}>
        Cancel
      </button>
    </div>
  );

  return (
    <section aria-labelledby={id("heading")}>
      <h5 id={id("heading")}>Visa</h5>
      {!visa ? (
        <p className="muted">No visa case yet.</p>
      ) : (
        <>
          <p>
            <span className="badge">{stageLabel(visa.stage)}</span>
          </p>
          <dl className="card-stack">
            <dt>Visa application date</dt>
            <dd>{visa.visa_application_date ?? "Not recorded"}</dd>
            <dt>Appointment</dt>
            <dd>{visa.appointment_date ?? "Not recorded"}</dd>
            <dt>Interview</dt>
            <dd>{visa.interview_date ?? "Not recorded"}</dd>
            {visa.decision && (
              <>
                <dt>Decision</dt>
                <dd>{VISA_DECISION_LABELS[visa.decision]}</dd>
                <dt>Recorded</dt>
                <dd>{visa.decided_at ? formatDateTimeIn(visa.decided_at, viewerTimeZone(), true) : "—"}</dd>
              </>
            )}
          </dl>
          <h6>Document checklist</h6>
          {visa.checklist.length === 0 ? (
            <p className="muted">No documents are required on this checklist.</p>
          ) : (
            <ul aria-label="Document checklist">
              {visa.checklist.map((c) => (
                <li key={c.item}>
                  {c.item}: {checklistStatusLabel(c.verification_status)}
                </li>
              ))}
            </ul>
          )}
          {writable && visaChecklistEditable(visa.stage) && visa.checklist.length > 0 && (
            <p className="muted">Upload each document for this application under Documents; it counts once it is verified.</p>
          )}
          {(visa.decision || visa.stage === "decision") && <p className="muted">{visa.disclaimer}</p>}
        </>
      )}
      {writable && mode === null && (
        <div className="actions">
          <button id={id(visa ? "edit" : "start")} type="button" className="btn secondary small" onClick={() => open("details", "visa_application_date")}>
            {visa ? "Edit visa details" : "Start visa case"}
          </button>
          {forward.length > 0 && (
            <button id={id("move")} type="button" className="btn secondary small" onClick={() => open("move", "to_stage")}>
              Move visa stage
            </button>
          )}
          {visa?.stage === "decision" && (
            <button id={id("decide")} type="button" className="btn secondary small" onClick={() => open("decide", "decision")}>
              Record decision
            </button>
          )}
        </div>
      )}
      {mode === "details" && (
        <AgentVisaDetailsForm
          appId={detail.id}
          visa={visa}
          busy={busy}
          errors={errors}
          failure={failureNode}
          onSubmit={saveDetails}
          onCancel={() => close(visa ? "edit" : "start")}
        />
      )}
      {mode === "move" && (
        <form className="form" aria-label="Move visa stage" onSubmit={submitMove}>
          <div className="field">
            <label htmlFor={id("to_stage")}>Move to</label>
            <select id={id("to_stage")} value={target} onChange={(event) => (setTarget(event.target.value), setConfirming(false))} {...invalid("to_stage")}>
              <option value="">Choose a stage</option>
              {forward.map((stage) => (
                <option key={stage} value={stage}>
                  {stageLabel(stage)}
                </option>
              ))}
            </select>
            {fieldError("to_stage")}
          </div>
          {failureNode}
          {confirming
            ? confirmGroup("Confirm move", `This skips ${skipped} stage${skipped === 1 ? "" : "s"}. Move to ${stageLabel(target)} anyway?`, "Yes, move", move, "move-submit")
            : submitRow("move-submit", "Move", !target, "move")}
        </form>
      )}
      {mode === "decide" && (
        <form className="form" aria-label="Record visa decision" onSubmit={submitDecision}>
          <fieldset id={id("decision")} tabIndex={-1} className="form-section" {...invalid("decision")}>
            <legend>The authority&apos;s decision</legend>
            {VISA_DECISIONS.map((value) => (
              <label key={value} className="pf-check">
                <input type="radio" name={id("decision-value")} value={value} checked={decision === value} onChange={() => (setDecision(value), setConfirming(false))} />
                {VISA_DECISION_LABELS[value]}
              </label>
            ))}
            {fieldError("decision")}
          </fieldset>
          {failureNode}
          {confirming && decision
            ? confirmGroup("Confirm decision", `Record “${VISA_DECISION_LABELS[decision]}”? A recorded decision cannot be changed.`, "Yes, record decision", decide, "decide-submit")
            : submitRow("decide-submit", "Record decision", !decision, "decide")}
        </form>
      )}
    </section>
  );
}
