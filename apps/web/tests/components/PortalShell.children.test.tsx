import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PortalShell from "@/components/PortalShell";

let search = "status=offer";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/overseas/agent/applications",
  useSearchParams: () => new URLSearchParams(search),
}));

const nav = [
  { href: "/overseas/agent/dashboard", label: "Dashboard" },
  {
    href: "/overseas/agent/applications",
    label: "Applications",
    children: [
      { href: "/overseas/agent/applications?status=draft", label: "Draft" },
      { href: "/overseas/agent/applications?status=offer", label: "Offer received" },
    ],
  },
];

afterEach(cleanup);

describe("PortalShell sidebar filters (AGN-008)", () => {
  it("renders children under their parent and marks the active filter, not the parent", () => {
    search = "status=offer";
    const { container } = render(<PortalShell nav={nav} roleLabel="Agent" userName="A"><p>x</p></PortalShell>);
    const desktop = container.querySelector(".portal-nav") as HTMLElement;
    const group = within(desktop).getByRole("list", { name: "Applications filters" });
    expect(within(group).getByRole("link", { name: "Offer received" })).toHaveAttribute("aria-current", "page");
    expect(within(group).getByRole("link", { name: "Draft" })).not.toHaveAttribute("aria-current");
    expect(within(desktop).getByRole("link", { name: "Applications" })).not.toHaveAttribute("aria-current");
  });

  it("marks the parent when no filter is set", () => {
    search = "";
    const { container } = render(<PortalShell nav={nav} roleLabel="Agent" userName="A"><p>x</p></PortalShell>);
    const desktop = container.querySelector(".portal-nav") as HTMLElement;
    expect(within(desktop).getByRole("link", { name: "Applications" })).toHaveAttribute("aria-current", "page");
  });

  it("lists the filters in the mobile menu after their parent", () => {
    search = "";
    const { container } = render(<PortalShell nav={nav} roleLabel="Agent" userName="A"><p>x</p></PortalShell>);
    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const mobile = container.querySelector("#portal-mobile-nav-panel") as HTMLElement;
    const names = within(mobile).getAllByRole("link").map((a) => a.textContent);
    expect(names.slice(-3)).toEqual(["Applications", "Applications: Draft", "Applications: Offer received"]);
  });
  // QA8-08: the mobile menu marks the active filter child as current, not the parent; the parent only when no filter matches.
  it("marks the active filter, not the parent, in the mobile menu", () => {
    search = "status=offer";
    const { container } = render(<PortalShell nav={nav} roleLabel="Agent" userName="A"><p>x</p></PortalShell>);
    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const mobile = container.querySelector("#portal-mobile-nav-panel") as HTMLElement;
    expect(within(mobile).getByRole("link", { name: "Applications: Offer received" })).toHaveAttribute("aria-current", "page");
    expect(within(mobile).getByRole("link", { name: "Applications: Draft" })).not.toHaveAttribute("aria-current");
    expect(within(mobile).getByRole("link", { name: "Applications" })).not.toHaveAttribute("aria-current");
  });

  it("marks the parent in the mobile menu when no filter is set", () => {
    search = "";
    const { container } = render(<PortalShell nav={nav} roleLabel="Agent" userName="A"><p>x</p></PortalShell>);
    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const mobile = container.querySelector("#portal-mobile-nav-panel") as HTMLElement;
    expect(within(mobile).getByRole("link", { name: "Applications" })).toHaveAttribute("aria-current", "page");
    expect(within(mobile).getByRole("link", { name: "Applications: Offer received" })).not.toHaveAttribute("aria-current");
  });
});
