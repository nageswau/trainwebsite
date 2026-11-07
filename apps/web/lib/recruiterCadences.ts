/** pob-008 (DEC-SCOPE-423 B5-B9): outreach cadences -- the Team Lead's library and a contact's run of one, started on an outreach message. */
import { MESSAGES_URL } from "@/lib/recruiterMessages";

export const CADENCES_URL = "/api/v1/recruiter/cadences";
export const cadenceUrl = (id: string) => `${CADENCES_URL}/${encodeURIComponent(id)}`;
export const messageCadenceUrl = (messageId: string) => `${MESSAGES_URL}/${encodeURIComponent(messageId)}/cadence`;

export const CHANNELS = [
  { key: "email", label: "Email" }, { key: "whatsapp", label: "WhatsApp" }, { key: "linkedin", label: "LinkedIn" }, { key: "call", label: "Call" },
] as const;
export type CadenceChannel = (typeof CHANNELS)[number]["key"];
export const channelLabel = (key: string) => CHANNELS.find((c) => c.key === key)?.label ?? key;
export const MAX_STEPS = 10;
export const MAX_DAY = 90;
export const NAME_MAX = 120;
export const DESCRIPTION_MAX = 500;

export type CadenceStep = { day: number; channel: CadenceChannel; template: { id: string; name: string } | null };
export type Cadence = { id: string; name: string; description: string | null; active: boolean; steps: CadenceStep[]; updated_at: string; can_edit: boolean };
export type CadenceList = { items: Cadence[]; can_edit: boolean };

/** The run started on a message (null when none). */
export type CadenceRun = {
  id: string; cadence_id: string; name: string; status: "active" | "replied" | "stopped" | "completed"; step: number; steps: number;
  next_step_at: string | null; end_reason: string | null; ended_at: string | null; can_stop: boolean;
};

const END_LABELS: Record<string, string> = {
  reply: "the contact replied", do_not_contact: "Do not contact", not_interested: "not interested", inactive: "contact deactivated",
  archived: "company archived", manual: "stopped by hand", last_step: "all steps done",
};
export const endLabel = (reason: string | null) => (reason ? END_LABELS[reason] ?? reason : "");

/** "Day 0 Email → Day 3 LinkedIn → Day 7 Call" */
export const stepsSummary = (steps: { day: number; channel: string }[]) => steps.map((s) => `Day ${s.day} ${channelLabel(s.channel)}`).join(" → ");

export type StepTemplate = { id: string; name: string; channel: string };

/** Every approved shared template (a personal one is never approved), page after page -- the step pickers filter by channel. */
export async function approvedTemplates(signal?: AbortSignal): Promise<StepTemplate[]> {
  const items: StepTemplate[] = [];
  for (;;) {
    const response = await fetch(`/api/v1/recruiter/templates?status=approved&limit=100&offset=${items.length}`, { signal });
    const body = (await response.json().catch(() => null)) as { items?: StepTemplate[]; total?: number } | null;
    if (!response.ok || !body || !Array.isArray(body.items)) throw new Error(`Request failed (${response.status})`);
    items.push(...body.items.map(({ id, name, channel }) => ({ id, name, channel })));
    if (!body.items.length || items.length >= (body.total ?? 0)) return items;
  }
}

/** The client's copy of the API's step rules (B5), so a mistake is shown before the round trip; the API stays the gate. */
export function stepsError(steps: { day: string }[]): string | null {
  if (steps.length < 2 || steps.length > MAX_STEPS) return `Add 2 to ${MAX_STEPS} steps`;
  const days = steps.map((s) => (/^\d+$/.test(s.day.trim()) ? Number(s.day) : NaN));
  if (days.some((d) => Number.isNaN(d) || d > MAX_DAY)) return `Each day is a whole number from 0 to ${MAX_DAY}`;
  if (days[0] !== 0) return "The first step is on day 0 (the outreach that starts the cadence)";
  if (days.some((d, i) => i > 0 && d <= days[i - 1])) return "Each step must come on a later day than the one before";
  return null;
}
