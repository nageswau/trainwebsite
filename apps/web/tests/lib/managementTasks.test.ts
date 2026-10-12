import { describe, expect, it } from "vitest";

import { managementNavFor } from "@/lib/management";
import { groupByBand, taskFilters, taskLine, tasksHref, tasksUrl } from "@/lib/managementTasks";
import {
  BDM_MANAGER_NAV, BDM_NAV, PARTNERSHIP_HEAD_NAV, PARTNERSHIP_NAV, PORTAL_NAV, RECRUITER_MANAGER_NAV, RECRUITER_NAV, SCHOOL_NAV, SUPER_ADMIN_NAV,
  TELECALLER_MANAGER_NAV, TELECALLER_NAV,
} from "@/lib/navigation";

const ALL = { operational: true, finance: true, partner_only: true };
const task = (id: string, band: string) => ({ id, band }) as never;

describe("mgmt-028 task helpers", () => {
  it("groups items into the §28 bands in source order and drops empty bands", () => {
    const groups = groupByBand([task("a", "completed"), task("b", "overdue"), task("c", "later"), task("d", "overdue")]);
    expect(groups.map((g) => [g.band, g.items.map((i: { id: string }) => i.id)])).toEqual([["overdue", ["b", "d"]], ["later", ["c"]], ["completed", ["a"]]]);
  });

  it("reads the view from the address, dropping anything malformed", () => {
    expect(taskFilters({})).toEqual({ view: "mine" });
    expect(taskFilters({ view: "everyone" })).toEqual({ view: "everyone" });
    expect(taskFilters({ view: "cancelled" })).toEqual({ view: "cancelled" });
    expect(taskFilters({ view: "secret" })).toEqual({ view: "mine" });
    expect(taskFilters({ view: ["everyone", "mine"] })).toEqual({ view: "mine" });
  });

  it("builds the page link and the API url for each view", () => {
    expect(tasksHref({ view: "mine" })).toBe("/management/tasks");
    expect(tasksHref({ view: "everyone" })).toBe("/management/tasks?view=everyone");
    expect(tasksUrl({ view: "mine" })).toBe("/api/v1/management/tasks?owner=me&limit=200");
    expect(tasksUrl({ view: "everyone" })).toBe("/api/v1/management/tasks?limit=200");
    expect(tasksUrl({ view: "cancelled" })).toBe("/api/v1/management/tasks?band=cancelled&limit=200");
  });

  it("writes the task line as title, deadline and priority", () => {
    expect(taskLine({ title: "Approve marketing budget", deadline: "2026-10-10", priority: "high" })).toBe("Approve marketing budget — 10 Oct 2026 — High priority");
  });
});

describe("mgmt-028 navigation (MT14)", () => {
  const MY_TASKS = "/account/management-tasks";
  const has = (nav: { href: string; label: string }[]) => nav.some((x) => x.href === MY_TASKS && x.label === "Management tasks");

  it("adds Management tasks to every staff portal's sidebar", () => {
    for (const nav of [BDM_NAV, BDM_MANAGER_NAV, TELECALLER_NAV, TELECALLER_MANAGER_NAV, RECRUITER_NAV, RECRUITER_MANAGER_NAV, PARTNERSHIP_NAV, PARTNERSHIP_HEAD_NAV, SUPER_ADMIN_NAV]) {
      expect(has(nav)).toBe(true);
    }
    for (const key of ["it/trainer", "it/placement", "it/hr", "it/counselor", "it/admin", "overseas/counselor", "overseas/admin"]) expect(has(PORTAL_NAV[key])).toBe(true);
    for (const key of ["academic-team", "career-counselor", "psychometric-team"]) expect(has(SCHOOL_NAV[key])).toBe(true);
  });

  it("keeps it out of student, parent, agent, university, employer and school-side portals", () => {
    for (const key of ["it/student", "overseas/student", "overseas/university", "overseas/agent"]) expect(has(PORTAL_NAV[key])).toBe(false);
    for (const key of ["coordinator", "principal", "teacher", "parent"]) expect(has(SCHOOL_NAV[key])).toBe(false);
  });

  it("makes the Command Center To-do live for the operational tier and gives the accountant their own list", () => {
    expect(managementNavFor(ALL)).toContainEqual({ label: "To-do", href: "/management/tasks" });
    const accountant = managementNavFor({ operational: false, finance: true, partner_only: false });
    expect(accountant).toContainEqual({ label: "Management tasks", href: MY_TASKS });
    expect(accountant.some((x) => x.href === "/management/tasks")).toBe(false);
  });
});
