import type { NavItem } from "./navigation";

// nehn-018 (DEC-SCOPE-299): which IT student features unlock at which payment state (apps/api/app/services/student_access.py).
export type PaymentState = "registered" | "enrolled_pending_payment" | "partially_paid" | "fully_paid";
export type PaymentLock = { feature: string; label: string; required_state: PaymentState; current_state: PaymentState };
export type StudentAccess = { state: PaymentState; features: { key: string; label: string; unlocked: boolean; required_state: PaymentState }[] };
export type StudentAccessRules = { rules: { feature: string; label: string; min_state: PaymentState }[]; states: { key: PaymentState; label: string }[] };

export const PAYMENT_STATE_LABELS: Record<PaymentState, string> = {
  registered: "Registered",
  enrolled_pending_payment: "Enrolled, payment pending",
  partially_paid: "First payment made",
  fully_paid: "Fully paid",
};
// What the student has to reach, said as a moment ("opens once ...").
const UNLOCKS_WHEN: Record<PaymentState, string> = {
  registered: "you register",
  enrolled_pending_payment: "you enrol in a course",
  partially_paid: "your first payment is made",
  fully_paid: "your fees are fully paid",
};
export const unlocksWhen = (state: PaymentState) => UNLOCKS_WHEN[state];

// The student pages each feature lives on (the API's SECTION_FEATURES); live classes sit inside the always-open Course page.
const FEATURE_PAGES: Record<string, string[]> = {
  attendance: ["attendance"],
  assignments: ["assignments", "projects"],
  assessments: ["examinations"],
  resources: ["downloads"],
  questions: ["questions"],
  feedback: ["feedback"],
  certificates: ["certificates"],
};

export function withLocks(nav: NavItem[], access: StudentAccess | null): NavItem[] {
  if (!access) return nav;
  const locked = new Set(access.features.filter((f) => !f.unlocked).flatMap((f) => (FEATURE_PAGES[f.key] ?? []).map((page) => `/it/student/${page}`)));
  return nav.map((item) => (locked.has(item.href) ? { ...item, locked: true } : item));
}

export function featureLock(access: StudentAccess | null, key: string): PaymentLock | null {
  const entry = access?.features.find((f) => f.key === key);
  return access && entry && !entry.unlocked ? { feature: key, label: entry.label, required_state: entry.required_state, current_state: access.state } : null;
}

export function paymentLock(detail: unknown): PaymentLock | null {
  return detail && typeof detail === "object" && (detail as { code?: string }).code === "payment_required" ? (detail as PaymentLock) : null;
}
