import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminPermissionsPage from "@/app/admin/permissions/page";
import { ApiError, serverApi } from "@/lib/api";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

// nehn-006 (DEC-SCOPE-295 AC5): /admin/permissions is the Super Admin's; anyone else gets the access card, never the matrix.
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock("@/components/PermissionMatrix", () => ({ default: ({ catalogue }: { catalogue: { roles: string[] } }) => <p>matrix of {catalogue.roles.length} roles</p> }));
vi.mock("@/components/UserPermissionOverrides", () => ({ default: ({ userId }: { userId: string | null }) => <p>overrides for {userId ?? "nobody"}</p> }));

const CATALOGUE = { roles: ["super_admin", "it_admin"], actions: ["view"], resources: [] };
const page = (params: Record<string, string> = {}) => ({ searchParams: Promise.resolve(params) });
const person = (role: string) => ({ id: "u1", full_name: "Sam", role, email: "s@example.local", division: role === "it_admin" ? "it" : "global" });

function api(role: string, catalogue: () => Promise<unknown> = () => Promise.resolve(CATALOGUE)) {
  vi.mocked(serverApi).mockImplementation(((path: string) => (path.endsWith("/auth/me") ? Promise.resolve(person(role)) : catalogue())) as typeof serverApi);
}

afterEach(() => {
  cleanup();
  vi.mocked(serverApi).mockReset();
});

describe("nehn-006 /admin/permissions", () => {
  it("is linked from the Super Admin's sidebar after Roles", () => {
    const hrefs = SUPER_ADMIN_NAV.map((item) => item.href);
    expect(hrefs.indexOf("/admin/permissions")).toBe(hrefs.indexOf("/admin/roles") + 1);
  });

  it("shows the Super Admin the matrix", async () => {
    api("super_admin");
    render(await AdminPermissionsPage(page()));
    expect(screen.getByRole("heading", { name: "Permissions" })).toBeInTheDocument();
    expect(screen.getByText("matrix of 2 roles")).toBeInTheDocument();
    expect(serverApi).toHaveBeenCalledWith("/api/v1/admin/permissions/catalogue");
  });

  it("refuses any other role without reading the catalogue", async () => {
    api("it_admin");
    render(await AdminPermissionsPage(page()));
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeInTheDocument();
    expect(screen.getByText("Only a super admin can manage permissions")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to your dashboard" })).toHaveAttribute("href", "/it/admin/dashboard");
    expect(serverApi).not.toHaveBeenCalledWith("/api/v1/admin/permissions/catalogue");
    expect(screen.queryByText(/matrix of/)).toBeNull();
  });

  it("shows the access card when the catalogue read fails", async () => {
    api("super_admin", () => Promise.reject(new ApiError("Only a super admin can manage permissions", 403)));
    render(await AdminPermissionsPage(page()));
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeInTheDocument();
  });

  // nehn-007 (DEC-SCOPE-297): a "By user" tab beside the role matrix; the tab and the picked user live in the URL.
  it("offers the By role and By user tabs, By role current by default", async () => {
    api("super_admin");
    render(await AdminPermissionsPage(page()));
    expect(screen.getByRole("link", { name: "By role" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "By user" })).toHaveAttribute("href", "/admin/permissions?tab=user");
    expect(screen.queryByText(/overrides for/)).toBeNull();
  });

  it("shows the user tab with the picked user", async () => {
    api("super_admin");
    render(await AdminPermissionsPage(page({ tab: "user", user: "abc" })));
    expect(screen.getByRole("link", { name: "By user" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("overrides for abc")).toBeInTheDocument();
    expect(screen.queryByText(/matrix of/)).toBeNull();
  });
});
