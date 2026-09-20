import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolGradeHistory, { loadGradeHistory, type GradeHistoryEntry } from "@/components/SchoolGradeHistory";
import { serverApi } from "@/lib/api";

// ENH-004 -- read-only grade history (spec §7, §7.1). `serverApi` reads next/headers cookies, so it is mocked.
vi.mock("@/lib/api", () => ({ serverApi: vi.fn() }));

const state = (label: string | null, level: number | null, year: string | null) => ({ academic_year_id: year ? `y-${year}` : null, academic_year_label: year, grade_level: level, grade_or_class: label });

const promoted: GradeHistoryEntry = { id: "h1", action: "promoted", created_at: "2026-09-19T10:00:00Z", from: state("Grade 8-A", 8, null), to: state("Grade 9-A", 9, "2026-27") };
const heldBack: GradeHistoryEntry = { id: "h2", action: "held_back", created_at: "2026-09-19T11:00:00Z", from: state("Grade 8-B", 8, "2025-26"), to: state("Grade 8-B", 8, "2026-27") };

afterEach(() => {
  cleanup();
  vi.mocked(serverApi).mockReset();
});

describe("SchoolGradeHistory", () => {
  it("says so when the student has never been promoted", () => {
    render(<SchoolGradeHistory history={[]} />);
    expect(screen.getByText("No promotions recorded yet.")).toBeTruthy();
  });

  it("states a promotion in text: an outcome badge, the move, and the year (no prior year on a first transition)", () => {
    render(<SchoolGradeHistory history={[promoted]} />);
    expect(screen.getByText("Promoted")).toBeTruthy();
    expect(screen.getByText("Moved from Grade 8-A to Grade 9-A")).toBeTruthy();
    expect(screen.getByText("Academic year: 2026-27")).toBeTruthy();
  });

  it("states a hold-back in text, with the year range", () => {
    render(<SchoolGradeHistory history={[heldBack]} />);
    expect(screen.getByText("Held back")).toBeTruthy();
    expect(screen.getByText("Kept in Grade 8-B")).toBeTruthy();
    expect(screen.getByText("Academic year: 2025-26 to 2026-27")).toBeTruthy();
  });

  it("keeps the order it is given (the API returns newest first)", () => {
    render(<SchoolGradeHistory history={[heldBack, promoted]} />);
    const titles = screen.getAllByRole("heading", { level: 4 }).map((h) => h.textContent);
    expect(titles).toEqual(["Kept in Grade 8-B", "Moved from Grade 8-A to Grade 9-A"]);
  });

  it("falls back to the numeric grade, then to an honest 'not set', when there is no label", () => {
    const noLabel: GradeHistoryEntry = { ...promoted, id: "h3", from: state(null, 8, null), to: state(null, null, "2026-27") };
    render(<SchoolGradeHistory history={[noLabel]} />);
    expect(screen.getByText("Moved from Grade 8 to Grade not set")).toBeTruthy();
  });
});

describe("loadGradeHistory", () => {
  it("reads the student's grade-history endpoint", async () => {
    vi.mocked(serverApi).mockResolvedValue({ student: { id: "s1", full_name: "Child" }, history: [] });
    await loadGradeHistory("s1");
    expect(serverApi).toHaveBeenCalledWith("/api/v1/school/students/s1/grade-history");
  });
});
