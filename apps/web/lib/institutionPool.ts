// pob-014 (DEC-SCOPE-425): an institution's data permissions and the student pool they cover (API §12LR). The server decides who sees what;
// these are the shapes, URLs and labels.
import { collegeUrl } from "@/lib/recruiterColleges";
import { IMPORT_PATH } from "@/lib/recruiterCandidateImport";
import { APPLICATION_STAGES } from "@/lib/recruiterCandidateSearch";

export const PURPOSES = ["placement", "internship", "training", "campus_drive"] as const;
export const PURPOSE_LABEL: Record<string, string> = { placement: "Placement", internship: "Internship", training: "Training", campus_drive: "Campus drive" };
export const NOTICE_STATUSES = ["notice_sent", "consented"] as const;
export const NOTICE_LABEL: Record<string, string> = { notice_sent: "Privacy notice sent", consented: "Consent given" };
export const STATUS_LABEL: Record<string, string> = { active: "Active", scheduled: "Not started", expired: "Expired", revoked: "Revoked" };
export const ASSIGNEES_URL = "/api/v1/recruiter/candidate-tasks/assignees";

export const poolUrl = (orgId: string) => collegeUrl(orgId, "student-pool");
export const permissionsUrl = (orgId: string, ...rest: string[]) => collegeUrl(orgId, "data-permissions", ...rest);
export const importPath = (orgId: string, permissionId: string) =>
  `${IMPORT_PATH}?college=${encodeURIComponent(orgId)}&permission=${encodeURIComponent(permissionId)}`;

export type PermissionUser = { id: string; full_name: string };
export type Permission = {
  id: string; agreement_reference: string; mou_id: string | null; purposes: string[]; valid_from: string; expires_on: string; notes: string | null;
  status: "active" | "scheduled" | "expired" | "revoked"; users: PermissionUser[]; student_count: number; created_at: string; revoked_at: string | null;
};
export type Student = {
  id: string; candidate_code: string; name: string; passing_year: number | null; qualification: string | null; notice_status: string | null;
  permission_id: string; placement_status: string | null;
};
export type StudentPool = {
  college: { id: string; name: string }; can_manage: boolean; permissions: Permission[];
  students: { items: Student[]; total: number; limit: number; offset: number };
};

export function isPool(data: unknown): data is StudentPool {
  const pool = data as Partial<StudentPool> | null;
  return !!pool && Array.isArray(pool.permissions) && !!pool.students && Array.isArray(pool.students.items);
}

/** The latest application's stage as the student's placement status (S10). */
export const applicationLabel = (status: string | null) => (status ? APPLICATION_STAGES.find((s) => s.key === status)?.label ?? status : "Not applied");
