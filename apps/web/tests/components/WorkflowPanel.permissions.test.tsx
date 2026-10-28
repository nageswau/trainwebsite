import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import WorkflowPanel from "@/components/WorkflowPanel";
import { clearPermissions } from "@/lib/usePermissions";
import type { User } from "@/lib/types";

// nehn-006 (DEC-SCOPE-295): the admin Payments page's forms follow the catalogue -- "Create payment due" needs `payments.add`,
// "Apply discount" `discounts.add`. Until the set is known (or if the lookup fails) both show; the API refuses either way.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams(), usePathname: () => "/it/admin/payments",
}));

const itAdmin = { id: "u1", email: "it_admin@example.local", full_name: "Ira", role: "it_admin", division: "it" } as unknown as User;
const granted = (permissions: string[]) => vi.fn(() => Promise.resolve(new Response(JSON.stringify({ role: "it_admin", permissions }), { status: 200 })));

function renderPanel(section = "payments") {
  render(<WorkflowPanel user={itAdmin} section={section} />);
}

beforeEach(() => clearPermissions()); // each test starts from an unknown set
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("nehn-006 WorkflowPanel payment forms follow the grants", () => {
  it("hides Apply discount without discounts.add", async () => {
    vi.stubGlobal("fetch", granted(["payments.view", "payments.add"]));
    renderPanel();
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Apply discount" })).toBeNull());
    expect(screen.getByRole("heading", { name: "Create payment due" })).toBeInTheDocument();
  });

  it("hides Create payment due without payments.add", async () => {
    vi.stubGlobal("fetch", granted(["payments.view", "discounts.add"]));
    renderPanel();
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Create payment due" })).toBeNull());
    expect(screen.getByRole("heading", { name: "Apply discount" })).toBeInTheDocument();
  });

  it("shows both while the lookup fails", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("offline"))));
    renderPanel();
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/auth/me/permissions", expect.anything()));
    expect(screen.getByRole("heading", { name: "Create payment due" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Apply discount" })).toBeInTheDocument();
  });

  // nehn-021 (DEC-SCOPE-309 D5): the finance roles get only Apply discount on their Payments page, still behind discounts.add.
  it.each(["accountant", "partner"])("offers the %s Apply discount with discounts.add, and nothing else", async (role) => {
    vi.stubGlobal("fetch", granted(["payments.view", "discounts.add", "payments.add"]));
    render(<WorkflowPanel user={{ ...itAdmin, role, division: "global" } as unknown as User} section="payments" />);
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/auth/me/permissions", expect.anything()));
    expect(screen.getByRole("heading", { name: "Apply discount" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Create payment due" })).toBeNull();
  });

  it("hides the accountant's Apply discount without discounts.add", async () => {
    vi.stubGlobal("fetch", granted(["payments.view"]));
    render(<WorkflowPanel user={{ ...itAdmin, role: "accountant", division: "global" } as unknown as User} section="payments" />);
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Apply discount" })).toBeNull());
  });

  it("does not ask on a page whose forms carry no permission", async () => {
    const fetchMock = granted([]);
    vi.stubGlobal("fetch", fetchMock);
    renderPanel("programs");
    expect(screen.getByRole("heading", { name: "Create program" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith("/api/v1/auth/me/permissions", expect.anything());
  });
});
