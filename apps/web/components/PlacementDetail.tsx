"use client";
import Link from "next/link";
import { type FormEvent, type ReactNode, useEffect, useId, useMemo, useRef, useState } from "react";

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
import {
  type Confirmation, type Placement, placementOf, placementPath, type PlacementRef, placementUrl, SURVEY_AFTER_DAYS, type Survey, VIA_OPTIONS,
} from "@/lib/placements";
import { recruiterSearch, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { REQUIREMENTS_URL } from "@/lib/recruiterRequirements";
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

type Option = { id: string; code: string; title: string; status: string };
const ENDED = new Set(["closed", "cancelled"]);

/** pob-025 (G6): pick one of the client's open requirements for the owed replacement; the API re-checks scope, client and status. */
function ReplacementForm({ placement, onChanged, onCancel }: { placement: Placement; onChanged: Changed; onCancel: () => void }) {
  const id = useId();
  const [options, setOptions] = useState<Option[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [jobId, setJobId] = useState(placement.guarantee?.replacement?.requirement?.id ?? "");
  const { busy, errors, failure, run } = useSubmit((p) => onChanged(p, "Replacement requirement linked."));
  useEffect(() => {
    const controller = new AbortController();
    const query = new URLSearchParams({ company_id: placement.company.id, limit: "100" });
    fetch(`${REQUIREMENTS_URL}?${query}`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body: { items?: Option[] }) => setOptions((body.items ?? []).filter((o) => !ENDED.has(o.status))))
      .catch(() => {
        if (!controller.signal.aborted) setLoadFailed(true);
      });
    return () => controller.abort();
  }, [placement.company.id]);
  const fid = `${id}-job`;
  return (
    <form aria-label="Link replacement requirement" noValidate style={{ display: "grid", gap: 8 }} onKeyDown={(e) => e.key === "Escape" && onCancel()}
      onSubmit={(e) => {
        e.preventDefault();
        if (jobId) void run(() => sendJson(placementUrl(placement.id, "replacement"), "POST", { job_id: jobId }));
      }}>
      <Field id={fid} label="Replacement requirement" error={errors.job_id}>
        {options === null && !loadFailed && <p className="muted" role="status" style={{ margin: 0 }}>Loading requirements…</p>}
        {loadFailed && <p className="form-error" role="alert" style={{ margin: 0 }}>The requirements could not be loaded. Try again.</p>}
        {options?.length === 0 && <p className="muted" style={{ margin: 0 }}>This client has no open requirement. Reopen the original or create a new one first.</p>}
        {!!options?.length && (
          <select id={fid} autoFocus value={jobId} onChange={(e) => setJobId(e.target.value)} aria-invalid={errors.job_id ? true : undefined}
            aria-describedby={errors.job_id ? `${fid}-error` : undefined}>
            <option value="">Choose a requirement</option>
            {options.map((o) => <option key={o.id} value={o.id}>{o.title} ({o.code})</option>)}
          </select>
        )}
      </Field>
      <div style={{ display: "flex", gap: 8 }}>
        <button type="submit" className="btn small" disabled={busy || !jobId}>{busy ? "Linking…" : "Link requirement"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
      <Problem failure={failure} />
    </form>
  );
}

const placementLink = (ref: PlacementRef) => <Link href={placementPath(ref.id)} style={LINK_STYLE}>{ref.candidate.name} ({ref.candidate.code})</Link>;

/** pob-025 (G3-G8, G11): the guarantee -- status, end date and days left; the dropout; the replacement owed, its requirement and its hire. */
function GuaranteeCard({ placement, onChanged }: { placement: Placement; onChanged: Changed }) {
  const g = placement.guarantee!;
  const id = useId();
  const [mode, setMode] = useState<"dropout" | "replacement" | null>(null);
  const [v, setV] = useState({ on: indiaToday(), reason: "" });
  const dropout = useSubmit((p) => {
    setMode(null);
    onChanged(p, p.guarantee?.replacement ? "Dropout recorded. A replacement is owed." : "Dropout recorded. The guarantee had ended, so no replacement is owed.");
  });
  const linked: Changed = (p, text) => {
    setMode(null);
    onChanged(p, text);
  };
  const fid = (k: string) => `${id}-${k}`;
  const invalid = (k: string) => ({ "aria-invalid": dropout.errors[k] ? true : undefined, "aria-describedby": dropout.errors[k] ? `${fid(k)}-error` : undefined });
  const r = g.replacement;
  return (
    <section className="action-card" style={{ gap: 8 }} aria-label="Replacement guarantee">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <strong>Replacement guarantee</strong>
        <span className="badge">{g.status_label}</span>
        {r && <span className="badge">{r.status_label}</span>}
      </div>
      <Facts rows={[
        ["Guarantee", g.days ? `${g.days} days` : "Not set"],
        ["Ends on", g.end_date ? formatCalendarDate(g.end_date) : placement.status === "joined" ? "No guarantee" : "Set when the candidate joins"],
        ...(g.days_left !== null ? [["Days left", g.days_left === 0 ? "Ends today" : String(g.days_left)] as [string, ReactNode]] : []),
        ...(g.dropout ? [["Dropped out on", formatCalendarDate(g.dropout.on)] as [string, ReactNode]] : []),
        ...(r?.requirement ? [["Replacement requirement", <Link key="rr" href={`/recruiter/requirements/${encodeURIComponent(r.requirement.id)}`} style={LINK_STYLE}>{r.requirement.title} ({r.requirement.code})</Link>] as [string, ReactNode]] : []),
        ...(r?.placement ? [["Replaced by", placementLink(r.placement)] as [string, ReactNode]] : []),
        ...(g.replaces ? [["Replacement for", placementLink(g.replaces)] as [string, ReactNode]] : []),
      ]} />
      {g.dropout && <p style={{ margin: 0, overflowWrap: "anywhere", whiteSpace: "pre-line" }}>Reason: {g.dropout.reason}</p>}
      {r?.status === "open" && <p className="muted" style={{ margin: 0 }}>Link the requirement that will fill the replacement. The replacement hire carries no new fee.</p>}
      {r?.status === "requested" && <p className="muted" style={{ margin: 0 }}>The next offer accepted on this requirement becomes the replacement.</p>}
      {mode === null && (placement.permissions.can_record_dropout || placement.permissions.can_request_replacement) && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {placement.permissions.can_record_dropout && <button type="button" className="btn secondary small" onClick={() => setMode("dropout")}>Record dropout</button>}
          {placement.permissions.can_request_replacement && (
            <button type="button" className="btn small" onClick={() => setMode("replacement")}>{r?.requirement ? "Change replacement requirement" : "Link replacement requirement"}</button>
          )}
        </div>
      )}
      {mode === "dropout" && (
        <form aria-label="Record dropout" noValidate style={{ display: "grid", gap: 8 }} onKeyDown={(e) => e.key === "Escape" && setMode(null)}
          onSubmit={(e) => {
            e.preventDefault();
            void dropout.run(() => sendJson(placementUrl(placement.id, "dropout"), "POST", { dropout_on: v.on || null, reason: v.reason.trim() || null }));
          }}>
          <div className="form-grid">
            <Field id={fid("dropout_on")} label="Left on" error={dropout.errors.dropout_on}>
              <input id={fid("dropout_on")} autoFocus type="date" min={placement.joining.actual_joining_date ?? undefined} max={indiaToday()} value={v.on}
                onChange={(e) => setV({ ...v, on: e.target.value })} {...invalid("dropout_on")} />
            </Field>
            <Field id={fid("reason")} label="Why did the candidate leave?" error={dropout.errors.reason}>
              <textarea id={fid("reason")} rows={2} maxLength={500} value={v.reason} onChange={(e) => setV({ ...v, reason: e.target.value })} {...invalid("reason")} />
            </Field>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="submit" className="btn small" disabled={dropout.busy}>{dropout.busy ? "Saving…" : "Record dropout"}</button>
            <button type="button" className="btn secondary small" onClick={() => setMode(null)}>Cancel</button>
          </div>
          <Problem failure={dropout.failure} />
        </form>
      )}
      {mode === "replacement" && <ReplacementForm placement={placement} onChanged={linked} onCancel={() => setMode(null)} />}
    </section>
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
  const replacementHire = !!p.guarantee?.replaces; // pob-025 G7/G12
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
      {p.guarantee && <GuaranteeCard placement={p} onChanged={changed} />}
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
            <span className="badge">{replacementHire && c.invoice.status === "none" ? "Not invoiced" : c.invoice.status_label}</span>
          </div>
          <Facts rows={[
            ["Expected fee", replacementHire ? "No fee (replacement)" : c.expected_fee === null ? "Not priced" : inr(c.expected_fee)],
            ...(c.invoice.status !== "none" ? [
              ["Draft amount", c.invoice.draft_amount === null ? "Enter on issue" : inr(c.invoice.draft_amount)] as [string, ReactNode],
              ["Draft due date", c.invoice.draft_due_date ? formatCalendarDate(c.invoice.draft_due_date) : "Not set"] as [string, ReactNode],
            ] : []),
          ]} />
          {c.invoice.status === "none" && (
            <p className="muted" style={{ margin: 0 }}>{replacementHire ? "A replacement hire gets no invoice draft." : "A draft is created when the candidate joins."}</p>
          )}
          {c.invoice.discard_reason && <p style={{ margin: 0, overflowWrap: "anywhere" }}>Discarded: {c.invoice.discard_reason}</p>}
          {p.permissions.can_invoice && <DraftReview placement={p} onChanged={changed} />}
          {c.invoice.invoice && <ul style={{ padding: 0, margin: 0 }}><RecruiterInvoiceCard invoice={c.invoice.invoice} /></ul>}
        </section>
      )}
    </div>
  );
}
