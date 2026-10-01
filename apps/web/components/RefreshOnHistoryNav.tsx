"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

// Shared by the page being left (which hears Back) and the cached page Next restores (which renders it).
let historyNavPending = false;

// AGN-003 browser QA-07: Back/Forward replays the client router's cached page, so a page whose access was just revoked (a staff
// member's Reports) reappeared without asking the server. The fix is a router.refresh() once Next has restored the page:
// - the capture-phase listener runs ahead of Next's own popstate listener (which unmounts the leaving page mid-dispatch);
// - it never refreshes synchronously inside the event (Next has not applied the restored page yet), but from a 0 ms timer -- measured
//   on the running stack to re-fetch reliably -- and, as a second path, from an effect once the restored page renders.
// Whichever path runs first consumes the flag, so one Back means exactly one refresh.
export default function RefreshOnHistoryNav() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const refreshOnce = () => {
      if (!historyNavPending) return;
      historyNavPending = false;
      router.refresh();
    };
    const onPopState = () => {
      historyNavPending = true;
      setTimeout(refreshOnce, 0); // deliberately not cancelled on unmount: the router is app-wide
    };
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) router.refresh();
    };
    window.addEventListener("popstate", onPopState, true);
    window.addEventListener("pageshow", onPageShow);
    return () => {
      window.removeEventListener("popstate", onPopState, true);
      window.removeEventListener("pageshow", onPageShow);
    };
  }, [router]);

  // Second path: after the restored page is committed (a new instance's mount, or the same instance seeing the new path).
  useEffect(() => {
    if (!historyNavPending) return;
    historyNavPending = false;
    router.refresh();
  }, [pathname, router]);

  return null;
}
