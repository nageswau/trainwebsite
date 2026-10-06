import { describe, expect, it } from "vitest";

import { daysOverdue, isTask, isTaskPage, orgTasksUrl, orgTypeText, taskRuleField, tasksUrl } from "@/lib/bdmTasks";

describe("bdmTasks (bdm-008 §6, §9)", () => {
  it("builds list URLs with only the filters that are set", () => {
    expect(tasksUrl({ bucket: "today" })).toBe("/api/v1/bdm/tasks?bucket=today&limit=50&offset=0");
    expect(tasksUrl({ bucket: "overdue", kind: "task", orgType: "none", bdm: "b1", offset: 50 })).toBe(
      "/api/v1/bdm/tasks?bucket=overdue&limit=50&offset=50&kind=task&org_type=none&bdm_user_id=b1");
    expect(orgTasksUrl("o1")).toBe("/api/v1/bdm/tasks?bucket=open&limit=50&offset=0&organization_id=o1");
  });

  it("guards response shapes", () => {
    expect(isTask({ id: "t", title: "x", due_on: "2030-01-01", permissions: {} })).toBe(true);
    expect(isTask({ id: "t" })).toBe(false);
    expect(isTaskPage({ items: [], total: 0, limit: 50, offset: 0, today: "2030-01-01", counts: { buckets: {}, by_org_type: [] } })).toBe(true);
    expect(isTaskPage({ items: [], total: 0, limit: 50, offset: 0 })).toBe(false);
  });

  it("words types, rules and overdue days", () => {
    expect(orgTypeText("training_institute")).toBe("Training Institute");
    expect(orgTypeText(null)).toBe("No organization");
    expect(taskRuleField("Due date can't be in the past")).toEqual({ due_on: "Due date can't be in the past" });
    expect(taskRuleField("This organization is archived — restore it before adding tasks")).toEqual({ organization_id: "This organization is archived — restore it before adding tasks" });
    expect(taskRuleField("boom")).toEqual({});
    expect(daysOverdue("2026-09-20", "2026-09-23")).toBe(3);
  });
});
