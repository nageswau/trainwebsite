// itc-026 (DEC-SCOPE-350): the IT student's resume versions -- types and endpoints shared by the student, counselor, IT Admin and HR
// views. The API decides who may read or upload, the type (by the file's bytes) and the size limit; the client only pre-checks the size.
import type { PersonRef } from "@/lib/telecallerLeads";

export type ResumeVisibility = "hr" | "private";
export type StudentResumeVersion = {
  version: number; file_name: string | null; content_type: string; size_bytes: number; visibility: ResumeVisibility;
  uploaded_by: PersonRef | null; uploaded_by_role: string | null; created_at: string;
};
export type StudentResumeList = { items: StudentResumeVersion[]; max_bytes: number; can_upload: boolean };
export type ResumeSettings = { max_mb: number; max_bytes: number; min_mb: number; max_mb_ceiling: number };

export const MY_RESUMES_URL = "/api/v1/it/me/resumes";
export const RESUME_SETTINGS_URL = "/api/v1/admin/it/resume-settings";
export const RESUME_ACCEPT = ".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

const PREFIX = { counselor: "/api/v1/counselor/it/students", admin: "/api/v1/admin/it/students", hr: "/api/v1/hr/students" } as const;
export const studentResumesUrl = (portal: keyof typeof PREFIX, studentId: string) => `${PREFIX[portal]}/${encodeURIComponent(studentId)}/resumes`;
export const resumeFileUrl = (listUrl: string, version: number) => `${listUrl}/${version}/file`;

const ROLE_LABELS: Record<string, string> = { it_student: "student", counselor: "counselor", it_admin: "IT Admin" };
export const uploaderLabel = (v: StudentResumeVersion) =>
  v.uploaded_by ? `${v.uploaded_by.full_name}${v.uploaded_by_role && ROLE_LABELS[v.uploaded_by_role] ? ` (${ROLE_LABELS[v.uploaded_by_role]})` : ""}` : "";
export const megabytes = (bytes: number) => `${Math.floor(bytes / (1024 * 1024))} MB`;
