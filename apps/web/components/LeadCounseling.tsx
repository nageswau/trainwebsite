"use client";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson, type Page } from "@/lib/apiErrors";
import { formatInr, todayIst } from "@/lib/bdmAppointments";
import { SAVE_FAILED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import { formatCalendarDate } from "@/lib/formatDate";
import {
  DECISION_MAKER_LABEL, DECISION_MAKERS, NOTES_MAX, OBJECTION_NOTES_MAX, OBJECTIONS_URL, OUTCOME_LABEL, OUTCOMES, counselingBody, counselingValues,
  isCounselingRecord, listUrl, type CounselingRecord, type CounselingValues, type Ref,
} from "@/lib/leadCounseling";
import { activeProducts, getPage, readAll } from "@/lib/telecallerCatalogue";

const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;
type WriteUrl = (recordId?: string) => string;

/** The pickers: active IT courses and active objections, plus whatever the record being edited already holds (it may be inactive now). */
function useOptions(record?: CounselingRecord) {
  const [courses, setCourses] = useState<Ref[]>([]);
  const [objections, setObjections] = useState<Ref[]>([]);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    const withKept = (list: Ref[], kept: Ref[]) => [...list, ...kept.filter((k) => !list.some((o) => o.id === k.id))];
    Promise.all([activeProducts(controller.signal), readAll<Ref>(OBJECTIONS_URL, controller.signal)])
      .then(([products, active]) => {
        setCourses(withKept(products.filter((p) => p.group === "it").map(({ id, name }) => ({ id, name })), record?.recommended_product ? [record.recommended_product] : []));
        setObjections(withKept(active.map(({ id, name }) => ({ id, name })), record?.objections ?? []));
      })
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [record]);
  return { courses, objections, failed };
}

/** itc-010: record (POST) or edit (PATCH) one session. The API's 422s land on their fields; typed values are kept. */
function CounselingForm({ url, record, onSaved, onCancel }: { url: WriteUrl; record?: CounselingRecord; onSaved: (text: string) => void; onCancel: () => void }) {
  const id = useId();
  const [v, setV] = useState<CounselingValues>(() => counselingValues(record));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // a POST is not idempotent: Enter while saving must not record twice
  const { courses, objections, failed } = useOptions(record);
  const title = record ? "Edit counseling" : "Record counseling";
  const fid = (key: string) => `${id}-${key}`;
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });
  const error = (key: string) => errors[key] && <p id={`${fid(key)}-error`} className="form-error">{errors[key]}</p>;
  const set = (key: keyof CounselingValues) => (e: { target: { value: string } }) => setV({ ...v, [key]: e.target.value });
  const minDate = (stored: string | null | undefined) => (stored && stored < todayIst() ? undefined : todayIst()); // a kept past date still saves

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!v.outcome) return setErrors({ outcome: "Choose the counseling outcome" });
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setErrors({});
    setFailure(null);
    const result = await sendJson(url(record?.id), record ? "PATCH" : "POST", counselingBody(v));
    inFlight.current = false;
    setBusy(false);
    if (result.ok) return isCounselingRecord(result.data) ? onSaved(record ? "Counseling saved." : "Counseling recorded.") : setFailure(SAVE_FAILED);
    const placed = fieldErrors(result.detail);
    if (Object.keys(placed).length) return setErrors(placed);
    setFailure(writeFailure(result.status) === "retry" ? SAVE_FAILED : result.message);
  }

  return (
    <form aria-label={title} className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()} style={{ display: "grid", gap: 8 }}>
      <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))" }}>
        <div className="field">
          <label htmlFor={fid("outcome")}>Outcome (required)</label>
          <select id={fid("outcome")} value={v.outcome} disabled={busy} aria-required="true" onChange={set("outcome")} {...invalid("outcome")}>
            <option value="">Choose…</option>
            {OUTCOMES.map((o) => <option key={o} value={o}>{OUTCOME_LABEL[o]}</option>)}
          </select>
          {error("outcome")}
        </div>
        <div className="field">
          <label htmlFor={fid("recommended_product_id")}>Recommended course</label>
          <select id={fid("recommended_product_id")} value={v.recommended_product_id} disabled={busy} onChange={set("recommended_product_id")} {...invalid("recommended_product_id")}>
            <option value="">Not chosen</option>
            {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          {error("recommended_product_id")}
        </div>
        <div className="field">
          <label htmlFor={fid("fee_quoted")}>Course fee quoted (₹)</label>
          <input id={fid("fee_quoted")} type="number" inputMode="decimal" min={0} step="0.01" value={v.fee_quoted} disabled={busy} onChange={set("fee_quoted")} {...invalid("fee_quoted")} />
          {error("fee_quoted")}
        </div>
        <div className="field">
          <label htmlFor={fid("expected_joining_date")}>Expected joining date</label>
          <input id={fid("expected_joining_date")} type="date" min={minDate(record?.expected_joining_date)} value={v.expected_joining_date} disabled={busy}
            onChange={set("expected_joining_date")} {...invalid("expected_joining_date")} />
          {error("expected_joining_date")}
        </div>
        <div className="field">
          <label htmlFor={fid("decision_maker")}>Decision-maker</label>
          <select id={fid("decision_maker")} value={v.decision_maker} disabled={busy} onChange={set("decision_maker")} {...invalid("decision_maker")}>
            <option value="">Not known</option>
            {DECISION_MAKERS.map((d) => <option key={d} value={d}>{DECISION_MAKER_LABEL[d]}</option>)}
          </select>
          {error("decision_maker")}
        </div>
        <div className="field">
          <label htmlFor={fid("next_follow_up")}>Next follow-up</label>
          <input id={fid("next_follow_up")} type="date" min={minDate(record?.next_follow_up)} value={v.next_follow_up} disabled={busy}
            onChange={set("next_follow_up")} {...invalid("next_follow_up")} />
          {error("next_follow_up")}
        </div>
      </div>
      <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }} {...invalid("objection_ids")}>
        <legend>Objections</legend>
        {failed && <p className="form-error" role="alert">Unable to load the course and objection lists.</p>}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 16px" }}>
          {objections.map((o) => (
            <label key={o.id} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
              <input type="checkbox" checked={v.objection_ids.includes(o.id)} disabled={busy}
                onChange={(e) => setV({ ...v, objection_ids: e.target.checked ? [...v.objection_ids, o.id] : v.objection_ids.filter((x) => x !== o.id) })} />
              {o.name}
            </label>
          ))}
        </div>
        {error("objection_ids")}
      </fieldset>
      <div className="field">
        <label htmlFor={fid("objection_notes")}>Other objections</label>
        <textarea id={fid("objection_notes")} rows={2} maxLength={OBJECTION_NOTES_MAX} value={v.objection_notes} disabled={busy} onChange={set("objection_notes")} {...invalid("objection_notes")} />
        {error("objection_notes")}
      </div>
      <div className="field">
        <label htmlFor={fid("notes")}>Counselor notes</label>
        <textarea id={fid("notes")} rows={3} maxLength={NOTES_MAX} value={v.notes} disabled={busy} onChange={set("notes")} {...invalid("notes")} />
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>{v.notes.length}/{NOTES_MAX}</p>
        {error("notes")}
      </div>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save counseling"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

