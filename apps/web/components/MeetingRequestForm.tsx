"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useId, useState } from "react";

import { BDM_TYPE_LABEL } from "@/lib/bdm";
import { nowIstInput } from "@/lib/bdmAppointments";
import { fieldErrors } from "@/lib/bdmTravel";
import { isRequestBody, sendJson } from "@/lib/apiErrors";
import { EMPTY_DRAFT, requestBody, type RequestDraft, type RequestOptions, TEL_REQUEST_OPTIONS_URL, TEL_REQUESTS_URL } from "@/lib/meetingRequests";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

// Form order, so the first refused field is the one focused (the API's keys: proposed_at is the "when" input).
const ORDER = ["request_type", "bdm_user_id", "organization_name", "person_name", "contact_phone", "contact_email", "proposed_at", "mode", "location", "purpose", "remarks"] as const;
const REQUIRED: [keyof RequestDraft, string, string][] = [
  ["request_type", "request_type", "Choose the meeting type."], ["organization_name", "organization_name", "Enter the organization."],
  ["person_name", "person_name", "Enter the person to meet."], ["contact_phone", "contact_phone", "Enter a phone number."],
  ["when", "proposed_at", "Choose the date and time."], ["purpose", "purpose", "Enter the purpose."],
];

/** tel-019 (EVID-019 §9; MR1, MR5, MR7): request a meeting with a BDM. The BDM list follows the meeting type's module (a corporate meeting
 *  goes to college BDMs); "Any … BDM" sends it to that module's pool. The API checks everything again. */
