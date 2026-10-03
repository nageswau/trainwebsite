import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PortalShell from "@/components/PortalShell";
import { agentNavFor, PORTAL_NAV } from "@/lib/navigation";

// AGN-018 browser QA18-02 / QA18-07: the real staff nav, whose "All" children repeat their parent's path. Exactly one link is the
// current page -- in the sidebar and in the mobile menu -- and it is the most specific match.
let pathname = "/overseas/agent/students";
let search = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams(search),
}));
afterEach(cleanup);

const nav = agentNavFor(PORTAL_NAV["overseas/agent"], "staff");

function at(path: string) {
  [pathname, search] = path.split("?") as [string, string?] as [string, string];
  search = search ?? "";
  const view = render(<PortalShell nav={nav} roleLabel="Agency Staff" userName="S"><p>x</p></PortalShell>);
  const desktop = view.container.querySelector(".portal-nav") as HTMLElement;
  fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
  const mobile = view.container.querySelector("#portal-mobile-nav-panel") as HTMLElement;
  const current = (root: HTMLElement) => [...root.querySelectorAll('a[aria-current="page"]')].map((a) => a.textContent);
  return { desktop: current(desktop), mobile: current(mobile), mobileHrefs: [...mobile.querySelectorAll("a")].map((a) => a.getAttribute("href")) };
}

describe("PortalShell with the staff nav's All children (AGN-018)", () => {
  it("marks one current link on My Students, in the sidebar and the mobile menu (QA18-02)", () => {
    const { desktop, mobile, mobileHrefs } = at("/overseas/agent/students");
    expect(desktop).toEqual(["All"]);
    expect(mobile).toHaveLength(1);
    expect(new Set(mobileHrefs).size).toBe(mobileHrefs.length); // no href twice (React keys them by href)
  });

  it("marks All applications on the bare Applications path, and a filter over All (QA18-07)", () => {
    expect(at("/overseas/agent/applications").desktop).toEqual(["All applications"]);
    cleanup();
    expect(at("/overseas/agent/applications?status=draft").desktop).toEqual(["Draft"]);
    cleanup();
    expect(at("/overseas/agent/applications?status=draft").mobile).toEqual(["Applications: Draft"]);
  });

  it("marks Add while ?new=1 is in the URL (QA18-07)", () => {
    expect(at("/overseas/agent/students?new=1").desktop).toEqual(["Add"]);
  });
});
