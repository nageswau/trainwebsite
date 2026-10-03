import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import MobileNavToggle from "@/components/MobileNavToggle";

// AGN-018 final review: the staff "My Students" item has an "All" child with the parent's own href. The mobile menu must mark one
// link as the current page -- the child, as the desktop NavGroup does -- not both.
vi.mock("next/navigation", () => ({ usePathname: () => "/overseas/agent/students" }));
afterEach(cleanup);

const nav = [
  { href: "/overseas/agent/dashboard", label: "Dashboard" },
  {
    href: "/overseas/agent/students",
    label: "My Students",
    children: [
      { href: "/overseas/agent/students", label: "All" },
      { href: "/overseas/agent/students?new=1", label: "Add" },
    ],
  },
];

describe("MobileNavToggle with a child that repeats its parent's href (AGN-018)", () => {
  it("marks only the child as the current page", () => {
    const { container } = render(<MobileNavToggle nav={nav} buttonClassName="b" panelClassName="p" panelId="m" />);
    const current = [...container.querySelectorAll('[aria-current="page"]')].map((a) => a.textContent);
    expect(current).toEqual(["All"]);
  });
});
