import { describe, expect, it } from "vitest";

import { BAND_LABEL, BANDS, isTask, isTaskPage, taskUrl, tasksUrl } from "@/lib/partnershipTasks";

describe("partnershipTasks lib (upc-020)", () => {
  it("names the §20 bands in source order, then done and cancelled", () => {
    expect(BANDS.map((b) => BAND_LABEL[b])).toEqual(["Overdue", "Due today", "Due tomorrow", "Upcoming", "Done", "Cancelled"]);
  });

  it("builds list and task URLs", () => {
    expect(tasksUrl({ band: "today" })).toBe("/api/v1/partnership/tasks?band=today&limit=50&offset=0");
    expect(tasksUrl({ band: "open", university: "u 1", assignee: "team", offset: 50 })).toBe(
      "/api/v1/partnership/tasks?band=open&limit=50&offset=50&assignee=team&university_id=u+1",
    );
    expect(taskUrl("t/1", "complete")).toBe("/api/v1/partnership/tasks/t%2F1/complete");
  });

  it("recognises a task and a page", () => {
    expect(isTask({ id: "t", title: "x", due_on: "2030-01-01", permissions: {} })).toBe(true);
    expect(isTask({ id: "t" })).toBe(false);
    expect(isTaskPage({ items: [], total: 0, limit: 50, offset: 0, counts: { overdue: 0 } })).toBe(true);
    expect(isTaskPage({ items: [], total: 0, limit: 50, offset: 0 })).toBe(false);
  });
});
