// ccrm-027 (DEC-SCOPE-259): an application's enrolment confirmation. The server (services/application_enrollment.py) is the authority on
// every rule; this mirrors its payload for the counselor's Enrolment panel.
import type { OfferDocument } from "@/lib/applicationOffers";

export type EnrollmentView = {
  status: string;
  confirmed: boolean;
  confirmed_at: string | null;
  can_confirm: boolean;
  enrollment_date: string | null;
  university_student_id: string | null;
  course_start_date: string | null;
  pre_enrollment_checklist_complete: boolean;
  document: OfferDocument | null;
};
export type EnrollmentPayload = { enrollment: EnrollmentView; documents: OfferDocument[] };

const APPLICATION_URL = (id: string) => `/api/v1/workflows/overseas/applications/${id}`;
export const enrollmentUrl = (id: string) => `${APPLICATION_URL(id)}/enrollment`;
export const enrollmentDocumentsUrl = (id: string) => `${APPLICATION_URL(id)}/enrollment-documents`;

/** The panel is offered from the offer stage on, and stays readable once enrolled. */
export const showsEnrollment = (stage: string) => ["offer", "visa_documentation", "status_tracking", "enrolled"].includes(stage);
