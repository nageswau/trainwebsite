"use client";
import Link from "next/link";
import { type FormEvent, type ReactNode, useId, useMemo, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import RecruiterInvoiceCard from "@/components/RecruiterInvoiceCard";
import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import SearchableSelect from "@/components/SearchableSelect";
import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors, indiaToday } from "@/lib/bdmTravel";
import { formatCalendarDate } from "@/lib/formatDate";
import type { PickOption } from "@/lib/lookups";
import { type Confirmation, type Placement, placementOf, placementUrl, SURVEY_AFTER_DAYS, type Survey, VIA_OPTIONS } from "@/lib/placements";
import { recruiterSearch, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { inr } from "@/lib/recruiterRevenue";

type Failure = { kind: "session" | "error"; message: string };
type Changed = (placement: Placement, notice: string) => void;

/** One form's submit: 422s go on their fields, a refusal (403/409) stays on the form in the server's words. In-flight guarded. */
function useSubmit(onSaved: (p: Placement) => void) {
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<Failure | null>(null);
  const inFlight = useRef(false);
  async function run(send: () => Promise<SendOutcome>) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setErrors({});
    setFailure(null);
    const result = await send();
    inFlight.current = false;
    setBusy(false);
    if (result.ok) {
      const saved = placementOf(result.data);
      return saved ? onSaved(saved) : setFailure({ kind: "error", message: SAVE_FAILED });
    }
    const placed = fieldErrors(result.detail);
    if (Object.keys(placed).length) return setErrors(placed);
    const kind = writeFailure(result.status);
    setFailure(kind === "session" ? { kind, message: SESSION_ENDED } : { kind: "error", message: kind === "retry" ? SAVE_FAILED : result.message });
  }
  return { busy, errors, failure, run };
}

function Problem({ failure }: { failure: Failure | null }) {
  if (!failure) return null;
  return (
    <div role="alert">
      <p className="form-error">{failure.message}</p>
      {failure.kind === "session" && <ReturnToLoginLink loginHref={RECRUITER_SIGN_IN} />}
    </div>
  );
}

function Field({ id, label, error, children }: { id: string; label: string; error?: string; children: ReactNode }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      {error && <p id={`${id}-error`} className="form-error">{error}</p>}
    </div>
  );
}

