"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

type Refreshable = { refresh: () => void };

// AGN-003 browser QA-07: Back/Forward replays the client router's cached page, so a page whose access was just revoked (a staff
// member's Reports) reappeared without asking the server. Four browser re-checks on the running stack showed why earlier versions
// failed: on a real Back, Next swaps the page BEFORE popstate is dispatched -- the leaving page's listener is already gone and the
// restored page's is not attached yet -- and a refresh issued synchronously inside the event is lost. So:
// - the Back listener lives at module level (registered once when this module loads, independent of any component's lifecycle);
// - the refresh runs from a 0 ms timer (measured to re-fetch reliably) or when the restored page renders, whichever comes first;
// - one Back means exactly one refresh. The router is app-wide, so the one an agent page recorded stays valid after that page
//   unmounts (which is exactly what happens before popstate on a real Back).
let historyNavPending = false;
let activeRouter: Refreshable | null = null;

function refreshOnce() {
  if (!historyNavPending || !activeRouter) return;
  historyNavPending = false;
  activeRouter.refresh();
}

if (typeof window !== "undefined") {
  window.addEventListener(
    "popstate",
    () => {
      historyNavPending = true;
      setTimeout(refreshOnce, 0);
    },
    true,
  );
}

export default function RefreshOnHistoryNav() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    activeRouter = router;
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) router.refresh();
    };
    window.addEventListener("pageshow", onPageShow);
    return () => {
      window.removeEventListener("pageshow", onPageShow);
    };
  }, [router]);

  // The restored page has rendered (a new instance's mount, or the same instance seeing the new path).
  useEffect(() => {
    refreshOnce();
  }, [pathname]);

  return null;
}
