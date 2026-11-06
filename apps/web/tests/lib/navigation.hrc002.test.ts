// @vitest-environment node
import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { dashboardPathFor, PORTAL_NAV } from "@/lib/navigation";
import { roleLabel } from "@/lib/managementDiscussions";
import { middleware } from "@/middleware";

// hrc-002 (DEC-SCOPE-374 R1/R3): the HR Manager, Placement Officer and Interviewer sign in at /it and land on their own dashboards.
const PORTALS = [
  ["hr_manager", "hr-manager", "HR Manager"],
  ["placement_officer", "placement-officer", "Placement Officer"],
  ["interviewer", "interviewer", "Interviewer"],
] as const;

describe("hrc-002 recruitment role navigation", () => {
  it.each(PORTALS)("lands %s on its own dashboard, whose portal holds only that page", (role, segment, label) => {
    expect(dashboardPathFor({ role, division: "it" })).toBe(`/it/${segment}/dashboard`);
    // hrc-007 (DEC-SCOPE-380 A9) gave the HR Manager its approval queue; hrc-006 (DEC-SCOPE-384 O12) the Placement Officer its requirements
    const EXTRA: Record<string, { label: string; href: string }[]> = {
      // hrc-035 (DEC-SCOPE-396 K7): and the candidate data requests
      "hr-manager": [{ label: "Approvals", href: "/it/hr-manager/approvals" }, { label: "Result approvals", href: "/it/hr-manager/results" } /* hrc-030 */, { label: "Delivery exceptions", href: "/recruiter/notification-exceptions" }, { label: "Notifications", href: "/recruiter/notifications" } /* hrc-032 */, { label: "Data requests", href: "/it/hr-manager/data-requests" }, { label: "Website registrations", href: "/recruiter/website-registrations" }], // hrc-025
      "placement-officer": [{ label: "Job requirements", href: "/recruiter/requirements" }, { label: "Notifications", href: "/recruiter/notifications" } /* hrc-032 */],
    };
    const extra = EXTRA[segment] ?? [];
    expect(PORTAL_NAV[`it/${segment}`]).toEqual([{ label: "Dashboard", href: `/it/${segment}/dashboard` }, ...extra]);
    expect(roleLabel(role)).toBe(label);
  });

  it.each(PORTALS)("protects the %s portal: a signed-out visit goes to the IT sign-in, keeping next", (_role, segment) => {
    const req = new NextRequest(`http://localhost/it/${segment}/dashboard`);
    expect(middleware(req).headers.get("location")).toBe(`http://localhost/it/login?next=%2Fit%2F${segment}%2Fdashboard`);
  });

  it("leaves look-alike paths unprotected", () => {
    expect(middleware(new NextRequest("http://localhost/it/hr-managers")).headers.get("location")).toBeNull();
  });
});
