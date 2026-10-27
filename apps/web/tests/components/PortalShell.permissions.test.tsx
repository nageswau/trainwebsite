import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PortalShell from "@/components/PortalShell";
import { clearPermissions } from "@/lib/usePermissions";
import type { NavItem } from "@/lib/navigation";

// nehn-006 (DEC-SCOPE-295): the sidebar follows GET /auth/me/permissions -- a tagged item goes once its `view` grant is known to be
// missing; until then (or if the lookup fails) the nav is unchanged, and a nav without tagged items never asks.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/it/admin/dashboard",
  useSearchParams: () => new URLSearchParams(""),
}));

const NAV: NavItem[] = [
  { href: "/it/admin/dashboard", label: "Dashboard" },
  { href: "/it/admin/payments", label: "Payments", resource: "payments" },
  { href: "/it/admin/telecaller-reports", label: "Telecaller Reports", resource: "reports.telecaller" },
];

const permissionsResponse = (permissions: string[]) => new Response(JSON.stringify({ role: "it_admin", permissions }), { status: 200 });

async function renderShell(nav: NavItem[] = NAV) {
  return render(<PortalShell nav={nav} roleLabel="IT Administrator" userName="Ira"><p>page</p></PortalShell>);
}

const sidebar = () => screen.getAllByRole("navigation")[0];

beforeEach(() => clearPermissions()); // each test starts from an unknown set
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("nehn-006 PortalShell permission-driven nav", () => {
  it("drops an item whose view grant is missing once the set arrives", async () => {
    const fetchMock = vi.fn().mockResolvedValue(permissionsResponse(["reports.telecaller.view", "payments.add"]));
    vi.stubGlobal("fetch", fetchMock);
    await renderShell();
    await waitFor(() => expect(screen.queryByRole("link", { name: "Payments" })).not.toBeInTheDocument());
    expect(sidebar()).toHaveTextContent("Telecaller Reports");
    expect(sidebar()).toHaveTextContent("Dashboard");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/auth/me/permissions", expect.objectContaining({ cache: "no-store" }));
  });

  it("keeps every item while the lookup fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await renderShell();
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.getAllByRole("link", { name: "Payments" }).length).toBeGreaterThan(0);
  });

  it("keeps every item on a refused lookup", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 401 })));
    await renderShell();
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.getAllByRole("link", { name: "Payments" }).length).toBeGreaterThan(0);
  });

  it("does not ask when no item is tagged", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await renderShell([{ href: "/it/admin/dashboard", label: "Dashboard" }]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("also removes the item from the mobile menu", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(permissionsResponse([])));
    await renderShell();
    await waitFor(() => expect(screen.queryAllByText("Payments")).toHaveLength(0));
  });
});
