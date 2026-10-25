import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import OverdueByCounselor from "@/components/OverdueByCounselor";
import { overdueTasksHref, type OverdueByCounselorPage } from "@/lib/counselorTasks";
import { offsetUnit } from "@/lib/reminderRules";

// ccrm-031 (DEC-SCOPE-271, E7/E8): the Overseas Admin's "Overdue by counselor" section on the counselor-tasks page.
const page = (over: Partial<OverdueByCounselorPage> = {}): OverdueByCounselorPage => ({
  today: "2026-10-25",
  threshold_days: 2,
  enabled: true,
  items: [
    { counselor: { id: "11111111-1111-1111-1111-111111111111", full_name: "Asha Rao" }, active: true, overdue_tasks: 3, overdue_follow_ups: 1, past_threshold: 2, oldest_due: "2026-10-15" },
    { counselor: { id: "22222222-2222-2222-2222-222222222222", full_name: "Ben Old" }, active: false, overdue_tasks: 1, overdue_follow_ups: 0, past_threshold: 0, oldest_due: "2026-10-24" },
  ],
  ...over,
});

afterEach(cleanup);

describe("OverdueByCounselor", () => {
  it("lists each counselor's overdue work with a link to their overdue tasks", () => {
    render(<OverdueByCounselor data={page()} />);
    const section = screen.getByRole("region", { name: "Overdue by counselor" });
    expect(section).toHaveAttribute("id", "overdue");
    const rows = within(section).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(within(rows[1]).getByRole("rowheader")).toHaveTextContent("Asha Rao");
    expect(rows[1]).toHaveTextContent("3");
    expect(rows[1]).toHaveTextContent("15 Oct 2026");
    expect(within(rows[2]).getByRole("rowheader")).toHaveTextContent("Ben Old (inactive)");
    expect(within(rows[1]).getByRole("link", { name: "View Asha Rao's overdue tasks" })).toHaveAttribute(
      "href",
      "/overseas/admin/counselor-tasks?counselor=11111111-1111-1111-1111-111111111111&band=overdue",
    );
    expect(section).toHaveTextContent("Work overdue by more than 2 days is escalated to every Overseas Admin once.");
    expect(within(section).getByRole("link", { name: "Reminder rules" })).toHaveAttribute("href", "/overseas/admin/reminder-rules");
  });

  it("says when escalation is off and when nobody is behind", () => {
    render(<OverdueByCounselor data={page({ enabled: false, threshold_days: 1, items: [] })} />);
    expect(screen.getByText("No counselor has overdue work.")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Overdue by counselor" })).toHaveTextContent("Escalation is switched off");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("builds the filter link and names the escalation unit", () => {
    expect(overdueTasksHref("abc")).toBe("/overseas/admin/counselor-tasks?counselor=abc&band=overdue");
    expect(offsetUnit("escalate")).toBe("days overdue before the Overseas Admin is told");
  });
});