function Facts({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))", gap: "6px 16px", margin: 0 }}>
      {rows.map(([term, value]) => (
        <div key={term}>
          <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
          <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** P5: one side's confirmation -- who, when and how; Clear removes it. */
function ConfirmationCard({ placement, side, title, onChanged }: { placement: Placement; side: "candidate" | "client"; title: string; onChanged: Changed }) {
  const key = `${side}_confirmation` as const;
  const current: Confirmation = placement[key];
  const id = useId();
  const [editing, setEditing] = useState(false);
  const [v, setV] = useState({ by: current?.by ?? "", on: current?.on ?? indiaToday(), via: current?.via ?? "call" });
  const { busy, errors, failure, run } = useSubmit((p) => {
    setEditing(false);
    onChanged(p, `${title} saved.`);
  });
  const fid = (k: string) => `${id}-${k}`;
  const invalid = (k: string) => ({ "aria-invalid": errors[k] ? true : undefined, "aria-describedby": errors[k] ? `${fid(k)}-error` : undefined });
  const save = (body: unknown) => run(() => sendJson(placementUrl(placement.id), "PATCH", { [key]: body }));
  function submit(event: FormEvent) {
    event.preventDefault();
    void save({ by: v.by.trim() || null, on: v.on || null, via: v.via });
  }
  return (
    <section className="action-card" style={{ gap: 6 }} aria-label={title}>
      <strong>{title}</strong>
      {current ? (
        <p style={{ margin: 0, overflowWrap: "anywhere" }}>{current.by} · {formatCalendarDate(current.on)} · {current.via_label}</p>
      ) : <p className="muted" style={{ margin: 0 }}>Not confirmed yet.</p>}
      {placement.permissions.can_edit && !editing && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" className="btn secondary small" onClick={() => setEditing(true)}>{current ? "Change" : "Record confirmation"}</button>
          {current && <button type="button" className="btn secondary small" disabled={busy} onClick={() => void save(null)}>Clear</button>}
        </div>
      )}
      {editing && (
        <form aria-label={`${title} form`} noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && setEditing(false)} style={{ display: "grid", gap: 8 }}>
          <div className="form-grid">
            <Field id={fid("by")} label="Confirmed by" error={errors.by}>
              <input id={fid("by")} autoFocus maxLength={160} value={v.by} onChange={(e) => setV({ ...v, by: e.target.value })} {...invalid("by")} />
            </Field>
            <Field id={fid("on")} label="Confirmed on" error={errors.on}>
              <input id={fid("on")} type="date" max={indiaToday()} value={v.on} onChange={(e) => setV({ ...v, on: e.target.value })} {...invalid("on")} />
            </Field>
            <Field id={fid("via")} label="How" error={errors.via}>
              <select id={fid("via")} value={v.via} onChange={(e) => setV({ ...v, via: e.target.value })} {...invalid("via")}>
                {VIA_OPTIONS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
              </select>
            </Field>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            <button type="button" className="btn secondary small" onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </form>
      )}
      <Problem failure={failure} />
    </section>
  );
}

/** P6: the Team Lead picks another recruiter as the PO owner. */
function OwnerPicker({ placement, onChanged }: { placement: Placement; onChanged: Changed }) {
  const [picked, setPicked] = useState<PickOption | null>(null);
  const owner = placement.po_owner?.id ?? null;
  const search = useMemo(() => recruiterSearch(owner), [owner]);
  const { busy, errors, failure, run } = useSubmit((p) => {
    setPicked(null);
    onChanged(p, "PO owner changed.");
  });
  return (
    <div style={{ display: "grid", gap: 8 }}>
      <SearchableSelect key={owner ?? "none"} label="Change PO owner to" noun="recruiter" search={search} onChange={setPicked} />
      {errors.po_owner_user_id && <p className="form-error" role="alert">{errors.po_owner_user_id}</p>}
      <div>
        <button type="button" className="btn secondary small" disabled={!picked || busy} onClick={() => picked && void run(() => sendJson(placementUrl(placement.id), "PATCH", { po_owner_user_id: picked.id }))}>
          {busy ? "Saving…" : "Change owner"}
        </button>
      </div>
      <Problem failure={failure} />
    </div>
  );
}

/** P10/P11: review the draft -- issue it as an invoice (the form starts from the draft) or discard it with a reason. */
function DraftReview({ placement, onChanged }: { placement: Placement; onChanged: Changed }) {
  const draft = placement.commercials!.invoice;
  const id = useId();
  const [mode, setMode] = useState<"issue" | "discard" | null>(null);
  const [v, setV] = useState({ invoice_number: "", invoice_date: indiaToday(), due_date: draft.draft_due_date ?? indiaToday(), amount: draft.draft_amount ?? "", note: "" });
  const [reason, setReason] = useState("");
  const issue = useSubmit((p) => {
    setMode(null);
    onChanged(p, "Invoice issued. It now shows in Receivables.");
  });
  const discard = useSubmit((p) => {
    setMode(null);
    onChanged(p, "Invoice draft discarded.");
  });
  const fid = (k: string) => `${id}-${k}`;
  const invalid = (k: string) => ({ "aria-invalid": issue.errors[k] ? true : undefined, "aria-describedby": issue.errors[k] ? `${fid(k)}-error` : undefined });
  const input = (k: keyof typeof v, label: string, type = "text") => (
    <Field id={fid(k)} label={label} error={issue.errors[k]}>
      <input id={fid(k)} type={type} inputMode={k === "amount" ? "decimal" : undefined} maxLength={k === "invoice_number" ? 40 : k === "note" ? 500 : undefined}
        value={v[k]} onChange={(e) => setV({ ...v, [k]: e.target.value })} {...invalid(k)} />
    </Field>
  );
  return (
    <div style={{ display: "grid", gap: 8 }}>
      {mode === null && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" className="btn small" onClick={() => setMode("issue")}>Issue invoice</button>
          <button type="button" className="btn secondary small" onClick={() => setMode("discard")}>Discard draft</button>
        </div>
      )}
      {mode === "issue" && (
        <form aria-label="Issue invoice" noValidate style={{ display: "grid", gap: 8 }} onKeyDown={(e) => e.key === "Escape" && setMode(null)}
          onSubmit={(e) => {
            e.preventDefault();
            void issue.run(() => sendJson(placementUrl(placement.id, "invoice-draft/issue"), "POST", {
              invoice_number: v.invoice_number.trim() || null, invoice_date: v.invoice_date || null, due_date: v.due_date || null, amount: v.amount.trim() || null,
              note: v.note.trim() || null,
            }));
          }}>
          <div className="form-grid">
            {input("invoice_number", "Invoice number")}
            {input("invoice_date", "Invoice date", "date")}
            {input("due_date", "Payment due date", "date")}
            {input("amount", "Amount (₹)")}
            {input("note", "Note (optional)")}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="submit" className="btn small" disabled={issue.busy}>{issue.busy ? "Issuing…" : "Issue invoice"}</button>
            <button type="button" className="btn secondary small" onClick={() => setMode(null)}>Cancel</button>
          </div>
          <Problem failure={issue.failure} />
        </form>
      )}
      {mode === "discard" && (
        <form aria-label="Discard invoice draft" noValidate style={{ display: "grid", gap: 8 }} onKeyDown={(e) => e.key === "Escape" && setMode(null)}
          onSubmit={(e) => {
            e.preventDefault();
            void discard.run(() => sendJson(placementUrl(placement.id, "invoice-draft/cancel"), "POST", { reason: reason.trim() || null }));
          }}>
          <Field id={fid("reason")} label="Why is this draft not needed?" error={discard.errors.reason}>
            <textarea id={fid("reason")} rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)}
              aria-invalid={discard.errors.reason ? true : undefined} aria-describedby={discard.errors.reason ? `${fid("reason")}-error` : undefined} />
          </Field>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="submit" className="btn small" disabled={discard.busy}>{discard.busy ? "Discarding…" : "Discard draft"}</button>
            <button type="button" className="btn secondary small" onClick={() => setMode(null)}>Cancel</button>
          </div>
          <Problem failure={discard.failure} />
        </form>
      )}
    </div>
  );
}

