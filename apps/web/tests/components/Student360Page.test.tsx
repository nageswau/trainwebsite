import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// A plain function stand-in for serverApi (not vi.fn): these routes make one resolving and one rejecting call in the same render,
// and a reset vi.fn that has recorded a rejected promise is reported by vitest as a test failure even when the page handles it.
const api = vi.hoisted(() => ({ calls: [] as string[], impl: (() => Promise.resolve({})) as (path: string) => Promise<unknown> }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }), usePathname: () => "/x" }));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, serverApi: (path: string) => { api.calls.push(path); return api.impl(path); } };
});

import CounselorPage from "@/app/school/career-counselor/students/[id]/360/page";
import TeacherPage from "@/app/school/teacher/students/[id]/360/page";
import Student360Directory from "@/components/Student360Directory";
import { ApiError } from "@/lib/api";
import type { Student360, Tab360 } from "@/lib/student360";
import { TAB_KEYS } from "@/lib/student360Links";

beforeEach(() => { api.calls = []; });
afterEach(cleanup);

const EMPTY: Student360 = {
  student: { id: "s1", full_name: "Asha Rao", school_name: "North School", student_code: null, grade_or_class: null, date_of_birth: null, assigned_teacher_name: null },
  career_goal: null,
  can_edit_career_goal: true,
  tabs: Object.fromEntries(TAB_KEYS.map((k): [string, Tab360] => [k, { status: "restricted", count: null, not_tracked: [], data: {} }])) as Student360["tabs"],
};

const args = (tab?: string) => ({ params: Promise.resolve({ id: "s1" }), searchParams: Promise.resolve(tab ? { tab } : {}) });

describe("Student 360° routes", () => {
  it("shows Access unavailable with the server's own reason when the API refuses the teacher", async () => {
    api.impl = (path) => (path === "/api/v1/auth/me" ? Promise.resolve({ role: "school_teacher", full_name: "Tara" }) : Promise.reject(new ApiError("This student is not assigned to you", 403)));
    render(await TeacherPage(args()));
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeInTheDocument();
    expect(screen.getByText("This student is not assigned to you")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /go to your dashboard/i })).toHaveAttribute("href", "/school/teacher/dashboard");
  });

  it("fetches the 360 payload for the id in the URL and opens the requested tab", async () => {
    api.impl = (path) => Promise.resolve(path === "/api/v1/auth/me" ? { role: "career_counselor", full_name: "Chris" } : EMPTY);
    render(await CounselorPage(args("certificates")));
    expect(api.calls).toContain("/api/v1/school/students/s1/360-view");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Asha Rao");
    expect(screen.getByRole("tab", { name: /^certificates/i })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("link", { name: /back to dashboard/i })).toHaveAttribute("href", "/school/career-counselor/dashboard");
  });
});

describe("Student360Directory", () => {
  it("links each portfolio student to the role's 360 route", () => {
    render(<Student360Directory role="psychometric_team" students={[{ id: "a", full_name: "Asha", school_name: "North" }]} />);
    expect(screen.getByRole("link", { name: /asha/i })).toHaveAttribute("href", "/school/psychometric-team/students/a/360");
  });

  it("renders nothing for an empty portfolio -- the dashboard's own panel already says so (sch-004 regression)", () => {
    const { container } = render(<Student360Directory role="psychometric_team" students={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
