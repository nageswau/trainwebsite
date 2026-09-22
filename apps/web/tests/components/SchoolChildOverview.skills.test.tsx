import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolChildOverview, { ChildStatusRow, type ChildOverview } from "@/components/SchoolChildOverview";

// ENH-011 spec §7: the Parent Portal Skills section (DEC-SCOPE-026 D5) and its two status chips. `serverApi` reads next/headers
// cookies, so it is mocked like the other server-component tests.
vi.mock("@/lib/api", () => ({ serverApi: vi.fn() }));

const base: ChildOverview = {
  student: { id: "s1", student_code: "A1B2C3D4", full_name: "Asha R", date_of_birth: null, grade_or_class: "Grade 8-A", school_name: "Sunrise School", assigned_teacher_name: null },
  career_guidance: { status: "not_started", sessions: [] },
  counselling: { status: "not_started", notes: [] },
  recommended_careers: [],
  psychometric: { status: "not_started", assessments: [] },
  results: [],
  activities: { attended: [], upcoming: [] },
};

const skills: NonNullable<ChildOverview["skills"]> = {
  soft_skills: {
    status: "certified",
    enrollments: [{
      id: "e1", batch_id: "b1", batch_title: "Leadership", topic: "Teamwork", trainer_name: "R. Iyer", start_date: "2026-10-01", end_date: null, status: "certified", frozen: false,
      completed_at: null, certified_at: "2026-11-01T10:00:00Z", attendance: { present: 1, marked: 1 },
      assessments: [{ name: "Speech", max_score: 20, score: 16, remarks: "Pace" }, { name: "Final", max_score: 50, score: null, remarks: null }],
    }],
  },
  digital_skills: { status: "not_started", enrollments: [] },
};

afterEach(cleanup);

describe("Parent Portal Skills", () => {
  it("shows each module with the batch, status in words, attendance and scores", () => {
    render(<SchoolChildOverview overview={{ ...base, skills }} />);
    const card = screen.getByRole("heading", { name: "Skills" }).closest(".card") as HTMLElement;
    expect(within(card).getByRole("heading", { name: "Soft Skills" })).toBeTruthy();
    expect(within(card).getByText(/Leadership/)).toBeTruthy();
    expect(within(card).getByText("Certified")).toBeTruthy();
    expect(within(card).getByText("Attended 1 of 1 session")).toBeTruthy();
    expect(within(card).getByText("Speech: 16 / 20 — Pace")).toBeTruthy();
    expect(within(card).getByText("Final: not scored yet")).toBeTruthy();
    expect(within(card).getByText("Not enrolled in a Digital Skills batch yet.")).toBeTruthy();
  });

  it("says when a batch was at a previous school", () => {
    const moved = { ...skills, soft_skills: { ...skills.soft_skills, enrollments: [{ ...skills.soft_skills.enrollments[0], frozen: true }] } };
    render(<SchoolChildOverview overview={{ ...base, skills: moved }} />);
    expect(screen.getByText(/at a previous school/)).toBeTruthy();
  });

  it("renders an overview without the skills key (an older API) and shows no Skills section", () => {
    render(<SchoolChildOverview overview={base} />);
    expect(screen.queryByRole("heading", { name: "Skills" })).toBeNull();
    expect(screen.getByText("Asha R", { exact: false })).toBeTruthy();
  });

  it("adds a chip for each module to the status row", () => {
    render(<ChildStatusRow overview={{ ...base, skills }} />);
    expect(within(screen.getByText("Soft skills").parentElement!).getByText("Certified")).toBeTruthy();
    expect(within(screen.getByText("Digital skills").parentElement!).getByText("Not started")).toBeTruthy();
  });
});