/** pob-026 (S10): one side's survey -- not due yet, not sent (why), sent / reminded, or the answer. */
function SurveyCard({ title, survey }: { title: string; survey: Survey }) {
  return (
    <section className="action-card" style={{ gap: 6 }} aria-label={title}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <strong>{title}</strong>
        {survey && <span className="badge">{survey.status_label}</span>}
      </div>
      {!survey && <p className="muted" style={{ margin: 0 }}>Sent {SURVEY_AFTER_DAYS} days after joining.</p>}
      {survey?.status === "skipped" && <p className="muted" style={{ margin: 0 }}>{survey.skip_reason_label}</p>}
      {survey?.status === "sent" && (
        <p className="muted" style={{ margin: 0 }}>
          Sent <LocalTime value={survey.sent_at} />{survey.resent_at && <>; reminder sent <LocalTime value={survey.resent_at} /></>}. No answer yet.
        </p>
      )}
      {survey?.status === "responded" && (
        <>
          <p style={{ margin: 0 }}><strong>{survey.rating} / 5</strong> <span className="muted">· <LocalTime value={survey.responded_at} /></span></p>
          <p style={{ margin: 0, overflowWrap: "anywhere", whiteSpace: "pre-line" }}>{survey.comment ?? <span className="muted">No comment.</span>}</p>
        </>
      )}
    </section>
  );
}

