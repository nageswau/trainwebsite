// pob-027 (DEC-SCOPE-434, API §12MA): intake automation -- the task template, the escalation rules and a requirement's tasks.
export const INTAKE_SETTINGS_URL = "/api/v1/recruiter/intake-automation/settings";
export const ESCALATION_RULES_URL = "/api/v1/recruiter/escalation-rules";
export const AUTOMATION_PATH = "/recruiter/manager/automation";
export const tasksUrl = (requirementId: string) => `/api/v1/recruiter/requirements/${requirementId}/tasks`;
export const completeUrl = (requirementId: string, taskId: string) => `${tasksUrl(requirementId)}/${taskId}/complete`;

export const TEMPLATE_MAX = 10;
export const HOURS_MAX = 720;

export type TaskKind = "sourcing" | "screening";
export const TASK_KINDS: { value: TaskKind; label: string }[] = [
  { value: "sourcing", label: "Sourcing" },
  { value: "screening", label: "Screening" },
];
export const kindLabel = (kind: string) => TASK_KINDS.find((k) => k.value === kind)?.label ?? kind;

export type TemplateItem = { kind: TaskKind; title: string; due_in_hours: number };
export type IntakeSettings = { task_template: TemplateItem[] };

export type EventType = "requirement_unowned" | "requirement_task_overdue" | "follow_up_overdue";
export const EVENT_TYPES: { value: EventType; label: string; hint: string }[] = [
  { value: "requirement_unowned", label: "Requirement without an owner", hint: "hours after it was received; with no owner, every Team Lead is told" },
  { value: "requirement_task_overdue", label: "Requirement task overdue", hint: "hours past its due time" },
  { value: "follow_up_overdue", label: "Follow-up overdue", hint: "hours past its due time" },
];
export type Notify = "reporting_manager" | "all_team_leads";
export const NOTIFY: { value: Notify; label: string }[] = [
  { value: "reporting_manager", label: "The owner's Team Lead" },
  { value: "all_team_leads", label: "Every Team Lead" },
];
export const eventLabel = (value: string) => EVENT_TYPES.find((e) => e.value === value)?.label ?? value;
export const notifyLabel = (value: string) => NOTIFY.find((n) => n.value === value)?.label ?? value;

export type EscalationRule = { id: string; event_type: EventType; after_hours: number; notify: Notify; active: boolean; created_at: string };

export type RequirementTask = {
  id: string;
  kind: TaskKind;
  title: string;
  due_at: string;
  status: "open" | "done" | "cancelled";
  completed_at: string | null;
  assignee: { id: string; full_name: string } | null;
  can_complete: boolean;
};

/** Whole hours from 1 to HOURS_MAX, as typed. */
export const validHours = (text: string) => /^\d+$/.test(text) && Number(text) >= 1 && Number(text) <= HOURS_MAX;
