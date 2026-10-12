"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmTravel";
import {
  DISCUSSIONS_API, DISCUSSIONS_HOME, roleLabel, STATUS_LABEL, type DiscussionDetail, type DiscussionOptions, type DiscussionStatus,
} from "@/lib/managementDiscussions";
import { useHydrated } from "@/lib/useHydrated";

type Values = {
  topic: string; discussion_date: string; department: string; points: string; decision: string; responsible_user_id: string; deadline: string;
  status: DiscussionStatus; follow_up_date: string; participant_ids: string[];
};
type Field = keyof Values;

function initial(discussion: DiscussionDetail | undefined, today: string): Values {
  if (!discussion) {
    return { topic: "", discussion_date: today, department: "", points: "", decision: "", responsible_user_id: "", deadline: "", status: "open", follow_up_date: "", participant_ids: [] };
  }
  return {
    topic: discussion.topic, discussion_date: discussion.discussion_date, department: discussion.department ?? "", points: discussion.points ?? "",
    decision: discussion.decision ?? "", responsible_user_id: discussion.responsible?.id ?? "", deadline: discussion.deadline ?? "", status: discussion.status,
    follow_up_date: discussion.follow_up_date ?? "", participant_ids: discussion.participants.map((p) => p.id),
  };
}

/** The body the API takes: optional text and dates as null when blank. */
function body(values: Values): Record<string, unknown> {
  const blank = (value: string) => (value.trim() ? value.trim() : null);
  return {
    topic: values.topic.trim(), discussion_date: values.discussion_date, department: blank(values.department), points: blank(values.points),
    decision: blank(values.decision), responsible_user_id: values.responsible_user_id || null, deadline: values.deadline || null, status: values.status,
    follow_up_date: values.follow_up_date || null, participant_ids: values.participant_ids,
  };
}

/** What the browser can check before sending; the API checks everything again (active staff, dates). */
function validate(values: Values): Partial<Record<Field, string>> {
  const errors: Partial<Record<Field, string>> = {};
  const length = (value: string) => value.trim().length;
  if (length(values.topic) < 2 || length(values.topic) > 200) errors.topic = "Give the topic (2-200 characters)";
  if (!values.discussion_date) errors.discussion_date = "Choose the discussion date";
  if (values.department.trim() && (length(values.department) < 2 || length(values.department) > 80)) errors.department = "Use 2-80 characters";
  if (values.decision.trim() && (length(values.decision) < 2 || length(values.decision) > 500)) errors.decision = "Use 2-500 characters";
  else if (!values.decision.trim() && values.responsible_user_id) errors.decision = "Record the decision before naming a responsible person";
  else if (!values.decision.trim() && values.deadline) errors.decision = "Record the decision before setting a deadline";
  if (values.deadline && values.discussion_date && values.deadline < values.discussion_date) errors.deadline = "The deadline can't be before the discussion date";
  if (values.follow_up_date && values.discussion_date && values.follow_up_date < values.discussion_date) errors.follow_up_date = "The follow-up date can't be before the discussion date";
  return errors;
}

