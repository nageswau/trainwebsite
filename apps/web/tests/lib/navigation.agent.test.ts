import { describe, expect, it } from "vitest";
import { agentNavFor, PORTAL_NAV } from "@/lib/navigation";

// AGN-004 G2/G3 (identical to AGN-002): an agency's staff lose Team and Commissions from the sidebar.
describe("agentNavFor", () => {
  const nav = PORTAL_NAV["overseas/agent"];

  // AGN-003 (DEC-SCOPE-044 P1, reconciled on merging `main`): Reports is also off for staff until their Master switches it on.
  it("hides Team and Commissions from staff", () => {
    expect(agentNavFor(nav, "staff", { can_verify_documents: false, can_view_reports: true }).map((i) => i.href)).toEqual([
      "/overseas/agent/dashboard",
      "/overseas/agent/students",
      "/overseas/agent/universities",
      "/overseas/agent/applications",
      "/overseas/agent/documents",
      "/overseas/agent/tasks",
      "/overseas/agent/notifications", // AGN-017 (DEC-SCOPE-059 N8): Masters and staff, after Tasks
      "/overseas/agent/reports",
    ]);
    expect(agentNavFor(nav, "staff").map((i) => i.href)).toEqual([
      "/overseas/agent/dashboard",
      "/overseas/agent/students",
      "/overseas/agent/universities",
      "/overseas/agent/applications",
      "/overseas/agent/documents",
      "/overseas/agent/tasks",
      "/overseas/agent/notifications",
    ]);
  });

  it("shows Tasks to both roles, after Documents (AGN-016, EVID-015 §4 sidebar order)", () => {
    const hrefs = nav.map((i) => i.href);
    expect(hrefs.indexOf("/overseas/agent/tasks")).toBe(hrefs.indexOf("/overseas/agent/documents") + 1);
    // AGN-018 (DEC-SCOPE-061 G4): the EVID-015 §4 wording.
    expect(nav.find((i) => i.href === "/overseas/agent/tasks")?.label).toBe("Tasks & Follow-ups");
    expect(agentNavFor(nav, "staff").map((i) => i.href)).toContain("/overseas/agent/tasks");
  });

  it("shows Universities to both roles (AGN-007)", () => {
    expect(nav.map((i) => i.href)).toContain("/overseas/agent/universities");
    expect(agentNavFor(nav, "staff").map((i) => i.href)).toContain("/overseas/agent/universities");
  });

  it("leaves a Master's nav unchanged", () => {
    expect(agentNavFor(nav, "master")).toEqual(nav);
    expect(agentNavFor(nav, null)).toEqual(nav);
    expect(agentNavFor(nav)).toEqual(nav);
  });

  it("gives Documents the Pending / Uploaded / Additional views for Masters and staff (AGN-009)", () => {
    const children = (items: ReturnType<typeof agentNavFor>) => items.find((i) => i.href === "/overseas/agent/documents")?.children?.map((c) => [c.label, c.href]);
    const expected = [
      ["Pending", "/overseas/agent/documents?view=pending"],
      ["Uploaded", "/overseas/agent/documents?view=uploaded"],
      ["Additional", "/overseas/agent/documents?view=additional"],
    ];
    expect(children(agentNavFor(nav, "master"))).toEqual(expected);
    expect(children(agentNavFor(nav, "staff"))).toEqual(expected);
  });

  it("gives Applications the status filters for Masters and staff (AGN-008)", () => {
    const children = (items: ReturnType<typeof agentNavFor>) => items.find((i) => i.href === "/overseas/agent/applications")?.children?.map((c) => c.href.split("=")[1] ?? "(bare)");
    // AGN-018 (DEC-SCOPE-061 G4): "All applications" first (EVID-015 §4 "All") -- the bare path, the list's default (QA18-07).
    const expected = ["(bare)", "draft", "submitted", "offer", "visa", "enrolled", "withdrawn"];
    expect(children(agentNavFor(nav, "master"))).toEqual(expected);
    expect(children(agentNavFor(nav, "staff"))).toEqual(expected);
    expect(nav.find((i) => i.href === "/overseas/agent/applications")?.children?.[0].label).toBe("All applications");
  });

  it("gives staff My Students with All and Add; a Master keeps Students (AGN-018 G4)", () => {
    const students = (items: ReturnType<typeof agentNavFor>) => items.find((i) => i.href === "/overseas/agent/students");
    expect(students(agentNavFor(nav, "staff"))?.label).toBe("My Students");
    expect(students(agentNavFor(nav, "staff"))?.children?.map((c) => [c.label, c.href])).toEqual([
      ["All", "/overseas/agent/students"],
      ["Add", "/overseas/agent/students?new=1"],
    ]);
    expect(students(agentNavFor(nav, "master"))).toEqual({ label: "Students", href: "/overseas/agent/students" });
  });
});