function RecordCard({ record, onEdit }: { record: CounselingRecord; onEdit?: () => void }) {
  const show = (value: React.ReactNode) => (value === null || value === undefined || value === "" ? <span className="muted">—</span> : value);
  const rows: [string, React.ReactNode][] = [
    ["Recommended course", show(record.recommended_product?.name)], ["Fee quoted", show(record.fee_quoted && formatInr(record.fee_quoted))],
    ["Expected joining", show(record.expected_joining_date && formatCalendarDate(record.expected_joining_date))],
    ["Decision-maker", show(record.decision_maker && DECISION_MAKER_LABEL[record.decision_maker])],
    ["Next follow-up", show(record.next_follow_up && formatCalendarDate(record.next_follow_up))],
    ["Objections", show(record.objections.map((o) => o.name).join(", "))],
  ];
  return (
    <li className="action-card" style={{ listStyle: "none", gap: 6 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <strong>{OUTCOME_LABEL[record.outcome] ?? record.outcome}</strong>
        {onEdit && <button type="button" className="btn secondary small" aria-label={`Edit counseling of ${formatCalendarDate(record.created_at)}`} onClick={onEdit}>Edit</button>}
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        <LocalTime value={record.created_at} /> · {record.author.full_name}
        {record.updated_at !== record.created_at && <> · edited by {record.updated_by.full_name}</>}
      </p>
      <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))", gap: "6px 16px", margin: 0 }}>
        {rows.map(([term, value]) => (
          <div key={term}><dt className="muted" style={{ fontSize: 13 }}>{term}</dt><dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd></div>
        ))}
      </dl>
      {record.objection_notes && <p style={{ ...TEXT, margin: 0 }}><span className="muted">Other objections: </span>{record.objection_notes}</p>}
      {record.notes && <p style={{ ...TEXT, margin: 0 }}>{record.notes}</p>}
    </li>
  );
}

/** itc-010 (DEC-SCOPE-343): a lead's counseling sessions, newest first. `writeUrl` (the IT counselor on an open lead) adds Record and Edit;
 *  without it the section is read only (the telecaller side, or a closed lead). Internal: never shown to the student. */
export default function LeadCounseling({ listUrl: url, writeUrl, onChanged }: { listUrl: string; writeUrl: WriteUrl | null; onChanged?: () => void }) {
  const [data, setData] = useState<Page<CounselingRecord> | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [editing, setEditing] = useState<CounselingRecord | "new" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const reload = () => setVersion((n) => n + 1);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<CounselingRecord>(listUrl(url), controller.signal).then(setData).catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [url, version]);

  function saved(text: string) {
    setEditing(null);
    setNotice(text);
    reload();
    onChanged?.();
  }

  return (
    <section aria-labelledby="lead-counseling-heading">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id="lead-counseling-heading" style={{ margin: 0 }}>Counseling</h3>
        {writeUrl && editing === null && (
          <button type="button" className="btn secondary small" onClick={() => { setEditing("new"); setNotice(null); }}>Record counseling</button>
        )}
      </div>
      <div role="status" aria-live="polite">{notice && <p className="form-message" style={{ margin: "6px 0 0", fontSize: 13 }}>{notice}</p>}</div>
      {writeUrl && editing !== null && (
        <CounselingForm key={editing === "new" ? "new" : editing.id} url={writeUrl} record={editing === "new" ? undefined : editing} onSaved={saved}
          onCancel={() => setEditing(null)} />
      )}
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the counseling sessions.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading counseling…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ fontSize: 13 }}>No counseling recorded yet.</p>
      ) : (
        <ul aria-label="Counseling sessions" style={{ padding: 0, margin: "8px 0 0", display: "grid", gap: 8 }}>
          {data.items.map((r) => (
            <RecordCard key={r.id} record={r} onEdit={writeUrl && editing === null ? () => { setEditing(r); setNotice(null); } : undefined} />
          ))}
        </ul>
      )}
      {data && data.total > data.items.length && <p className="muted" style={{ fontSize: 13 }}>Showing the latest {data.items.length} of {data.total} sessions.</p>}
    </section>
  );
}
