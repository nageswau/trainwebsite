"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, type KeyboardEvent, useRef, useState } from "react";

import { type SendOutcome, sendJson } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmPipeline";
import { formatCalendarDate } from "@/lib/formatDate";
import {
  AUTO_LABEL,
  EXPECTED_FIELDS,
  expectedUrl,
  isMilestonePage,
  type Milestone,
  type MilestonePage,
  type MilestoneStatus,
  milestonesUrl,
  monthLabel,
  quarterLabel,
  STATUS_LABEL,
  type UniversityExpected,
} from "@/lib/partnershipMilestones";
import { probabilityText, probabilityUrl, type UniversityProbability } from "@/lib/partnershipExpected";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Values = Record<string, string>;
// QA8-04: the current milestone (blue) stands apart from the pending ones (amber); the label always says which (never colour alone).
const STATUS_CLASS: Record<MilestoneStatus, string> = { done: "status", in_progress: "badge", pending: "status pending", delayed: "status error" };
const blankToNull = (values: Values) => Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v.trim() === "" ? null : v.trim()]));

// upc-008 (spec §4): §5's expected timeline (month and quarter derived by the API, Q-10) and §6's milestone table with its Q-11 status as
// text -- a delayed milestone is also highlighted, never by colour alone. Writes go to the API, which enforces every rule (owner / head /
// super_admin, achieved not in the future); a refusal keeps what was typed. The expected timeline lives on the server-rendered university,
// so saving it refreshes the page; a milestone save replaces the whole table, since statuses depend on each other.
// upc-023 (§24, EX2-EX4): the partnership probability -- the stage's band, or a manual override (0-100, with a reason) set by those who may
// move the stage; it lives on the server-rendered university too, so saving refreshes the page.
type Target = "expected" | "probability" | Milestone;

