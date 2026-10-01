import { act, cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RefreshOnHistoryNav from "@/components/RefreshOnHistoryNav";

const { refresh } = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

afterEach(() => {
  cleanup();
  refresh.mockClear();
  vi.useRealTimers();
});

describe("RefreshOnHistoryNav (AGN-003 browser QA-07)", () => {
  it("re-asks the server after Back/Forward, so a revoked page is not shown from the cache", () => {
    vi.useFakeTimers();
    render(<RefreshOnHistoryNav />);
    expect(refresh).not.toHaveBeenCalled();
    act(() => {
      window.dispatchEvent(new PopStateEvent("popstate"));
      vi.runAllTimers();
    });
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("also re-asks when the browser restores the page from its back/forward cache", () => {
    render(<RefreshOnHistoryNav />);
    act(() => {
      window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
    });
    expect(refresh).toHaveBeenCalledTimes(1);
    act(() => {
      window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: false }));
    });
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  // Browser re-check of QA-07: the page that hears Back is the one being left, and it unmounts while Next swaps in the cached
  // page -- the refresh it scheduled must still run.
  it("still refreshes when the page that heard Back unmounts before the refresh runs", () => {
    vi.useFakeTimers();
    const { unmount } = render(<RefreshOnHistoryNav />);
    act(() => {
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    unmount();
    act(() => {
      vi.runAllTimers();
    });
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("stops listening when unmounted", () => {
    vi.useFakeTimers();
    const { unmount } = render(<RefreshOnHistoryNav />);
    unmount();
    act(() => {
      window.dispatchEvent(new PopStateEvent("popstate"));
      vi.runAllTimers();
    });
    expect(refresh).not.toHaveBeenCalled();
  });
});
