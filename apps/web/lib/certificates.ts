// nehn-031 (DEC-SCOPE-296): the certificate eligibility returned by `GET /workflows/it/certificates/eligibility/{id}` and the queue.
export type CertificateRules = { min_progress_percent: number; min_attendance_percent: number };
export type CertificateCriteria = {
  eligible: boolean;
  progress_percent: number;
  attendance_percent: number;
  assignments_graded: number;
  assignments_total: number;
  assessments_passed: number;
  assessments_total: number;
  pending_fee: number;
  rules: CertificateRules;
  certificate_issued?: boolean; // only on the eligibility route (QA31-04)
};

export function criteriaSummary(c: CertificateCriteria): string {
  const facts = `progress ${c.progress_percent}% (needs ${c.rules.min_progress_percent}%), attendance ${c.attendance_percent}% (needs ${c.rules.min_attendance_percent}%), assignments graded ${c.assignments_graded}/${c.assignments_total}, assessments passed ${c.assessments_passed}/${c.assessments_total}, pending fee ${c.pending_fee}`;
  return c.eligible ? `Eligible: ${facts}.` : `Not yet eligible: ${facts}.`;
}
