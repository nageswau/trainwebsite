// itc-023 (DEC-SCOPE-352): at-risk thresholds per programme (GET/PUT /admin/it/risk-thresholds, the IT Admin) and the scoped at-risk
// list (GET /it/at-risk: the IT Admin any student, an IT counselor their linked students, a trainer their batches). API_CONTRACT §12IX.

export type RiskReason = "attendance" | "assessment" | "absences";

export type RiskThreshold = {
  program_id: string;
  program: string;
  active: boolean;
  min_attendance_percent: number | null;
  min_assessment_percent: number | null;
  max_consecutive_absences: number | null;
  min_sessions: number;
  monitored: boolean;
  updated_at: string | null;
};

export type RiskFlag = {
  id: string;
  student: { id: string; full_name: string; student_code: string | null };
  program: string;
  batch: { id: string; name: string };
  reasons: RiskReason[];
  attendance_percent: string | number | null;
  assessment_percent: string | number | null;
  consecutive_absences: number;
  raised_at: string;
  cleared_at: string | null;
  clear_reason: "recovered" | "stopped" | null;
  profile_url: string | null;
};

export const RISK_THRESHOLDS_URL = "/api/v1/admin/it/risk-thresholds";
export const riskThresholdUrl = (programId: string) => `${RISK_THRESHOLDS_URL}/${encodeURIComponent(programId)}`;
export const AT_RISK_URL = "/api/v1/it/at-risk";
export const studentRiskUrl = (studentId: string) => `${AT_RISK_URL}?student_id=${encodeURIComponent(studentId)}&history=true`;

/** The flag's reasons with the figures of the last daily check, e.g. "Attendance 68%". */
export function riskReasonLabels(flag: Pick<RiskFlag, "reasons" | "attendance_percent" | "assessment_percent" | "consecutive_absences">): string[] {
  const pct = (v: string | number | null) => (v === null ? "" : ` ${Number(v).toFixed(0)}%`);
  return flag.reasons.map((reason) =>
    reason === "attendance" ? `Attendance${pct(flag.attendance_percent)}`
      : reason === "assessment" ? `Assessment average${pct(flag.assessment_percent)}`
        : `${flag.consecutive_absences} absences in a row`,
  );
}

/** A threshold row's criteria in words; "Not monitored" when all are off. */
export function thresholdSummary(t: RiskThreshold): string {
  const parts = [
    t.min_attendance_percent !== null && `Attendance below ${t.min_attendance_percent}% (after ${t.min_sessions} sessions)`,
    t.min_assessment_percent !== null && `Assessment average below ${t.min_assessment_percent}%`,
    t.max_consecutive_absences !== null && `${t.max_consecutive_absences} absences in a row`,
  ].filter(Boolean);
  return parts.length ? parts.join("; ") : "Not monitored";
}

export const formatRiskDate = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata" });
