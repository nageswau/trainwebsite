import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminSchoolAnalyticsPage from "@/app/overseas/admin/school-analytics/page";
import { serverApi } from "@/lib/api";
import { PORTAL_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";

// ENH-016 browser QA: QA-016-07 (offset clamp), QA-016-08 (a Super Admin keeps their own navigation), QA-016-09 (search reaches the API).
// Same shape as AdminSchoolTransfersPage.test.tsx: serverApi is mocked (it reads next/headers cookies) and the shell records its nav.
vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
const shellNav = vi.hoisted(() => ({ current: [] as { href: string }[] }));
vi.mock("@/components/PortalShell", () => ({
  default: ({ nav, children }: { nav: { href: string }[]; children: React.ReactNode }) => {
    shellNav.current = nav;
    return <div data-testid="shell">{children}</div>;
  },
}));
vi.mock("@/components/CrossSchoolAnalytics", () => ({ default: ({ q }: { q?: string }) => <div data-testid="analytics">q={q}</div> }));

const calls: string[] = [];
function serve(role: string) {
  calls.length = 0;
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    calls.push(path);
    if (path === "/api/v1/auth/me") return { id: "u1", email: "u@example.local", full_name: "Admin", role, division: "overseas", profile: {} } as never;
    return null as never;
  });
}

afterEach(() => {
  cleanup();
  vi.mocked(serverApi).mockReset();
});

describe("AdminSchoolAnalyticsPage", () => {
  it("keeps the Super Admin's own navigation", async () => {
    serve("super_admin");
    render(await AdminSchoolAnalyticsPage({ searchParams: Promise.resolve({}) }));
    expect(shellNav.current).toBe(SUPER_ADMIN_NAV);
    expect(shellNav.current.some((i) => i.href === "/admin")).toBe(true);
  });

  it("shows the Overseas Admin navigation to an Overseas Admin", async () => {
    serve("overseas_admin");
    render(await AdminSchoolAnalyticsPage({ searchParams: Promise.resolve({}) }));
    expect(shellNav.current).toBe(PORTAL_NAV["overseas/admin"]);
  });

  it("clamps a huge offset and passes the search to the API and the table", async () => {
    serve("overseas_admin");
    render(await AdminSchoolAnalyticsPage({ searchParams: Promise.resolve({ offset: "99999", q: "  alpha " }) }));
    expect(calls).toContain("/api/v1/overseas-admin/analytics/schools?offset=10000&q=alpha");
    expect(screen.getByTestId("analytics")).toHaveTextContent("q=alpha");
  });
});
