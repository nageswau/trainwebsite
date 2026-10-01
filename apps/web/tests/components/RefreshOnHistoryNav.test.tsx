import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RefreshOnHistoryNav from "@/components/RefreshOnHistoryNav";

const nav = vi.hoisted(() => ({ refresh: vi.fn(), pathname: "/overseas/agent/dashboard" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: nav.refresh }), usePathname: () => nav.pathname }));

const back = () => act(() => {
  window.dispatchEvent(new PopStateEvent("popstate"));
});
const runTimers = () => act(() => {
  vi.runAllTimers();
});

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  runTimers(); // consume anything a test left pending, so tests stay independent
  cleanup();
  nav.refresh.mockClear();
  nav.pathname = "/overseas/agent/dashboard";
  vi.useRealTimers();
});

// AGN-003 browser QA-07: Back/Forward replays the client router's cached page, so a page whose access was just revoked reappeared
// without asking the server. Browser re-checks (four rounds on the running stack) showed Next swaps the page BEFORE popstate is
// dispatched on a real Back: the leaving page's listener is already gone and the restored page's is not attached yet. So the Back
// listener lives at module level; the refresh runs once, from a 0 ms timer or the restored page's render, whichever comes first.
describe("RefreshOnHistoryNav (AGN-003 browser QA-07)", () => {
  it("re-asks the server after Back, not synchronously inside the event", () => {
    render(<RefreshOnHistoryNav />);
    back();
    expect(nav.refresh).not.toHaveBeenCalled();
    runTimers();
    expect(nav.refresh).toHaveBeenCalledTimes(1);
  });

  it("still re-asks when the leaving page unmounted before the event (Next restores first on a real Back)", () => {
    const { unmount } = render(<RefreshOnHistoryNav />);
    unmount(); // Next already swapped the page out
    back(); // no instance mounted while the event is dispatched
    nav.pathname = "/overseas/agent/reports";
    render(<RefreshOnHistoryNav />); // the cached page Next restored
    runTimers();
    expect(nav.refresh).toHaveBeenCalledTimes(1);
  });

  it("refreshes once when the restored page renders before the timer fires", () => {
    const { rerender } = render(<RefreshOnHistoryNav />);
    back();
    nav.pathname = "/overseas/agent/reports";
    rerender(<RefreshOnHistoryNav />);
    expect(nav.refresh).toHaveBeenCalledTimes(1);
    runTimers();
    expect(nav.refresh).toHaveBeenCalledTimes(1);
  });

  it("does not refresh on an ordinary link navigation", () => {
    const { rerender } = render(<RefreshOnHistoryNav />);
    nav.pathname = "/overseas/agent/reports";
    rerender(<RefreshOnHistoryNav />);
    runTimers();
    expect(nav.refresh).not.toHaveBeenCalled();
  });

  it("consumes the Back even when no instance is mounted, so a later link navigation does not refresh", () => {
    const { unmount } = render(<RefreshOnHistoryNav />);
    unmount();
    back();
    runTimers(); // the router is app-wide: the timer refreshes once even between pages
    expect(nav.refresh).toHaveBeenCalledTimes(1);
    nav.pathname = "/overseas/agent/reports";
    render(<RefreshOnHistoryNav />); // an ordinary navigation afterwards
    runTimers();
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
