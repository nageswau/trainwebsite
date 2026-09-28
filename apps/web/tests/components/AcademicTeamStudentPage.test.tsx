import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// QA24-01 (ENH-024 browser QA): academic_team is one of the three portfolio writers (DEC-SCOPE-031 D10) but had no screen to write
// from. It now gets a student page with the editable Digital Portfolio, reached the way the coordinator reaches hers: directory ->
// student page -> "Open 360° view", and the 360° view's back link returns to the student page.
// Same serverApi stand-in as Student360Page.test.tsx (a plain function, not vi.fn -- see that file's note).
const api = vi.hoisted(() => ({ calls: [] as string[], impl: (() => Promise.resolve({})) as (path: string) => Promise<unknown> }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }), usePathname: () => "/x" }));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, serverApi: (path: string) => { api.calls.push(path); return api.impl(path); } };
});

import AcademicStudent360Page from "@/app/school/academic-team/students/[id]/360/page";
import AcademicStudentPage from "@/app/school/academic-team/students/[id]/page";
import Student360Directory from "@/components/Student360Directory";
import { ApiError } from "@/lib/api";
import type { PortfolioData } from "@/lib/portfolio";
import type { Student360, Tab360 } from "@/lib/student360";
import { TAB_KEYS } from "@/lib/student360Links";

beforeEach(() => { api.calls = []; });
afterEach(cleanup);

const ME = { role: "academic_team", full_name: "Anu Academic" };
const PORTFOLIO: PortfolioData = {
  student: { id: "s1", full_name: "Asha Rao" },
  completion_percentage: 6, can_edit: true, profile_complete: false,
  academic_achievements: [], psychometric_report: [], career_guidance: [], languages: [],
  entries: { project: [], internship: [], competition: [], sport: [], leadership: [], volunteering: [], extracurricular: [], award: [], skill: [],
    certification: [{ id: "c1", section: "certification", title: "Retail Sales Associate", description: null, organization: null, date_from: null, date_to: null, certification_type: "skill_india", certification_status: "enrolled", certificate_number: null, issued_on: null, created_at: "2026-01-01", updated_at: "2026-01-01" }] },
  personal_statement: null,
};
const args = { params: Promise.resolve({ id: "s1" }) };

describe("Academic Team student page (QA24-01)", () => {
  it("shows the student's editable Digital Portfolio with links to the 360° view and the dashboard", async () => {
    api.impl = (path) => Promise.resolve(path === "/api/v1/auth/me" ? ME : PORTFOLIO);
    render(await AcademicStudentPage(args));
    expect(api.calls).toContain("/api/v1/school/students/s1/portfolio");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Asha Rao");
    expect(screen.getByRole("link", { name: "Open 360° view" })).toHaveAttribute("href", "/school/academic-team/students/s1/360");
    expect(screen.getByRole("link", { name: "Back to dashboard" })).toHaveAttribute("href", "/school/academic-team/dashboard");
    expect(screen.getByRole("heading", { name: "Digital Portfolio" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add certification" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Retail Sales Associate" })).toBeInTheDocument();
  });

  it("shows Access unavailable with the server's reason when the student is outside the team's portfolio", async () => {
    api.impl = (path) => (path === "/api/v1/auth/me" ? Promise.resolve(ME) : Promise.reject(new ApiError("This student is at a school outside your own portfolio", 403)));
    render(await AcademicStudentPage(args));
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeInTheDocument();
    expect(screen.getByText("This student is at a school outside your own portfolio")).toBeInTheDocument();
  });

  it("the Academic Team's 360° view links back to the student page", async () => {
    const view: Student360 = {
      student: { id: "s1", full_name: "Asha Rao", school_name: "North School", student_code: null, grade_or_class: null, date_of_birth: null, assigned_teacher_name: null },
      career_goal: null, can_edit_career_goal: false,
      tabs: Object.fromEntries(TAB_KEYS.map((k): [string, Tab360] => [k, { status: "restricted", count: null, not_tracked: [], data: {} }])) as Student360["tabs"],
    };
    api.impl = (path) => Promise.resolve(path === "/api/v1/auth/me" ? ME : view);
    render(await AcademicStudent360Page({ params: Promise.resolve({ id: "s1" }), searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("link", { name: "Back to student" })).toHaveAttribute("href", "/school/academic-team/students/s1");
  });

  it("the directory opens the Academic Team's student page; other service roles keep the 360° link", () => {
    const students = [{ id: "a", full_name: "Asha", school_name: "North" }];
    const { unmount } = render(<Student360Directory role="academic_team" students={students} />);
    expect(screen.getByRole("link", { name: /asha/i })).toHaveAttribute("href", "/school/academic-team/students/a");
    unmount();
    render(<Student360Directory role="career_counselor" students={students} />);
    expect(screen.getByRole("link", { name: /asha/i })).toHaveAttribute("href", "/school/career-counselor/students/a/360");
  });
});