export default function UniversityTimeline({ universityId, expected, canEdit, initial, probability, canOverride }: {
  universityId: string; expected: UniversityExpected; canEdit: boolean; initial: MilestonePage | null; probability: UniversityProbability; canOverride: boolean;
}) {
  const router = useRouter();
  const [milestones, setMilestones] = useState<MilestonePage | null>(initial);
  const [loadFailed, setLoadFailed] = useState(initial === null);
  const [editing, setEditing] = useState<Target | null>(null);
  const [values, setValues] = useState<Values>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // a second submit before the re-render (double click) sends nothing
  const focus = useFocusAfterRender();
  const id = (part: string) => `timeline-${universityId}-${part}`;
  const editId = (m: Target) => id(typeof m === "string" ? `edit-${m}` : `edit-${m.kind}`);
  const delayed = milestones?.items.filter((m) => m.status === "delayed").length ?? 0;
  const editingMilestone = editing !== null && typeof editing !== "string" ? editing : null;
  const overridden = probability.override !== null;

  async function reload() {
    setLoadFailed(false);
    const response = await fetch(milestonesUrl(universityId)).catch(() => null);
    const data = response?.ok ? await response.json().catch(() => null) : null;
    if (isMilestonePage(data)) setMilestones(data);
    else setLoadFailed(true);
  }

  function open(target: Target) {
    setEditing(target);
    setErrors({});
    setFailure(null);
    setNotice(null);
    if (target === "probability") {
      setValues({ probability: probability.override?.toString() ?? "", reason: probability.reason ?? "" });
      focus(id("probability"));
    } else if (target === "expected") {
      setValues(Object.fromEntries(EXPECTED_FIELDS.map((f) => [f.key, expected[f.key] ?? ""])));
      focus(id(EXPECTED_FIELDS[0].key));
    } else {
      // An auto-achieved date is not a recorded one: the field stays blank, so saving keeps the automatic date (MS5).
      setValues({ target_date: target.target_date ?? "", achieved_on: target.achieved_by === "manual" ? target.achieved_on ?? "" : "" });
      focus(id("target_date"));
    }
  }

  function close() {
    if (editing === null) return;
    const back = editId(editing);
    setEditing(null);
    setErrors({});
    focus(back);
  }

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape") close();
  };

  function request(target: Target, sent: Values): Promise<SendOutcome> {
    if (target === "probability") {
      const { probability: value, reason } = blankToNull(sent);
      return sendJson(probabilityUrl(universityId), "PUT", { probability: value === null ? null : Number(value), reason });
    }
    return sendJson(target === "expected" ? expectedUrl(universityId) : milestonesUrl(universityId, target.kind), "PATCH", blankToNull(sent));
  }

  async function save(event: FormEvent | null, target: Target | null = editing, sent: Values = values) {
    event?.preventDefault();
    if (target === null || inFlight.current) return;
    const percent = sent.probability?.trim() ?? "";
    if (target === "probability" && percent !== "" && !(/^\d+$/.test(percent) && Number(percent) <= 100)) {
      setErrors({ probability: "Enter a whole number from 0 to 100." }); // QA23-01: the API's range wording is Pydantic's
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    setNotice(null);
    setErrors({});
    try {
      const outcome = await request(target, sent);
      if (!outcome.ok) {
        const fields = fieldErrors(outcome.detail);
        if (Object.keys(fields).length) setErrors(fields);
        else setFailure(outcome.message);
        return;
      }
      setEditing(null);
      focus(editId(target));
      if (target === "probability") {
        setNotice(sent.probability.trim() === "" ? "Probability override cleared." : "Probability saved.");
        router.refresh();
      } else if (target === "expected") {
        setNotice("Expected timeline saved.");
        router.refresh();
      } else {
        if (isMilestonePage(outcome.data)) setMilestones(outcome.data);
        setNotice(`${target.label} saved.`);
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  const field = (key: string, label: string, type: "date" | "text" | "number", extra: { min?: string; max?: string; maxLength?: number; hint?: string } = {}) => (
    <div className="field" key={key}>
      <label htmlFor={id(key)}>{label}</label>
      <input id={id(key)} type={type} value={values[key] ?? ""} onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
        min={extra.min} max={extra.max} maxLength={extra.maxLength} aria-invalid={errors[key] ? true : undefined}
        aria-describedby={[errors[key] && id(`${key}-error`), extra.hint && id(`${key}-hint`)].filter(Boolean).join(" ") || undefined} />
      {extra.hint && <p id={id(`${key}-hint`)} className="muted" style={{ margin: 0, fontSize: 13 }}>{extra.hint}</p>}
      {errors[key] && <p id={id(`${key}-error`)} className="form-error">{errors[key]}</p>}
    </div>
  );
  const buttons = (saveLabel: string) => (
    <div className="actions">
      <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : saveLabel}</button>
      <button type="button" className="btn secondary small" onClick={close} disabled={busy}>Cancel</button>
    </div>
  );
  const notSet = <span className="muted">Not set</span>;
  const facts: [string, string | null][] = [
    ["Target partnership date", expected.target_partnership_date && formatCalendarDate(expected.target_partnership_date)],
    ["Expected month", monthLabel(expected.expected_month)],
    ["Expected quarter", quarterLabel(expected.expected_quarter)],
    ["Expected intake", expected.expected_intake],
    ["Expected agreement date", expected.expected_agreement_date && formatCalendarDate(expected.expected_agreement_date)],
    ["Expected student recruitment start date", expected.expected_recruitment_start && formatCalendarDate(expected.expected_recruitment_start)],
  ];

  return (
    <section className="action-card wide" aria-labelledby={id("heading")}>
      <h3 id={id("heading")}>Partnership timeline</h3>
      {notice && <p className="form-message" role="status">{notice}</p>}
      {failure && <p className="form-error" role="alert">{failure}</p>}

      <h4 id={id("expected")} style={{ margin: "0 0 8px" }}>Expected timeline</h4>
      {editing === "expected" ? (
        <form className="form-grid" onSubmit={save} onKeyDown={onKeyDown} aria-label="Edit expected timeline" style={{ alignItems: "start" }}>
          {EXPECTED_FIELDS.map((f) => field(f.key, f.label, f.type, f.type === "text" ? { maxLength: 80 } : {}))}
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>The expected month and quarter follow the target partnership date.</p>
          {buttons("Save expected timeline")}
        </form>
      ) : (
        <>
          {/* QA8-03: the value column keeps room for a whole word ("November 2026") on phones; long labels wrap instead */}
          <dl role="group" aria-labelledby={id("expected")} style={{ display: "grid", gridTemplateColumns: "minmax(min(120px, 40%), max-content) minmax(9rem, 1fr)", gap: "6px 16px", margin: "0 0 12px" }}>
            {facts.map(([term, value]) => [
              <dt key={`${term}-t`} className="muted">{term}</dt>,
              <dd key={`${term}-d`} style={{ margin: 0, overflowWrap: "anywhere" }}>{value || notSet}</dd>,
            ])}
          </dl>
          {canEdit && (
            <button id={editId("expected")} type="button" className="btn secondary small" onClick={() => open("expected")} disabled={busy} style={{ justifySelf: "start" }}>
              Edit expected timeline
            </button>
          )}
        </>
      )}

      <h4 id={id("probability-heading")} style={{ margin: "20px 0 8px" }}>Partnership probability</h4>
      {editing === "probability" ? (
        <form className="form-grid" onSubmit={save} onKeyDown={onKeyDown} aria-label="Override probability" noValidate style={{ alignItems: "start" }}>
          {field("probability", "Probability (%)", "number", { min: "0", max: "100", hint: `The stage gives ${probability.stage}%. Leave blank to use it.` })}
          {field("reason", "Reason", "text", { maxLength: 500 })}
          {buttons("Save probability")}
        </form>
      ) : (
        <>
          <p style={{ margin: "0 0 4px" }}>{probabilityText(probability.effective, probability.stage, overridden)}</p>
          {overridden && probability.reason && <p className="muted" style={{ margin: "0 0 8px", overflowWrap: "anywhere" }}>Reason: {probability.reason}</p>}
          {canOverride && (
            <div className="actions">
              <button id={editId("probability")} type="button" className="btn secondary small" onClick={() => open("probability")} disabled={busy}>
                {overridden ? "Change override" : "Override probability"}
              </button>
              {overridden && (
                <button type="button" className="btn ghost small" onClick={() => void save(null, "probability", { probability: "", reason: "" })} disabled={busy}>
                  Clear override
                </button>
              )}
            </div>
          )}
        </>
      )}

      <h4 style={{ margin: "20px 0 8px" }}>Milestones</h4>
      {loadFailed || milestones === null ? (
        <div className="actions" style={{ alignItems: "center" }}>
          <p className="form-error" role="alert" style={{ margin: 0 }}>Unable to load the milestones.</p>
          <button type="button" className="btn secondary small" onClick={() => void reload()}>Try again</button>
        </div>
      ) : (
        <>
          {delayed > 0 && <p><span className="status error">{delayed} milestone{delayed === 1 ? "" : "s"} delayed</span></p>}
          <div className="table-wrap">
            <table className="table milestone-table">
              <caption className="visually-hidden">Partnership milestones</caption>
              <thead>
                <tr><th scope="col">Milestone</th><th scope="col">Target date</th><th scope="col">Achieved</th><th scope="col">Status</th>{milestones.can_edit && <th scope="col"><span className="visually-hidden">Actions</span></th>}</tr>
              </thead>
              <tbody>
                {milestones.items.map((m) => (
                  <tr key={m.kind} className={m.status === "delayed" ? "milestone-delayed" : undefined}>
                    <th scope="row">{m.label}</th>
                    <td>{m.target_date ? formatCalendarDate(m.target_date) : "—"}</td>
                    <td>
                      {m.achieved_on ? formatCalendarDate(m.achieved_on) : "—"}
                      {m.achieved_by === "auto" && m.auto_source && <span className="muted"> (Auto, {AUTO_LABEL[m.auto_source]})</span>}
                    </td>
                    <td><span className={STATUS_CLASS[m.status]}>{STATUS_LABEL[m.status]}</span></td>
                    {milestones.can_edit && (
                      <td>
                        <button id={editId(m)} type="button" className="btn ghost small" aria-label={`Edit ${m.label}`} onClick={() => open(m)} disabled={busy || editing !== null}>
                          Edit
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {editingMilestone && (
            <form className="form-grid" onSubmit={save} onKeyDown={onKeyDown} aria-label={`Edit ${editingMilestone.label}`} style={{ alignItems: "start", marginTop: 12 }}>
              {field("target_date", "Target date", "date")}
              {field("achieved_on", "Achieved on", "date", {
                max: milestones.today,
                hint: editingMilestone.achieved_by === "auto" && editingMilestone.achieved_on
                  ? `Leave blank to use the automatic date (${formatCalendarDate(editingMilestone.achieved_on)}).` : undefined,
              })}
              {buttons("Save")}
            </form>
          )}
        </>
      )}
    </section>
  );
}