export default function MeetingRequestForm() {
  const router = useRouter();
  const idp = useId();
  const focus = useFocusAfterRender();
  const [options, setOptions] = useState<RequestOptions | "failed" | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [draft, setDraft] = useState<RequestDraft>(EMPTY_DRAFT);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useLeaveGuard(JSON.stringify(draft) !== JSON.stringify(EMPTY_DRAFT) && !busy, "Discard this request?");

  useEffect(() => {
    const controller = new AbortController();
    fetch(TEL_REQUEST_OPTIONS_URL, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Request failed (${response.status})`);
        setOptions((await response.json()) as RequestOptions);
      })
      .catch(() => controller.signal.aborted || setOptions("failed"));
    return () => controller.abort();
  }, [attempt]);

  const id = (key: string) => `${idp}-${key}`;
  const clear = (field: string) => setErrors((e) => (e[field] ? Object.fromEntries(Object.entries(e).filter(([k]) => k !== field)) : e));
  const set = (key: keyof RequestDraft, value: string) => {
    // a new type drops a BDM of another module
    setDraft((d) => ({ ...d, [key]: value, ...(key === "request_type" ? { bdm_user_id: "" } : {}) }));
    clear(key === "when" ? "proposed_at" : key);
  };

  function refuse(found: Record<string, string>, message: string) {
    setErrors(found);
    setFailure(message);
    const first = ORDER.find((key) => found[key]);
    focus(...(first ? [id(first)] : []), id("message"));
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const local = Object.fromEntries(REQUIRED.filter(([key]) => !draft[key].trim()).map(([, field, message]) => [field, message]));
    if (Object.keys(local).length) return refuse(local, "Check the highlighted fields.");
    setErrors({});
    setFailure(null);
    setBusy(true);
    const outcome = await sendJson(TEL_REQUESTS_URL, "POST", requestBody(draft));
    setBusy(false);
    if (!outcome.ok) {
      const mapped = fieldErrors(outcome.detail);
      if (Object.keys(mapped).length) return refuse(mapped, "Check the highlighted fields.");
      const server = (outcome.status ?? 0) >= 500;
      return refuse({}, server ? "We couldn't send the request. Please try again — your entry is kept." : outcome.message);
    }
    if (!isRequestBody(outcome.data)) return refuse({}, "Unable to send the request.");
    setDraft(EMPTY_DRAFT);
    const code = (outcome.data as { code?: unknown }).code;
    router.push(`/telecaller/meeting-requests?filed=${encodeURIComponent(typeof code === "string" ? code : "")}`);
  }

  if (options === null) return <p className="muted" role="status">Loading the request form…</p>;
  if (options === "failed") {
    return (
      <p className="form-error" role="alert">
        Unable to load the request form. <button type="button" className="btn secondary small" onClick={() => { setOptions(null); setAttempt((n) => n + 1); }}>Try again</button>
      </p>
    );
  }

  const bdmType = options.types.find((t) => t.key === draft.request_type)?.bdm_type;
  const bdms = bdmType ? options.bdms[bdmType] : [];
  const invalid = (key: string) => (errors[key] ? { "aria-invalid": true as const, "aria-describedby": `${id(key)}-error` } : {});
  const error = (key: string) => errors[key] && <p id={`${id(key)}-error`} className="form-error" style={{ margin: 0 }}>{errors[key]}</p>;
  const input = (key: "organization_name" | "person_name" | "contact_phone" | "contact_email" | "location", label: string, max: number, extra: object = {}) => (
    <div className="field">
      <label htmlFor={id(key)}>{label}</label>
      <input id={id(key)} maxLength={max} value={draft[key]} disabled={busy} onChange={(e) => set(key, e.target.value)} {...extra} {...invalid(key)} />
      {error(key)}
    </div>
  );
  const area = (key: "purpose" | "remarks", label: string, max: number, required: boolean) => (
    <div className="field">
      <label htmlFor={id(key)}>{label}</label>
      <textarea id={id(key)} rows={3} maxLength={max} value={draft[key]} disabled={busy} aria-required={required} onChange={(e) => set(key, e.target.value)} {...invalid(key)} />
      {error(key)}
    </div>
  );
  return (
    <form onSubmit={send} noValidate aria-label="Request a BDM meeting" style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))" }}>
        <div className="field">
          <label htmlFor={id("request_type")}>Meeting type</label>
          <select id={id("request_type")} value={draft.request_type} disabled={busy} aria-required onChange={(e) => set("request_type", e.target.value)} {...invalid("request_type")}>
            <option value="">Choose a type</option>
            {options.types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
          {error("request_type")}
        </div>
        <div className="field">
          <label htmlFor={id("bdm_user_id")}>BDM</label>
          <select id={id("bdm_user_id")} value={draft.bdm_user_id} disabled={busy || !bdmType} onChange={(e) => set("bdm_user_id", e.target.value)} {...invalid("bdm_user_id")}>
            {bdmType ? <option value="">Any {BDM_TYPE_LABEL[bdmType]} BDM</option> : <option value="">Choose the meeting type first</option>}
            {bdms.map((b) => <option key={b.id} value={b.id}>{b.full_name}</option>)}
          </select>
          {bdmType && bdms.length === 0 && <p className="muted" style={{ margin: 0, fontSize: 13 }}>There is no active {BDM_TYPE_LABEL[bdmType]} BDM yet; the request waits for one.</p>}
          {error("bdm_user_id")}
        </div>
        {input("organization_name", "Organization", 200, { "aria-required": true })}
        {input("person_name", "Person to meet", 200, { "aria-required": true })}
        {input("contact_phone", "Phone", 30, { type: "tel", "aria-required": true, autoComplete: "off" })}
        {input("contact_email", "Email (optional)", 255, { type: "email", autoComplete: "off" })}
        <div className="field">
          <label htmlFor={id("proposed_at")}>Proposed date and time (IST)</label>
          <input id={id("proposed_at")} type="datetime-local" min={nowIstInput()} value={draft.when} disabled={busy} aria-required
            onChange={(e) => set("when", e.target.value)} {...invalid("proposed_at")} />
          {error("proposed_at")}
        </div>
        <div className="field">
          <label htmlFor={id("mode")}>Mode</label>
          <select id={id("mode")} value={draft.mode} disabled={busy} onChange={(e) => set("mode", e.target.value)} {...invalid("mode")}>
            {options.modes.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          {error("mode")}
        </div>
        {input("location", "Meeting link or location (optional)", 255)}
      </div>
      {area("purpose", "Purpose", 1000, true)}
      {area("remarks", "Remarks (optional)", 2000, false)}
      {failure && <p id={id("message")} tabIndex={-1} className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
      <div className="actions">
        <button type="submit" className="btn" disabled={busy}>{busy ? "Sending…" : "Send request"}</button>
      </div>
    </form>
  );
}
