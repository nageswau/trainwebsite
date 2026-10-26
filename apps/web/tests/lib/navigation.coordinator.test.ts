// @vitest-environment node
import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { dashboardPathFor, PORTAL_NAV } from "@/lib/navigation";
import { middleware } from "@/middleware";

// nehn-030 (DEC-SCOPE-293): the IT coordinator signs in at /it and works in its own portal -- Dashboard and Certificates.
describe("nehn-030 coordinator navigation", () => {
  it("lands the coordinator on its own dashboard", () => {
    expect(dashboardPathFor({ role: "coordinator", division: "it" })).toBe("/it/coordinator/dashboard");
  });

  it("gives the coordinator Dashboard, Certificates and the shared Management tasks only", () => {
    expect(PORTAL_NAV["it/coordinator"]).toEqual([
      { label: "Dashboard", href: "/it/coordinator/dashboard" },
      { label: "Certificates", href: "/it/coordinator/certificates" },
      { label: "Management tasks", href: "/account/management-tasks" }, // mgmt-028 (MT14)
    ]);
  });

  it("protects /it/coordinator: a signed-out visit goes to the IT sign-in, keeping next", () => {
    const req = new NextRequest("http://localhost/it/coordinator/certificates");
    expect(middleware(req).headers.get("location")).toBe("http://localhost/it/login?next=%2Fit%2Fcoordinator%2Fcertificates");
  });
});
