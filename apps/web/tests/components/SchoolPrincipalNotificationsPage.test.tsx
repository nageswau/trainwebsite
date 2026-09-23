import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolPrincipalNotificationsPage from "@/app/school/principal/notifications/page";
import Loading from "@/app/school/principal/notifications/loading";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";

// Async server component: `serverApi` reads next/headers cookies, so it is mocked (the real ApiError class is kept);
// the shell is stubbed because this test is about who sees what, not the chrome.
vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div data-testid="shell">{children}</div> }));

const user = (role: string) => ({ id: "u1", email: "u@example.local", full_name: "Test User", role, division: "school", profile: {} });
const notice = { id: "n1", title: "Your partnership changed from Platinum to Gold", body: "These services are no longer available for new work: Visa support.", read: false, action_url: "/school/principal/entitlements", created_at: "2026-09-23T10:00:00Z" };

function serve(role: string, notifications: unknown[]) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    if (path === "/api/v1/auth/me") return user(role);
    if (path === "/api/v1/workflows/notifications") return notifications;
    throw new Error(`unexpected request ${path}`);
  });
}

afterEach(() => {
  cleanup();
  vi.mocked(serverApi).mockReset();
});

describe("SchoolPrincipalNotificationsPage", () => {
  it("lists the principal's own notifications", async () => {
    serve("school_principal", [notice]);
    render(await SchoolPrincipalNotificationsPage());
    expect(screen.getByText("Your partnership changed from Platinum to Gold")).toBeTruthy();
  });

  it("explains the empty state", async () => {
    serve("school_principal", []);
    render(await SchoolPrincipalNotificationsPage());
    expect(screen.getByText("No notifications yet. You will be told here when your school's partnership changes.")).toBeTruthy();
  });

  it.each(["school_coordinator", "school_teacher", "school_parent"])("denies %s and never loads the feed", async (role) => {
    serve(role, [notice]);
    render(await SchoolPrincipalNotificationsPage());
    expect(screen.getByText("Access unavailable")).toBeTruthy();
    expect(screen.getByText("School Principal role required")).toBeTruthy();
    expect(vi.mocked(serverApi).mock.calls.map((c) => c[0])).not.toContain("/api/v1/workflows/notifications");
  });

  it("still shows Access unavailable when the feed cannot be loaded", async () => {
    vi.mocked(serverApi).mockRejectedValue(new Error("Not authenticated"));
    render(await SchoolPrincipalNotificationsPage());
    expect(screen.getByText("Access unavailable")).toBeTruthy();
  });

  it("is in the principal navigation", () => {
    expect(SCHOOL_NAV.principal.map((item) => item.href)).toContain("/school/principal/notifications");
  });
});

describe("SchoolPrincipalNotificationsPage loading state", () => {
  it("shows a labelled, busy skeleton instead of a blank screen", () => {
    render(<Loading />);
    const region = screen.getByLabelText("Loading notifications");
    expect(region).toHaveAttribute("aria-busy", "true");
  });
});
