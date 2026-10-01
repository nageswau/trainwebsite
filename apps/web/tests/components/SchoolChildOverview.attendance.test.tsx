import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({ serverApi: vi.fn() }));

import { ChildStatusRow, type ChildOverview } from "@/components/SchoolChildOverview";

// ENH-030 spec §6: the parent's child card shows the last marked days as raw counts (C3); an older API without the key renders as before.
const base: ChildOverview = {
  student: { id: "s1", student_code: "S1", full_name: "Asha Rao", date_of_birth: null, grade_or_class: "Grade 5", school_name: "North", assigned_teacher_name: null },
  career_guidance: { status: "not_started", sessions: [] },
  counselling: { status: "not_started", notes: [] },
  recommended_careers: [],
  psychometric: { status: "not_started", assessments: [] },
  results: [],
  activities: { attended: [], upcoming: [] },
};
const ZERO = { present: 0, absent: 0, late: 0, excused: 0 };

afterEach(cleanup);

describe("ChildStatusRow — daily attendance (ENH-030)", () => {
  it("shows the counts over the last marked days", () => {
    const recent = Array.from({ length: 20 }, (_, i) => ({ session_date: `2026-09-${String(i + 1).padStart(2, "0")}`, status: "present" as const }));
    render(<ChildStatusRow overview={{ ...base, daily_attendance: { counts: { present: 18, absent: 1, late: 1, excused: 0 }, recent } }} />);
    expect(screen.getByText("Attendance (last 20 marked days)")).toBeTruthy();
    expect(screen.getByText("18 present · 1 late · 1 absent · 0 excused")).toBeTruthy();
  });

  it("uses the singular for one marked day", () => {
    render(<ChildStatusRow overview={{ ...base, daily_attendance: { counts: { ...ZERO, present: 1 }, recent: [{ session_date: "2026-09-30", status: "present" }] } }} />);
    expect(screen.getByText("Attendance (last 1 marked day)")).toBeTruthy();
  });

  it("says not marked yet when there are no records", () => {
    render(<ChildStatusRow overview={{ ...base, daily_attendance: { counts: ZERO, recent: [] } }} />);
    expect(screen.getByText("Attendance")).toBeTruthy();
    expect(screen.getByText("Not marked yet")).toBeTruthy();
  });

  it("renders exactly as before without the key", () => {
    render(<ChildStatusRow overview={base} />);
    expect(screen.queryByText(/^Attendance/)).toBeNull();
  });
});
