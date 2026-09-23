import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolActivitiesPanel from "@/components/SchoolActivitiesPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
afterEach(cleanup);

const past = "2026-01-10T09:00:00Z";
const future = "2099-01-10T09:00:00Z";

// ENH-018 spec §7.4: the only change to the SCH-001 Activities list is a link to the Feedback page on eligible rows.
describe("SchoolActivitiesPanel (ENH-018 link)", () => {
  it("offers Give feedback only on typed activities that have taken place, and keeps Mark attendance on every row", () => {
    render(
      <SchoolActivitiesPanel
        students={[]}
        activities={[
          { id: "1", title: "Career Seminar", scheduled_at: past, activity_type: "career_seminar" },
          { id: "2", title: "Sports Day", scheduled_at: past, activity_type: null },
          { id: "3", title: "Campus Visit", scheduled_at: future, activity_type: "campus_visit" },
        ]}
      />,
    );
    const rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[0]).getByRole("link", { name: "Give feedback for Career Seminar" })).toHaveAttribute("href", "/school/coordinator/feedback");
    expect(within(rows[1]).queryByRole("link")).toBeNull();
    expect(within(rows[2]).queryByRole("link")).toBeNull();
    for (const row of rows) expect(within(row).getByRole("button", { name: "Mark attendance" })).toBeTruthy();
  });
});
