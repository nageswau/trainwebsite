import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolCoordinatorPromotionPage from "@/app/school/coordinator/promotion/page";
import { serverApi } from "@/lib/api";

// The page is an async server component: `serverApi` reads next/headers cookies, so it is mocked; the shell and the
// panel are stubbed because this test is only about who is allowed to see the page.
vi.mock("@/lib/api", () => ({ serverApi: vi.fn() }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div data-testid="shell">{children}</div> }));
vi.mock("@/components/SchoolPromotionPanel", () => ({ default: () => <div data-testid="panel">promotion panel</div> }));

const user = (role: string) => ({ id: "u1", email: "u@example.local", full_name: "Test User", role, division: "school", profile: {} });

function serve(role: string) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    if (path === "/api/v1/auth/me") return user(role);
    if (path === "/api/v1/school/students") return [];
    if (path === "/api/v1/school/academic-years/active") return { id: "y1", label: "2027-28" };
    throw new Error(`unexpected request ${path}`);
  });
}

afterEach(() => {
  cleanup();
  vi.mocked(serverApi).mockReset();
});

describe("SchoolCoordinatorPromotionPage access", () => {
  it("shows the promotion panel to a School Coordinator", async () => {
    serve("school_coordinator");
    render(await SchoolCoordinatorPromotionPage());
    expect(screen.getByTestId("panel")).toBeTruthy();
  });

  it.each(["school_parent", "school_teacher", "school_principal"])("denies %s with a clear message and never loads the roster", async (role) => {
    serve(role);
    render(await SchoolCoordinatorPromotionPage());
    expect(screen.getByText("Access unavailable")).toBeTruthy();
    expect(screen.getByText("School Coordinator role required")).toBeTruthy();
    expect(screen.queryByTestId("panel")).toBeNull();
    const paths = vi.mocked(serverApi).mock.calls.map((c) => c[0]);
    expect(paths).not.toContain("/api/v1/school/students");
  });

  it("still shows Access unavailable when the workspace cannot be loaded", async () => {
    vi.mocked(serverApi).mockRejectedValue(new Error("Not authenticated"));
    render(await SchoolCoordinatorPromotionPage());
    expect(screen.getByText("Access unavailable")).toBeTruthy();
    expect(screen.getByText("Not authenticated")).toBeTruthy();
  });
});
