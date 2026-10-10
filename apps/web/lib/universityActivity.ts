// upc-013 (DEC-SCOPE-163): a university's communication history (§12) -- the row the API sends (`services/university_timeline.py`) and
// how each kind reads. Keys arrive for meetings, visits, agreements, documents and tasks; the labels are the ones their own sections
// already use. Display only: the API decides who reads it (TL2: the upc-012 `COMMS_READERS`) and what it holds.
import { EMAIL_TITLE, EXCERPT, duration, type TimelineEntry } from "@/lib/leadTimeline";
import { EVENT_LABELS, MEETING_TYPES } from "@/lib/meetings";
import { KIND_LABEL, type TaskKind } from "@/lib/partnershipTasks";
import { AGREEMENT_STATUSES, AGREEMENT_TYPES } from "@/lib/universityAgreements";
import { DOCUMENT_KINDS } from "@/lib/universityDocuments";
import { dateText, EVENT_ACTIONS, VISIT_STATUSES } from "@/lib/visits";

type ActivityKind = "stage" | "call" | "message" | "meeting" | "visit" | "agreement" | "task" | "document";
export type ActivityRow = {
  id: string; kind: ActivityKind; at: string; actor: { id: string; full_name: string } | null; event: string | null;
  from_value: string; from_label: string; to_value: string; to_label: string; subject: string | null; status: string | null;
  reason: string | null; duration_seconds: number | null; scheduled_for: string | null;
};

export const universityTimelineUrl = (universityId: string) => `/api/v1/partnership/universities/${encodeURIComponent(universityId)}/timeline`;

const TONE = { stage: "var(--blue)", contact: "var(--green)", plan: "var(--amber)", owner: "var(--navy)", stop: "var(--red)" };
const TASK_VERB: Record<string, string> = { scheduled: "added", done: "done", cancelled: "cancelled" };
const compact = (parts: (string | null | undefined | false)[]) => parts.filter((p): p is string => !!p);
const pick = (labels: Record<string, string>, key: string) => labels[key] ?? key;
const contact = (row: ActivityRow, prefix: string) => (row.to_label ? `${prefix} ${row.to_label}` : "Contact removed");

function stageTitle(row: ActivityRow): string {
  if (row.event === "lost") return "Marked Lost / Closed";
  if (row.event === "reopened") return `Reopened at ${row.to_label}`;
  return `Stage: ${row.from_label} → ${row.to_label}`;
}

function agreementTitle(row: ActivityRow): string {
  const name = `${pick(AGREEMENT_TYPES, row.status ?? "")} ${row.subject ?? ""}`.trim();
  if (row.event === "create") return `${name} created`;
  if (row.event === "renew") return `${name} renewed`;
  if (row.event === "update") return `${name} edited`;
  return `${name}: ${pick(AGREEMENT_STATUSES, row.from_value)} → ${pick(AGREEMENT_STATUSES, row.to_value)}`;
}

/** Who did it. No actor: the system. */
export function activityActor(row: ActivityRow): string {
  return row.actor ? row.actor.full_name : "System";
}

export function activityEntry(row: ActivityRow): TimelineEntry {
  const base = { meta: [] as string[], when: null, detail: row.reason ? (row.reason.length >= EXCERPT ? `${row.reason}…` : row.reason) : null };
  switch (row.kind) {
    case "stage":
      return { ...base, badge: "Stage", tone: row.event === "lost" ? TONE.stop : TONE.stage, title: stageTitle(row) };
    case "call":
      return { ...base, badge: "Call", tone: TONE.contact, title: `${row.event === "incoming" ? "Incoming" : "Outgoing"} call: ${row.from_label}`,
        meta: compact([contact(row, "With"), row.duration_seconds != null && `Duration ${duration(row.duration_seconds)}`]) };
    case "message": {
      const email = row.event === "email";
      return { ...base, badge: email ? "Email" : "WhatsApp", tone: row.status === "failed" ? TONE.stop : TONE.contact,
        title: email ? EMAIL_TITLE[row.status ?? "queued"] ?? "Email" : "WhatsApp sent",
        meta: compact([contact(row, "To"), row.from_value || "Custom message", email && row.subject && `Subject: ${row.subject}`]) };
    }
    case "meeting":
      return { ...base, badge: "Meeting", tone: row.event === "cancelled" ? TONE.stop : TONE.plan,
        title: `Meeting ${row.event === "completed" ? "completed" : pick(EVENT_LABELS, row.event ?? "").toLowerCase()}: ${pick(MEETING_TYPES, row.from_value)}`,
        meta: compact([row.subject]), when: row.event !== "completed" && row.scheduled_for ? { label: "For", value: row.scheduled_for } : null };
    case "visit":
      return { ...base, badge: "Visit", tone: row.event === "reject" ? TONE.stop : TONE.plan,
        title: `Visit ${pick(EVENT_ACTIONS, row.event ?? "").toLowerCase()}`,
        meta: compact([row.subject, row.to_value && `Status: ${pick(VISIT_STATUSES, row.to_value)}`]) };
    case "agreement":
      return { ...base, badge: "Agreement", tone: TONE.owner, title: agreementTitle(row) };
    case "task": {
      const kind = KIND_LABEL[row.from_value as TaskKind] ?? row.from_value;
      return { ...base, badge: kind, tone: row.event === "cancelled" ? TONE.stop : TONE.plan,
        title: `${kind} ${TASK_VERB[row.event ?? ""] ?? row.event}: ${row.subject ?? ""}`,
        meta: row.event === "scheduled" ? compact([row.to_value && `Due ${dateText(row.to_value)}`, row.to_label && `Assigned to ${row.to_label}`]) : [] };
    }
    case "document":
      return { ...base, badge: "Document", tone: TONE.owner,
        title: row.event === "new_version" ? `New version (v${row.to_value}): ${row.subject}` : `Document added: ${row.subject}`,
        meta: [pick(DOCUMENT_KINDS, row.from_value)] };
    default:
      return { ...base, badge: "Activity", tone: TONE.stage, title: String((row as { kind: string }).kind) };
  }
}