// mgmt-027 (MD1-MD7): a new discussion or a change to one. An edit sends only the fields that changed, so nothing unchanged is
// re-recorded in the audit trail. Attachments are added on the discussion's page once it is saved.
export default function DiscussionForm({ options, today, discussion }: { options: DiscussionOptions; today: string; discussion?: DiscussionDetail }) {
  const router = useRouter();
  const ready = useHydrated();
  const [values, setValues] = useState<Values>(() => initial(discussion, today));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const sending = useRef(false); // QA-01: a second click before the re-render disables the form is ignored
  const [search, setSearch] = useState("");
  const set = (key: Field, value: string) => {
    setValues((v) => ({ ...v, [key]: value }));
    setErrors((e) => Object.fromEntries(Object.entries(e).filter(([field]) => field !== key))); // QA-02: a changed field drops its old error
  };

  // A person named earlier who has since left still shows, so the current value is never silently dropped.
  const people = [...options.users];
  for (const p of [discussion?.responsible, ...(discussion?.participants ?? [])]) if (p && !people.some((u) => u.id === p.id)) people.push(p);
  const shown = people.filter((p) => values.participant_ids.includes(p.id) || p.full_name.toLowerCase().includes(search.trim().toLowerCase()));

  const fieldProps = (key: Field) => ({ id: `discussion-${key}`, "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `discussion-${key}-error` : undefined });
  const error = (key: Field) => errors[key] && <p className="form-error" id={`discussion-${key}-error`}>{errors[key]}</p>;
  const dateField = (key: "discussion_date" | "deadline" | "follow_up_date", label: string, max?: string) => (
    <div className="field">
      <label htmlFor={`discussion-${key}`}>{label}</label>
      <input type="date" max={max} value={values[key]} onChange={(e) => set(key, e.target.value)} {...fieldProps(key)} />
      {error(key)}
    </div>
  );
  const toggle = (id: string) => setValues((v) => ({ ...v, participant_ids: v.participant_ids.includes(id) ? v.participant_ids.filter((x) => x !== id) : [...v.participant_ids, id] }));

  async function save() {
    if (sending.current) return;
    const found = validate(values);
    setErrors(found);
    if (Object.keys(found).length) {
      setMessage("Check the highlighted fields.");
      document.getElementById(`discussion-${Object.keys(found)[0]}`)?.focus();
      return;
    }
    let payload = body(values);
    if (discussion) {
      const before = body(initial(discussion, today));
      const same = (key: string) => JSON.stringify(key === "participant_ids" ? [...(payload[key] as string[])].sort() : payload[key]) === JSON.stringify(key === "participant_ids" ? [...(before[key] as string[])].sort() : before[key]);
      payload = Object.fromEntries(Object.entries(payload).filter(([key]) => !same(key)));
      if (Object.keys(payload).length === 0) {
        router.push(`${DISCUSSIONS_HOME}/${discussion.id}`);
        return;
      }
    }
    sending.current = true;
    setBusy(true);
    setMessage("");
    const saved = discussion ? await sendJson(`${DISCUSSIONS_API}/${discussion.id}`, "PATCH", payload) : await sendJson(DISCUSSIONS_API, "POST", payload);
    if (!saved.ok) {
      const placed = fieldErrors(saved.detail);
      setErrors(placed);
      setMessage(Object.keys(placed).length ? "Check the highlighted fields." : saved.message);
      sending.current = false;
      setBusy(false);
      return;
    }
    router.push(`${DISCUSSIONS_HOME}/${discussion?.id ?? String(saved.data.id)}`);
    router.refresh(); // the discussion page may be cached from before this change
  }

  return (
    <form className="form action-card" noValidate aria-label={discussion ? "Edit discussion" : "New discussion"} onSubmit={(e) => { e.preventDefault(); void save(); }}>
      <fieldset disabled={!ready || busy} className="form" style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
        <div className="field">
          <label htmlFor="discussion-topic">Topic</label>
          <input type="text" maxLength={200} value={values.topic} onChange={(e) => set("topic", e.target.value)} {...fieldProps("topic")} />
          {error("topic")}
        </div>
        <div className="form-grid">
          {dateField("discussion_date", "Date", today)}
          <div className="field">
            <label htmlFor="discussion-department">Department (optional)</label>
            <input type="text" maxLength={80} value={values.department} onChange={(e) => set("department", e.target.value)} {...fieldProps("department")} />
            {error("department")}
          </div>
        </div>
        <fieldset style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }} aria-describedby={errors.participant_ids ? "discussion-participant_ids-error" : undefined}>
          <legend style={{ fontWeight: 800, fontSize: 13, marginBottom: 7 }}>Participants (optional)</legend>
          <input type="search" aria-label="Find a participant" placeholder="Find by name" value={search} onChange={(e) => setSearch(e.target.value)} style={{ marginBottom: 8 }} />
          <div style={{ maxHeight: 220, overflowY: "auto", display: "grid", gap: 6, padding: 4 }}>
            {shown.length === 0 && <span className="muted">No staff member matches.</span>}
            {shown.map((p) => (
              <label key={p.id} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input type="checkbox" style={{ width: "auto" }} checked={values.participant_ids.includes(p.id)} onChange={() => toggle(p.id)} />
                {p.full_name} ({roleLabel(p.role)})
              </label>
            ))}
          </div>
          {errors.participant_ids && <p className="form-error" id="discussion-participant_ids-error">{errors.participant_ids}</p>}
        </fieldset>
        <div className="field">
          <label htmlFor="discussion-points">Discussion points (optional)</label>
          <textarea rows={5} maxLength={10000} value={values.points} onChange={(e) => set("points", e.target.value)} {...fieldProps("points")} />
          <span className="muted" style={{ fontSize: 13 }}>Management only: the responsible person never sees these notes.</span>
          {error("points")}
        </div>
        <div className="field">
          <label htmlFor="discussion-decision">Decision (optional)</label>
          <input type="text" maxLength={500} value={values.decision} onChange={(e) => set("decision", e.target.value)} {...fieldProps("decision")} />
          {error("decision")}
        </div>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="discussion-responsible_user_id">Person responsible (optional)</label>
            <select value={values.responsible_user_id} onChange={(e) => set("responsible_user_id", e.target.value)} {...fieldProps("responsible_user_id")}>
              <option value="">No one yet</option>
              {people.map((p) => <option key={p.id} value={p.id}>{p.full_name} ({roleLabel(p.role)})</option>)}
            </select>
            {error("responsible_user_id")}
          </div>
          {dateField("deadline", "Deadline (optional)")}
          <div className="field">
            <label htmlFor="discussion-status">Status</label>
            <select value={values.status} onChange={(e) => set("status", e.target.value)} {...fieldProps("status")}>
              {Object.entries(STATUS_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            {error("status")}
          </div>
          {dateField("follow_up_date", "Follow-up date (optional)")}
        </div>
        <p className="muted" style={{ fontSize: 13, margin: 0 }}>The responsible person is notified and sees only the decision, its deadline and status, and any attachment you share with them.</p>
        {message && <p className="form-error" role="alert">{message}</p>}
        <div className="actions">
          <button className="btn" type="submit">{busy ? "Saving…" : discussion ? "Save changes" : "Save discussion"}</button>
          <a className="btn ghost" href={discussion ? `${DISCUSSIONS_HOME}/${discussion.id}` : DISCUSSIONS_HOME}>Cancel</a>
        </div>
      </fieldset>
    </form>
  );
}
