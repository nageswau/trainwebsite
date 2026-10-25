// ccrm-030 (DEC-SCOPE-270, RM1/RM9/RM10): the Overseas Admin's counselor reminder rules. The API owns the catalogue, the ranges and every
// check; the page shows what it returns and sends one rule at a time.
export const REMINDER_RULES_API = "/api/v1/overseas-admin/reminder-rules";
export const REMINDER_RULES_HOME = "/overseas/admin/reminder-rules";

export type ReminderTiming = "assign" | "silent" | "before" | "after" | "escalate";
export type ReminderRule = {
  key: string; label: string; description: string; action: "task" | "notify"; timing: ReminderTiming;
  min_offset: number; max_offset: number; enabled: boolean; offset_days: number; notify_student: boolean | null; updated_at: string | null;
};
export type ReminderLogItem = { id: string; rule_key: string; rule_label: string; summary: string; task_created: boolean; recipients: number; created_at: string };
export type ReminderLogPage = { items: ReminderLogItem[]; total: number; limit: number; offset: number };
export type ReminderRunCounts = { created: number; duplicate: number; skipped: number; failed: number; rules: Record<string, number> };

/** What the offset means for each timing, read as "<n> <unit>". */
const UNITS: Record<ReminderTiming, string> = {
  assign: "days after assignment (task due)",
  silent: "days without a call or stage change",
  before: "days before the date",
  after: "days after the date",
  escalate: "days overdue before the Overseas Admin is told", // ccrm-031 (DEC-SCOPE-272)
};

export function offsetUnit(timing: ReminderTiming): string {
  return UNITS[timing];
}

export function actionLabel(rule: Pick<ReminderRule, "action">): string {
  return rule.action === "task" ? "Task + notice" : "Notice";
}

/** The browser's check before a save; the API checks the same range again. */
export function offsetError(rule: Pick<ReminderRule, "min_offset" | "max_offset">, raw: string): string | null {
  const value = Number(raw);
  if (raw.trim() === "" || !Number.isInteger(value) || value < rule.min_offset || value > rule.max_offset) return `Choose a whole number from ${rule.min_offset} to ${rule.max_offset}`;
  return null;
}

export function runSummary(counts: ReminderRunCounts): string {
  const parts = [`${counts.created} new reminder${counts.created === 1 ? "" : "s"}`, `${counts.duplicate} already sent`];
  if (counts.skipped) parts.push(`${counts.skipped} skipped (no active counselor)`);
  if (counts.failed) parts.push(`${counts.failed} failed`);
  return `${parts.join(" · ")}.`;
}
