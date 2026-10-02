import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PortalShell from "@/components/PortalShell";
import type { NavItem } from "@/lib/navigation";

// AGN-017 (DEC-SCOPE-055 N8): the agency nav's Notifications item carries the unread count. The count is part of the link's name
// (visible text plus a visually hidden " unread"), never colour alone, and the mobile menu says it in words.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/overseas/agent/dashboard",
  useSearchParams: () => new URLSearchParams(""),
}));

afterEach(cleanup);

function renderShell(badge?: number) {
  const nav: NavItem[] = [
    { href: "/overseas/agent/dashboard", label: "Dashboard" },
    { href: "/overseas/agent/notifications", label: "Notifications", ...(badge === undefined ? {} : { badge }) },
  ];
  return render(
    <PortalShell nav={nav} roleLabel="Education Agent" userName="Asha">
      <p>page</p>
    </PortalShell>,
  );
}

const desktop = (container: HTMLElement) => container.querySelector(".portal-nav") as HTMLElement;

describe("PortalShell unread badge (AGN-017)", () => {
  it("puts the unread count in the Notifications link's accessible name", () => {
    const { container } = renderShell(3);
    const link = within(desktop(container)).getByRole("link", { name: "Notifications 3 unread" });
    expect(link.querySelector(".nav-badge")).toHaveTextContent("3 unread");
  });

  it("caps a large count at 99+", () => {
    const { container } = renderShell(120);
    expect(within(desktop(container)).getByRole("link", { name: "Notifications 99+ unread" })).toBeInTheDocument();
  });

  it("shows no badge at zero or without a count, and leaves other items alone", () => {
    for (const badge of [0, undefined]) {
      const { container } = renderShell(badge);
      expect(within(desktop(container)).getByRole("link", { name: "Notifications" })).toBeInTheDocument();
      expect(container.querySelector(".nav-badge")).toBeNull();
      cleanup();
    }
  });

  it("says the count in words in the mobile menu", () => {
    const { container } = renderShell(3);
    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const mobile = container.querySelector("#portal-mobile-nav-panel") as HTMLElement;
    expect(within(mobile).getByRole("link", { name: "Notifications (3 unread)" })).toHaveAttribute("href", "/overseas/agent/notifications");
    expect(within(mobile).getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
  });
});
