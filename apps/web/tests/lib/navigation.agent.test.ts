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
      "/overseas/agent/notifications", // AGN-017 (DEC-SCOPE-055 N8): Masters and staff, after Tasks
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
    expect(nav.find((i) => i.href === "/overseas/agent/tasks")?.label).toBe("Tasks");
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
    const children = (items: ReturnType<typeof agentNavFor>) => items.find((i) => i.href === "/overseas/agent/applications")?.children?.map((c) => c.href.split("=")[1]);
    const expected = ["draft", "submitted", "offer", "visa", "enrolled", "withdrawn"];
    expect(children(agentNavFor(nav, "master"))).toEqual(expected);
    expect(children(agentNavFor(nav, "staff"))).toEqual(expected);
  });
});
