import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolChildOverview, { ChildStatusRow, type ChildOverview } from "@/components/SchoolChildOverview";

// ENH-026 (spec §5.3 C14, §7): the Parent Portal shows counselling status and structured fields, the new "in_progress" module status,
// and recommendations from counselling sessions beside the older recommendation notes.
vi.mock("@/lib/api", () => ({ serverApi: vi.fn() }));

afterEach(cleanup);

const base: ChildOverview = {
  student: { id: "s1", student_code: "A1B2C3D4", full_name: "Asha R", date_of_birth: null, grade_or_class: "Grade 8-A", school_name: "Sunrise School", assigned_teacher_name: null },
  career_guidance: { status: "in_progress", sessions: [{ id: "g1", school_student_id: "s1", record_type: "guidance_session", notes: "Planned.", created_at: "2026-09-01T00:00:00Z", status: "scheduled", scheduled_for: "2026-10-01T04:30:00Z" }] },
  counselling: { status: "completed", notes: [{ id: "c1", school_student_id: "s1", record_type: "counselling_note", notes: "Met.", created_at: "2026-09-02T00:00:00Z", status: "completed", weak_areas: ["Essays"] }] },
  recommended_careers: [],
  structured_recommendations: [{ record_id: "c1", record_type: "counselling_note", created_at: "2026-09-02T00:00:00Z", recommended_careers: ["Architect"], recommended_courses: null, recommended_stream: null, recommended_skills: null }],
  psychometric: { status: "not_started", assessments: [] },
  results: [],
  activities: { attended: [], upcoming: [] },
};

describe("Parent Portal counselling (ENH-026)", () => {
  it("shows each record's status and structured fields", () => {
    render(<SchoolChildOverview overview={base} />);
    const counselling = screen.getByRole("heading", { name: "Counselling" }).closest(".card") as HTMLElement;
    expect(within(counselling).getByText("Completed")).toBeTruthy();
    expect(within(counselling).getByText("Essays")).toBeTruthy();
    const guidance = screen.getByRole("heading", { name: "Career guidance" }).closest(".card") as HTMLElement;
    expect(within(guidance).getByText("Scheduled")).toBeTruthy();
  });

  it("lists recommendations from counselling sessions instead of the empty message", () => {
    render(<SchoolChildOverview overview={base} />);
    const card = screen.getByRole("heading", { name: "Recommended careers" }).closest(".card") as HTMLElement;
    expect(within(card).getByText("Architect")).toBeTruthy();
    expect(within(card).queryByText(/No career recommendation yet/)).toBeNull();
  });

  it("words the in-progress module status", () => {
    render(<ChildStatusRow overview={base} />);
    expect(screen.getByText("In progress")).toBeTruthy();
  });
});
