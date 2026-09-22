import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PortalShell from "@/components/PortalShell";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/it/student/dashboard",
}));

const nav = [
  { href: "/it/student/dashboard", label: "Dashboard" },
  { href: "/it/student/courses", label: "My courses" },
];

function renderShell() {
  return render(
    <PortalShell nav={nav} roleLabel="IT Student" userName="Asha">
      <p>page content</p>
    </PortalShell>,
  );
}

afterEach(cleanup);

describe("PortalShell change-password entry point (ENH-006)", () => {
  it("offers Change password in the desktop sidebar footer beside Sign out", () => {
    const { container } = renderShell();
    const footer = container.querySelector(".sidebar-footer") as HTMLElement;
    expect(within(footer).getByRole("link", { name: "Change password" })).toHaveAttribute("href", "/account/password");
    expect(within(footer).getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  // QA-004: last of 17 items on a phone meant scrolling the menu to find it; first means it is always in view.
  it("puts it first in the mobile menu, ahead of the role's own items, and leaves the desktop nav untouched", () => {
    const { container } = renderShell();
    const desktop = container.querySelector(".portal-nav") as HTMLElement;
    expect(within(desktop).getAllByRole("link").map((link) => link.textContent)).toEqual(["Dashboard", "My courses"]);
    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const mobile = container.querySelector("#portal-mobile-nav-panel") as HTMLElement;
    expect(within(mobile).getAllByRole("link").map((link) => link.textContent)).toEqual(["Change password", "My profile", "Dashboard", "My courses"]);
  });

  it("still renders the page content", () => {
    renderShell();
    expect(screen.getByText("page content")).toBeInTheDocument();
  });
});

describe("PortalShell my-profile entry point (ENH-007)", () => {
  it("offers My profile in the desktop sidebar footer, right after Change password", () => {
    const { container } = renderShell();
    const footer = container.querySelector(".sidebar-footer") as HTMLElement;
    const links = within(footer).getAllByRole("link").map((link) => link.textContent);
    expect(links).toEqual(["Change password", "My profile"]);
    expect(within(footer).getByRole("link", { name: "My profile" })).toHaveAttribute("href", "/account/profile");
  });

  // Mirrors the QA-004 lesson this file already tests for "Change password": a shared link must stay
  // front-loaded in the mobile menu, not appended after the role's own (much longer) nav array.
  it("keeps My profile front-loaded in the mobile menu too, not buried after the role's items", () => {
    const { container } = renderShell();
    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const mobile = container.querySelector("#portal-mobile-nav-panel") as HTMLElement;
    expect(within(mobile).getAllByRole("link").map((link) => link.textContent)).toEqual(["Change password", "My profile", "Dashboard", "My courses"]);
  });
});
