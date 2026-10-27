import { PAYMENT_STATE_LABELS, unlocksWhen, type PaymentLock } from "@/lib/studentAccess";
import type { PortalPayload } from "@/lib/types";

// nehn-018 (DEC-SCOPE-303 AC1): a student feature their payment state does not unlock yet -- shown in place of the feature, never hidden,
// with the one step that opens it. A student with no enrolment has nothing to pay yet, so they are sent to choose a course.
export default function LockedFeatureCard({ lock }: { lock: PaymentLock }) {
  const enrol = lock.current_state === "registered";
  return (
    <div className="action-card">
      <h3>{lock.label} is locked</h3>
      <p>{lock.label} opens once {unlocksWhen(lock.required_state)}.</p>
      <p className="muted">Your payment status: {PAYMENT_STATE_LABELS[lock.current_state]}</p>
      <a className="btn small" href={enrol ? "/it/student/course" : "/it/student/fees"}>{enrol ? "Choose a course" : "Complete payment to unlock"}</a>
    </div>
  );
}

/** A locked portal section: its heading, then the card (no empty table, no actions). */
export function LockedSection({ data, lock }: { data: PortalPayload; lock: PaymentLock }) {
  return (
    <div className="portal-content">
      <div className="portal-title">
        <div><div className="eyebrow">Workspace</div><h2>{data.title}</h2><p className="muted">{data.subtitle}</p></div>
      </div>
      <LockedFeatureCard lock={lock} />
    </div>
  );
}
