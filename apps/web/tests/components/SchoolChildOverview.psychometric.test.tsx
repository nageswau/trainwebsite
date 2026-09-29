import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolChildOverview, { type ChildOverview } from "@/components/SchoolChildOverview";

// ENH-027: the Parent Portal shows the structured psychometric result under the existing status table. `serverApi` reads
// next/headers cookies, so it is mocked like the other server-component tests.
vi.mock("@/lib/api", () => ({ serverApi: vi.fn() }));
afterEach(cleanup);

const base: ChildOverview = {
  student: { id: "s1", student_code: "A1B2C3D4", full_name: "Asha R", date_of_birth: null, grade_or_class: "Grade 8-A", school_name: "Sunrise School", assigned_teacher_name: null },
  career_guidance: { status: "not_started", sessions: [] },
  counselling: { status: "not_started", notes: [] },
  recommended_careers: [],
  psychometric: { status: "completed", assessments: [
    { id: "a", assessment_type: "Aptitude Test", status: "completed", created_at: "2026-09-01T00:00:00Z", recommended_stream: ["Science (PCM)"] },
    { id: "b", assessment_type: "Interest Inventory", status: "assigned", created_at: "2026-09-02T00:00:00Z" },
  ] },
  results: [],
  activities: { attended: [], upcoming: [] },
};

describe("Parent child overview — psychometric results (ENH-027)", () => {
  it("keeps the status table and adds the structured results", () => {
    render(<SchoolChildOverview overview={base} />);
    expect(screen.getByRole("columnheader", { name: "Assigned on" })).toBeTruthy();
    expect(screen.getByText("Aptitude Test — results", { selector: "summary" })).toBeTruthy();
    expect(screen.getByText("Science (PCM)")).toBeTruthy();
    expect(screen.getByText("Interest Inventory: no results recorded yet.")).toBeTruthy();
  });
});
