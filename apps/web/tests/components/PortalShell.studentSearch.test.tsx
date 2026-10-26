import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PortalShell from "@/components/PortalShell";
import { PORTAL_NAV, SUPER_ADMIN_NAV, type NavItem } from "@/lib/navigation";

// nehn-041 (DEC-SCOPE-291 S10): every page of a portal whose nav has "Student search" carries a header search box that opens it.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/admin/users",
  useSearchParams: () => new URLSearchParams(""),
}));

afterEach(cleanup);

const shell = (nav: NavItem[]) => render(<PortalShell nav={nav} roleLabel="Admin" userName="Asha"><p>page</p></PortalShell>);

describe("PortalShell header student search (nehn-041)", () => {
  it.each([
    ["Super Admin", SUPER_ADMIN_NAV, "/admin/student-search"],
    ["IT Admin", PORTAL_NAV["it/admin"], "/it/admin/student-search"],
    ["Overseas Admin", PORTAL_NAV["overseas/admin"], "/overseas/admin/student-search"],
  ])("the %s nav lists Student search and the top bar searches it", (_, nav, href) => {
    expect(nav.some((item) => item.href === href && item.label === "Student search")).toBe(true);
    shell(nav);
    const form = screen.getByRole("search", { name: "Search students" });
    expect(form.getAttribute("method")).toBe("get");
    expect(form.getAttribute("action")).toBe(href);
    expect(screen.getByRole("searchbox", { name: "Search students" }).getAttribute("name")).toBe("q");
  });

  it("is absent from portals without the page", () => {
    shell(PORTAL_NAV["overseas/counselor"]);
    expect(screen.queryByRole("search")).toBeNull();
  });
});
