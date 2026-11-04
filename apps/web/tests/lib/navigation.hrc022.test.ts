// @vitest-environment node
import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { dashboardPathFor } from "@/lib/navigation";
import { middleware } from "@/middleware";

// hrc-022 (DEC-SCOPE-384): an external candidate lands on their own portal; it is protected, the rest of /it/careers stays public.
describe("hrc-022 candidate portal navigation", () => {
  it("lands a candidate on their profile", () => {
    expect(dashboardPathFor({ role: "candidate", division: "it" })).toBe("/it/careers/portal/profile");
  });

  it.each(["/it/careers/portal/profile", "/it/careers/portal/privacy", "/it/careers/portal"])("sends a signed-out visit to %s to the IT sign-in", (path) => {
    expect(middleware(new NextRequest(`http://localhost${path}`)).headers.get("location")).toBe(`http://localhost/it/login?next=${encodeURIComponent(path)}`);
  });

  it.each(["/it/careers", "/it/careers/register", "/it/careers/verify-email", "/it/careers/portalx"])("leaves %s public", (path) => {
    expect(middleware(new NextRequest(`http://localhost${path}`)).headers.get("location")).toBeNull();
  });
});
