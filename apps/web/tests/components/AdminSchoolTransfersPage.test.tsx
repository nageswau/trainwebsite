import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminSchoolTransfersPage from "@/app/overseas/admin/school-transfers/page";
import { serverApi } from "@/lib/api";

// ENH-005 browser QA N3: the admin's transfer screen used to be the portal's generic read-only table (raw UUIDs, ISO timestamps, capped at 200)
// with the real queue below the fold. It is now its own page: the queue first, no duplicate table. The page is an async server component and
// `serverApi` reads next/headers cookies, so it is mocked; the shell and the panel are stubbed because this test is about who sees the page
// and what surrounds the queue.
vi.mock("@/lib/api", () => ({ serverApi: vi.fn() }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div data-testid="shell">{children}</div> }));
vi.mock("@/components/AdminSchoolTransferPanel", () => ({ default: () => <div data-testid="panel">transfer queue</div> }));

const user = (role: string) => ({ id: "u1", email: "u@example.local", full_name: "Test User", role, division: "overseas", profile: {} });

function serve(role: string) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    if (path === "/api/v1/auth/me") return user(role) as never;
    throw new Error(`unexpected request ${path}`);
  });
}

afterEach(() => {
  cleanup();
  vi.mocked(serverApi).mockReset();
});

describe("AdminSchoolTransfersPage", () => {
  it.each(["overseas_admin", "super_admin"])("shows the queue to %s, under a title, with no generic table", async (role) => {
    serve(role);
    render(await AdminSchoolTransfersPage());
    expect(screen.getByRole("heading", { name: "School Transfers" })).toBeTruthy();
    expect(screen.getByTestId("panel")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText(/role-scoped records/)).toBeNull();
    const title = screen.getByRole("heading", { name: "School Transfers" });
    expect(title.compareDocumentPosition(screen.getByTestId("panel")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy(); // the queue comes straight after the title
  });

  it.each(["school_coordinator", "school_parent", "counselor", "it_admin"])("denies %s with a clear message and never renders the queue", async (role) => {
    serve(role);
    render(await AdminSchoolTransfersPage());
    expect(screen.getByText("Access unavailable")).toBeTruthy();
    expect(screen.getByText("Overseas Administrator role required")).toBeTruthy();
    expect(screen.queryByTestId("panel")).toBeNull();
  });

  it("still shows Access unavailable, with the reason, when the session cannot be read", async () => {
    vi.mocked(serverApi).mockRejectedValue(new Error("Not authenticated"));
    render(await AdminSchoolTransfersPage());
    expect(screen.getByText("Access unavailable")).toBeTruthy();
    expect(screen.getByText("Not authenticated")).toBeTruthy();
  });
});
