// @vitest-environment node
import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { safeNextPath } from "@/lib/safeNext";
import { middleware } from "@/middleware";

// AGN-008 QA8-07: a signed-out user keeps the filter they asked for, and `next` can never leave the site.
describe("login next (QA8-07)", () => {
  it("keeps the query string in the login redirect", () => {
    const response = middleware(new NextRequest("http://localhost:3000/overseas/agent/applications?status=enrolled"));
    const location = new URL(response.headers.get("location")!);
    expect(location.pathname).toBe("/overseas/login");
    expect(location.searchParams.get("next")).toBe("/overseas/agent/applications?status=enrolled");
  });

  it("still redirects a path without a query, and the admin console", () => {
    const plain = new URL(middleware(new NextRequest("http://localhost:3000/it/student/dashboard")).headers.get("location")!);
    expect(plain.pathname).toBe("/it/login");
    expect(plain.searchParams.get("next")).toBe("/it/student/dashboard");
    const admin = new URL(middleware(new NextRequest("http://localhost:3000/admin/users?page=2")).headers.get("location")!);
    expect(admin.pathname).toBe("/admin/login");
    expect(admin.searchParams.get("next")).toBe("/admin/users?page=2");
  });

  it("accepts a same-origin relative path with its query", () => {
    expect(safeNextPath("/overseas/agent/applications?status=enrolled")).toBe("/overseas/agent/applications?status=enrolled");
    expect(safeNextPath("/it/student/dashboard")).toBe("/it/student/dashboard");
  });

  it.each([
    "//evil.com",
    "//evil.com/overseas/agent/applications",
    "/\\evil.com",
    "\\\\evil.com",
    "https://evil.com",
    "http://localhost:3000/overseas/agent/dashboard",
    "javascript:alert(1)",
    "evil.com",
    "/\t/evil.com",
    // Fix round 1: dot-segment removal must not turn these into "//evil.com".
    "/.//evil.com",
    "/x/..//evil.com",
    "/..//evil.com",
    "/%2e//evil.com",
    "/%2E%2E//evil.com",
    "",
    null,
  ])("rejects %s", (value) => {
    expect(safeNextPath(value)).toBeNull();
  });
});
