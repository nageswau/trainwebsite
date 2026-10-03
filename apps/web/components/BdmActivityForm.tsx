"use client";
import { type FormEvent, useEffect, useId, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { localToIso, toLocalInput } from "@/lib/agentTasks";
import { sendJson } from "@/lib/apiErrors";
import {
  ACTIVITIES_URL, type Activity, activityRuleField, activityUrl, assignedOrgSearch, BACKDATE_DAYS, type Channel, CHANNEL_LABEL, CHANNELS,
  type Direction, DIRECTION_LABEL, isActivity, needsDirection, NOTE_MAX,
} from "@/lib/bdmActivities";
import { fieldErrors } from "@/lib/bdmTravel";
import { ORGS_URL } from "@/lib/bdmOrganizations";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

type ContactOption = { id: string; name: string };
type Draft = { channel: Channel; direction: Direction | null; occurredLocal: string; contactId: string; note: string };

const fromActivity = (a: Activity): Draft => ({
  channel: a.channel, direction: a.direction, occurredLocal: toLocalInput(a.occurred_at), contactId: a.contact_id ?? "", note: a.note ?? "",
});
const fresh = (): Draft => ({ channel: "call", direction: null, occurredLocal: toLocalInput(new Date().toISOString()), contactId: "", note: "" });

// bdm-009 (spec §6.3): log or edit one activity. The organization is fixed on the profile, or picked (the BDM's own assigned ones) on
// the activities page; the contacts come with it. The API decides every rule; the client only hints (direction, max time).
export default function BdmActivityForm({
  organizationId, contacts, activity, onSaved, onCancel,
}: {
  organizationId?: string;
  contacts?: ContactOption[];
  activity?: Activity;
  onSaved: (a: Activity, created: boolean) => void;
  onCancel: () => void;
}) {
  const idp = useId();
  const editing = !!activity;
  const [initial] = useState<Draft>(() => (activity ? fromActivity(activity) : fresh())); // fixed at open: "now" must not move the dirty check
  const [draft, setDraft] = useState<Draft>(initial);
  const [orgId, setOrgId] = useState(organizationId ?? activity?.organization.id ?? "");
  const [options, setOptions] = useState<ContactOption[]>(contacts ?? []);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial);
  useLeaveGuard(dirty && !busy, "Discard this activity?");

  useEffect(() => {
    if (contacts || !orgId) return;
    const controller = new AbortController();
    fetch(`${ORGS_URL}/${orgId}`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setOptions(data?.organization?.contacts?.map((c: ContactOption) => ({ id: c.id, name: c.name })) ?? []))
      .catch(() => setOptions([]));
    return () => controller.abort();
  }, [contacts, orgId]);

  const fieldId = (name: string) => `${idp}-${name}`;
  const focus = useFocusAfterRender();
  const pickerId = fieldId("organization_id");
  const picking = !organizationId && !editing;
  useEffect(() => focus(picking ? pickerId : fieldId("channel")), []); // eslint-disable-line react-hooks/exhaustive-deps -- once, on open (§12.2 F4)

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));
  // §12.2 F4: after a refused save, focus the first field that carries an error, else the top message (the TripForm pattern).
  const FIELD_ORDER = ["organization_id", "direction", "occurred_at", "contact_id", "note"];
  const focusFirst = (found: Record<string, string>) => {
    const first = FIELD_ORDER.find((name) => found[name]);
    focus(first === "direction" ? `${fieldId("direction")}-outbound` : first ? fieldId(first) : fieldId("message"));
  };
  const errorId = (name: string) => `${idp}-${name}-error`;
  const err = (name: string) => // the TripForm convention: a .form-error paragraph the input points at
    errors[name] ? <p id={errorId(name)} className="form-error">{errors[name]}</p> : null;
  const described = (name: string) => ({ "aria-invalid": errors[name] ? true : undefined, "aria-describedby": errors[name] ? errorId(name) : undefined });

  function body(): Record<string, unknown> {
    const occurred_at = localToIso(draft.occurredLocal);
    const full = { channel: draft.channel, direction: needsDirection(draft.channel) ? draft.direction : null, contact_id: draft.contactId || null,
      occurred_at, note: draft.note.trim() || null };
    if (!editing) return { organization_id: orgId, ...full };
    const before = fromActivity(activity!);
    const out: Record<string, unknown> = {};
    if (draft.channel !== before.channel) out.channel = full.channel;
    if (full.direction !== before.direction) out.direction = full.direction;
    if (draft.contactId !== before.contactId) out.contact_id = full.contact_id;
    if (draft.occurredLocal !== before.occurredLocal) out.occurred_at = full.occurred_at;
    if (draft.note !== before.note) out.note = full.note;
    return out;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const local: Record<string, string> = {};
    if (!orgId) local.organization_id = "Choose an organization.";
    if (needsDirection(draft.channel) && !draft.direction) local.direction = "Choose outgoing or incoming.";
    if (!localToIso(draft.occurredLocal)) local.occurred_at = "Enter when it happened.";
    setErrors(local);
    setFailure(null);
    if (Object.keys(local).length) {
      setFailure("Check the highlighted fields.");
      return focusFirst(local);
    }
    setBusy(true);
    const outcome = editing ? await sendJson(activityUrl(activity!.id), "PATCH", body()) : await sendJson(ACTIVITIES_URL, "POST", body());
    setBusy(false);
    if (outcome.ok && isActivity(outcome.data)) return onSaved(outcome.data, !editing);
    if (outcome.ok) {
      setFailure("Unable to save this activity.");
      return focusFirst({});
    }
    const mapped = { ...fieldErrors(outcome.detail), ...activityRuleField(outcome.detail) };
    setErrors(mapped);
    setFailure(Object.keys(mapped).length ? "Check the highlighted fields." : outcome.message);
    focusFirst(mapped);
  }

  return (
    <form onSubmit={submit} noValidate aria-label={editing ? "Edit activity" : "Log activity"} className="form-grid">
      {failure && <p id={fieldId("message")} tabIndex={-1} className="form-error" role="alert">{failure}</p>}
      {picking && (
        <div className="field">
          <SearchableSelect id={pickerId} label="Organization (required)" noun="organization" required search={assignedOrgSearch}
            onChange={(o) => { setOrgId(o?.id ?? ""); set("contactId", ""); }} />
          {err("organization_id")}
        </div>
      )}
      <div className="field">
        <label htmlFor={fieldId("channel")}>Channel (required)</label>
        <select id={fieldId("channel")} value={draft.channel}
          onChange={(e) => setDraft((d) => ({ ...d, channel: e.target.value as Channel, direction: needsDirection(e.target.value as Channel) ? d.direction : null }))}>
          {CHANNELS.map((c) => <option key={c} value={c}>{CHANNEL_LABEL[c]}</option>)}
        </select>
      </div>
      {needsDirection(draft.channel) && (
        <fieldset className="field" aria-describedby={errors.direction ? errorId("direction") : undefined}>
          <legend>Direction (required)</legend>
          {(Object.keys(DIRECTION_LABEL) as Direction[]).map((d) => (
            <label key={d} style={{ display: "flex", gap: 6, alignItems: "center", minHeight: 44 }}>
              <input id={`${fieldId("direction")}-${d}`} type="radio" name={fieldId("direction")} value={d} checked={draft.direction === d}
                onChange={() => set("direction", d)} />
              {DIRECTION_LABEL[d]}
            </label>
          ))}
          {err("direction")}
        </fieldset>
      )}
      <div className="field">
        <label htmlFor={fieldId("occurred_at")}>When (required)</label>
        <input id={fieldId("occurred_at")} type="datetime-local" value={draft.occurredLocal} max={toLocalInput(new Date().toISOString())}
          aria-invalid={errors.occurred_at ? true : undefined} aria-describedby={`${fieldId("occurred_at")}-hint${errors.occurred_at ? ` ${errorId("occurred_at")}` : ""}`}
          onChange={(e) => set("occurredLocal", e.target.value)} />
        <p id={`${fieldId("occurred_at")}-hint`} className="field-hint">Your local time. Up to {BACKDATE_DAYS} days back.</p>
        {err("occurred_at")}
      </div>
      <div className="field">
        <label htmlFor={fieldId("contact_id")}>Contact</label>
        <select id={fieldId("contact_id")} value={draft.contactId} onChange={(e) => set("contactId", e.target.value)} {...described("contact_id")}>
          <option value="">No contact</option>
          {options.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        {err("contact_id")}
      </div>
      <div className="field">
        <label htmlFor={fieldId("note")}>Note</label>
        <textarea id={fieldId("note")} value={draft.note} maxLength={NOTE_MAX} rows={3} onChange={(e) => set("note", e.target.value)}
          aria-invalid={errors.note ? true : undefined} aria-describedby={`${fieldId("note")}-hint ${fieldId("note")}-count${errors.note ? ` ${errorId("note")}` : ""}`} />
        <p id={`${fieldId("note")}-hint`} className="field-hint">Everyone who can see this organization can read this note.</p>
        <p id={`${fieldId("note")}-count`} className="muted">{draft.note.length} / {NOTE_MAX}</p>
        {err("note")}
      </div>
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : editing ? "Save changes" : "Save activity"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}
