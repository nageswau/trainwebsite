// ENH-011 -- shapes of the skills-tracker API (docs/superpowers/specs/2026-09-22-enh-011-skills-tracker-design.md §5) and how a
// status is shown. Status is always a text label plus a class, never colour alone. Safe for client components (no server imports).

import type { SchoolRef } from "@/lib/transfers";

export type SkillModule = "soft_skills" | "digital_skills";
export type SkillBatchStatus = "open" | "closed";
export const ENROLMENT_STATUSES = ["enrolled", "completed", "certified", "withdrawn"] as const;
export type SkillEnrollmentStatus = (typeof ENROLMENT_STATUSES)[number];

export type SkillAttendanceSummary = { present: number; marked: number };

export type SkillBatch = {
  id: string;
  school: SchoolRef;
  module_type: SkillModule;
  title: string;
  topic: string | null;
  trainer_name: string | null;
  start_date: string;
  end_date: string | null;
  status: SkillBatchStatus;
  enrolled_count: number;
  created_at: string;
};

export type SkillEnrollment = {
  id: string;
  batch_id: string;
  school_student_id: string;
  student_name: string;
  status: SkillEnrollmentStatus;
  frozen: boolean;
  completed_at: string | null;
  certified_at: string | null;
  created_at: string;
  attendance: SkillAttendanceSummary;
  scores: { assessment_id: string; score: number; remarks: string | null }[];
};

export type SkillSession = { id: string; session_date: string; topic: string | null; attendance: { enrollment_id: string; present: boolean }[] };
export type SkillAssessment = { id: string; name: string; max_score: number };
export type SkillBatchDetail = SkillBatch & { enrollments: SkillEnrollment[]; sessions: SkillSession[]; assessments: SkillAssessment[] };

/** One portfolio student as `GET /school/portfolio-students` returns it (SCH-004). */
export type PortfolioStudent = { id: string; full_name: string; school_id: string; school_name: string };

export const MODULE_LABEL: Record<SkillModule, string> = { soft_skills: "Soft Skills", digital_skills: "Digital Skills" };

export const ENROLMENT_LABEL: Record<SkillEnrollmentStatus, string> = { enrolled: "Enrolled", completed: "Completed", certified: "Certified", withdrawn: "Withdrawn" };
// `.status` is the positive tone; `.status.pending` the neutral one (globals.css).
export const ENROLMENT_CLASS: Record<SkillEnrollmentStatus, string> = { enrolled: "status pending", completed: "status", certified: "status", withdrawn: "status pending" };

/** Mirrors the API's TRANSITIONS (app/api/school_skills.py): the UI never offers a change the API would refuse. */
export const TRANSITIONS: Record<SkillEnrollmentStatus, SkillEnrollmentStatus[]> = {
  enrolled: ["completed", "certified", "withdrawn"],
  completed: ["certified", "enrolled"],
  withdrawn: ["enrolled"],
  certified: [],
};

export function attendanceText({ present, marked }: SkillAttendanceSummary): string {
  if (marked === 0) return "No attendance yet";
  return `Attended ${present} of ${marked} session${marked === 1 ? "" : "s"}`;
}

/** Attendance and scores are taken only for a live enrolment of a student still at the batch's school. */
export function canMark(enrolment: Pick<SkillEnrollment, "status" | "frozen">): boolean {
  return !enrolment.frozen && (enrolment.status === "enrolled" || enrolment.status === "completed");
}
