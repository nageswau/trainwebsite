// itc-011: the one-step IT conversion (lead -> IT student, enrolment, fee plan, onboarding checklist) and the onboarding checklist.
// Types, endpoints and the form -> body mapping. The API decides scope and every rule (stage, batch seats, fee plan, duplicates).
import { sendRequest, type SendOutcome } from "@/lib/apiErrors";
import type { FeeAccount } from "@/components/FeeAccountSummary";

/** Qualified up to Counselling Completed: the stages the API converts from (mirrors lead_handover.convertible_stage). */
export const CONVERTIBLE_STAGES = ["qualified", "interested", "follow_up", "counselling_scheduled", "counselling_completed"];
export const MAX_INSTALLMENTS = 12;

export type ConvertBatch = {
  id: string; name: string; program_id: string; program: string; fee: number; start_date: string; end_date: string;
  schedule: string; mode: string | null; available: number; recommended: boolean;
};
export type ConvertOptions = {
  prefill: { full_name: string; email: string | null; phone: string | null; fee: number | null; recommended_program_id: string | null; recommended_course: string | null };
  batches: ConvertBatch[];
  checklist: string[];
};
export type ChecklistItem = { id: string; label: string; position: number; done: boolean; done_at: string | null };
export type ConversionResult = {
  student: { id: string; full_name: string; email: string; student_code: string | null; setup: string | null };
  enrollment: { id: string; enrollment_code: string; status: string; course: string; batch: string };
  fee_account: FeeAccount;
  checklist: ChecklistItem[];
  lead: Record<string, unknown>;
  replayed: boolean;
  email_status?: string;
};
export type Installment = { amount: string; due_date: string };
export type ConvertEntry = { full_name: string; email: string; phone: string; batch_id: string; fee: string; installments: Installment[] };

export const counselorConvertUrl = (leadId: string) => `/api/v1/counselor/leads/${encodeURIComponent(leadId)}/convert-it`;
export const adminConvertUrl = (leadId: string) => `/api/v1/admin/leads/${encodeURIComponent(leadId)}/convert-it`;
export const onboardingUrl = (enrollmentId: string, itemId?: string) =>
  `/api/v1/it/enrollments/${encodeURIComponent(enrollmentId)}/onboarding${itemId ? `/${encodeURIComponent(itemId)}` : ""}`;

/** One key per opened dialog: a resubmit after a dropped connection replays instead of converting twice. */
export const newIdempotencyKey = () => (globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`).replace(/[^A-Za-z0-9._:-]/g, "");

/** Two decimal places, as the API stores money; a blank or non-number is NaN. */
export const money = (value: string) => (value.trim() === "" ? NaN : Math.round(Number(value) * 100) / 100);

/** What the form can check before sending (the API checks everything again); null when it looks sendable. */
export function entryProblem(entry: ConvertEntry, existingStudent: boolean): string | null {
  if (!existingStudent && (!entry.full_name.trim() || !entry.email.trim())) return "Add the student's name and email.";
  if (!entry.batch_id) return "Choose a batch.";
  const fee = money(entry.fee);
  if (!Number.isFinite(fee) || fee < 0) return "Enter a fee of 0 or more.";
  if (!entry.installments.length) return null;
  if (fee === 0) return "A fee of 0 takes no installments.";
  if (entry.installments.some((i) => !(money(i.amount) > 0) || !i.due_date)) return "Give each installment an amount above 0 and a due date.";
  const total = entry.installments.reduce((sum, i) => sum + money(i.amount), 0);
  if (Math.round(total * 100) !== Math.round(fee * 100)) return "The installments must add up to the fee.";
  return null;
}

export function convertBody(entry: ConvertEntry, existingStudentId: string | null) {
  const plan = { batch_id: entry.batch_id, fee: money(entry.fee).toFixed(2), installments: entry.installments.map((i) => ({ amount: money(i.amount).toFixed(2), due_date: i.due_date })) };
  if (existingStudentId) return { student_id: existingStudentId, ...plan };
  return { student: { full_name: entry.full_name.trim(), email: entry.email.trim(), phone: entry.phone.trim() || null }, ...plan };
}

export const convert = (url: string, body: unknown, key: string): Promise<SendOutcome> =>
  sendRequest(url, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(body) });

/** A coded 409 (`{code, message}`) reads its own message; sendRequest's generic text covers everything else. */
export function failureText(outcome: Extract<SendOutcome, { ok: false }>): { text: string; studentExists: boolean } {
  const detail = outcome.detail as { code?: string; message?: string } | undefined;
  if (detail && typeof detail === "object" && !Array.isArray(detail) && detail.message) return { text: detail.message, studentExists: detail.code === "student_exists" };
  return { text: outcome.message, studentExists: false };
}