/** pob-024: one placement -- the record, the candidate and client confirmations, the PO owner and the invoice draft review. */
export default function PlacementDetail({ initial }: { initial: Placement }) {
  const [p, setP] = useState(initial);
  const [notice, setNotice] = useState<string | null>(null);
  const changed: Changed = (next, text) => {
    setP(next);
    setNotice(text);
  };
  const c = p.commercials;
  const person = (x: Placement["recruiter"]) => (x ? x.full_name : "Not set");
  return (
    <div style={{ display: "grid", gap: 12 }}>
      <p role="status" className="muted" style={{ margin: 0, minHeight: "1em" }}>{notice}</p>
      <section className="action-card" style={{ gap: 8 }} aria-label="Placement">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
          <strong>{p.candidate.name}</strong>
          <span className="muted" style={{ fontSize: 13 }}>{p.candidate.code}</span>
          <span className="badge">{p.status_label}</span>
        </div>
        <Facts rows={[
          ["Role", p.role],
          ["Requirement", <Link key="r" href={`/recruiter/requirements/${encodeURIComponent(p.requirement.id)}`} style={LINK_STYLE}>{p.requirement.title} ({p.requirement.code})</Link>],
          ["Client", p.company.name],
          ...(p.vendor ? [["Vendor", p.vendor.name] as [string, ReactNode]] : []),
          ["Source", p.source ?? "Not recorded"],
          ["Recruiter", person(p.recruiter)],
          ["PO owner", person(p.po_owner)],
          ...(p.package ? [["Package", `${p.package.currency} ${Number(p.package.compensation).toLocaleString("en-IN")}`] as [string, ReactNode]] : []),
          ["Expected joining", p.joining.expected_joining_date ? formatCalendarDate(p.joining.expected_joining_date) : "Not set"],
          ["Joined on", p.joining.actual_joining_date ? formatCalendarDate(p.joining.actual_joining_date) : "Not yet"],
        ]} />
        {p.permissions.can_change_owner && <OwnerPicker placement={p} onChanged={changed} />}
      </section>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 18rem), 1fr))" }}>
        <ConfirmationCard placement={p} side="candidate" title="Candidate confirmation" onChanged={changed} />
        <ConfirmationCard placement={p} side="client" title="Client confirmation" onChanged={changed} />
      </div>
      {p.satisfaction && (
        <section aria-labelledby={`${p.id}-satisfaction`} style={{ display: "grid", gap: 8 }}>
          <h3 id={`${p.id}-satisfaction`} style={{ margin: 0, fontSize: 16 }}>Satisfaction</h3>
          <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 18rem), 1fr))" }}>
            <SurveyCard title="Client survey" survey={p.satisfaction.client} />
            <SurveyCard title="Candidate survey" survey={p.satisfaction.candidate} />
          </div>
        </section>
      )}
      {c && (
        <section className="action-card" style={{ gap: 8 }} aria-label="Invoice">
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
            <strong>Invoice</strong>
            <span className="badge">{c.invoice.status_label}</span>
          </div>
          <Facts rows={[
            ["Expected fee", c.expected_fee === null ? "Not priced" : inr(c.expected_fee)],
            ...(c.invoice.status !== "none" ? [
              ["Draft amount", c.invoice.draft_amount === null ? "Enter on issue" : inr(c.invoice.draft_amount)] as [string, ReactNode],
              ["Draft due date", c.invoice.draft_due_date ? formatCalendarDate(c.invoice.draft_due_date) : "Not set"] as [string, ReactNode],
            ] : []),
          ]} />
          {c.invoice.status === "none" && <p className="muted" style={{ margin: 0 }}>A draft is created when the candidate joins.</p>}
          {c.invoice.discard_reason && <p style={{ margin: 0, overflowWrap: "anywhere" }}>Discarded: {c.invoice.discard_reason}</p>}
          {p.permissions.can_invoice && <DraftReview placement={p} onChanged={changed} />}
          {c.invoice.invoice && <ul style={{ padding: 0, margin: 0 }}><RecruiterInvoiceCard invoice={c.invoice.invoice} /></ul>}
        </section>
      )}
    </div>
  );
}
