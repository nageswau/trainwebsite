import { vi } from "vitest";

import type { PortfolioStudent, SkillBatchDetail, SkillEnrollment } from "@/lib/skills";

// ENH-011: shared fixtures for the batch-detail component tests.
export const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

export function stubFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const fn = vi.fn((url: string, init?: RequestInit) => Promise.resolve(handler(String(url), init)));
  vi.stubGlobal("fetch", fn);
  return fn;
}

export function enrolment(n: string, over: Partial<SkillEnrollment> = {}): SkillEnrollment {
  return {
    id: `e${n}`, batch_id: "b1", school_student_id: `s${n}`, student_name: `Student ${n}`, status: "enrolled", frozen: false,
    completed_at: null, certified_at: null, created_at: "2026-10-01T10:00:00Z", attendance: { present: 0, marked: 0 }, scores: [], ...over,
  };
}

export function detail(over: Partial<SkillBatchDetail> = {}): SkillBatchDetail {
  return {
    id: "b1", school: { id: "sch1", name: "Sunrise School" }, module_type: "soft_skills", title: "Public speaking", topic: "Presentation",
    trainer_name: "R. Iyer", start_date: "2026-10-01", end_date: "2026-12-01", status: "open", enrolled_count: 2, created_at: "2026-09-22T10:00:00Z",
    enrollments: [enrolment("1"), enrolment("2")], sessions: [], assessments: [], ...over,
  };
}

export function student(n: string): PortfolioStudent {
  return { id: `s${n}`, full_name: `Student ${n}`, school_id: "sch1", school_name: "Sunrise School" };
}
