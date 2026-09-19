import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SuperAdmin from "@/app/admin/page";

vi.mock("@/lib/api", () => ({
  serverApi: vi.fn((path: string) =>
    Promise.resolve(path.endsWith("/auth/me") ? { id: "s1", full_name: "Super Admin", role: "super_admin", email: "s@example.local", division: "global" } : { users: 3, enquiries: 1, revenue: 0, universities: 2, expired_welcome_links: 2 }),
  ),
}));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// Codex finding 2: the requirement is "a count + list of expired-unused welcome links on the Super Admin, IT Admin and
// Overseas Admin dashboards". Super Admin only had the count tile.
describe("Super Admin dashboard (ENH-003)", () => {
  it("shows the expired-link count AND the list of accounts with a Re-send action", async () => {
    const rows = [{ id: "a1", name: "Asha Rao", email: "asha@example.local", role: "academic_team", division: "overseas", provisioning_status: "link_expired" }];
    const mock = vi.fn(() => Promise.resolve(new Response(JSON.stringify(rows), { status: 200 })));
    vi.stubGlobal("fetch", mock);
    render(await SuperAdmin());
    expect(screen.getByText("Expired welcome links")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /Expired set-password links/ })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Re-send set-password link to Asha Rao" })).toBeInTheDocument();
    await waitFor(() => expect(mock).toHaveBeenCalledWith("/api/v1/admin/users?provisioning_status=link_expired", expect.anything()));
  });
});
