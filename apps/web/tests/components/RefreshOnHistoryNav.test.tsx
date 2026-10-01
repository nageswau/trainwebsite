import { act, cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RefreshOnHistoryNav from "@/components/RefreshOnHistoryNav";

const nav = vi.hoisted(() => ({ refresh: vi.fn(), pathname: "/overseas/agent/dashboard" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: nav.refresh }), usePathname: () => nav.pathname }));

const back = () => act(() => {
  window.dispatchEvent(new PopStateEvent("popstate"));
});

afterEach(() => {
  cleanup();
  nav.refresh.mockClear();
  nav.pathname = "/overseas/agent/dashboard";
});

// AGN-003 browser QA-07: Back/Forward replays the client router's cached page, so a page whose access was just revoked reappeared
// without asking the server. Browser re-checks showed a refresh issued from the popstate event itself is lost (Next has not applied
// the restored page yet, and the leaving page unmounts mid-dispatch) -- so the refresh runs after the restored page renders.
describe("RefreshOnHistoryNav (AGN-003 browser QA-07)", () => {
  it("re-asks the server once the restored page has rendered (same component, new path)", () => {
    const { rerender } = render(<RefreshOnHistoryNav />);
    back();
    expect(nav.refresh).not.toHaveBeenCalled(); // not from inside the popstate event
    nav.pathname = "/overseas/agent/reports";
    rerender(<RefreshOnHistoryNav />);
    expect(nav.refresh).toHaveBeenCalledTimes(1);
  });

  it("re-asks the server when the restored page mounts a new instance", () => {
    const { unmount } = render(<RefreshOnHistoryNav />);
    back();
    unmount(); // the page being left
    nav.pathname = "/overseas/agent/reports";
    render(<RefreshOnHistoryNav />); // the cached page Next restored
    expect(nav.refresh).toHaveBeenCalledTimes(1);
  });

  it("still sees Back when an earlier popstate listener unmounts it synchronously (Next's own listener)", () => {
    let unmount: () => void = () => {};
    const nextRouter = () => unmount();
    window.addEventListener("popstate", nextRouter);
    try {
      ({ unmount } = render(<RefreshOnHistoryNav />));
      back();
      nav.pathname = "/overseas/agent/reports";
      render(<RefreshOnHistoryNav />);
      expect(nav.refresh).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener("popstate", nextRouter);
    }
  });

  it("does not refresh on an ordinary link navigation", () => {
    const { rerender } = render(<RefreshOnHistoryNav />);
    nav.pathname = "/overseas/agent/reports";
    rerender(<RefreshOnHistoryNav />);
    const { unmount } = render(<RefreshOnHistoryNav />);
    unmount();
    expect(nav.refresh).not.toHaveBeenCalled();
  });

  it("refreshes only once per Back", () => {
    const { rerender } = render(<RefreshOnHistoryNav />);
    back();
    nav.pathname = "/overseas/agent/reports";
    rerender(<RefreshOnHistoryNav />);
    render(<RefreshOnHistoryNav />);
    nav.pathname = "/overseas/agent/documents";
    rerender(<RefreshOnHistoryNav />);
    expect(nav.refresh).toHaveBeenCalledTimes(1);
  });

  it("also re-asks when the browser restores the page from its back/forward cache", () => {
    render(<RefreshOnHistoryNav />);
    act(() => {
      window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
    });
    expect(nav.refresh).toHaveBeenCalledTimes(1);
    act(() => {
      window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: false }));
    });
    expect(nav.refresh).toHaveBeenCalledTimes(1);
  });
});
