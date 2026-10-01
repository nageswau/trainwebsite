"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

// Shared by the page being left (which hears Back) and the cached page Next restores (which renders it).
let historyNavPending = false;

// AGN-003 browser QA-07: Back/Forward replays the client router's cached page, so a page whose access was just revoked (a staff
// member's Reports) reappeared without asking the server. Browser re-checks showed a refresh issued from the popstate event itself
// is lost: Next's own popstate listener runs first and unmounts the leaving page mid-dispatch, and Next has not applied the
// restored page yet. So the event only marks the navigation (capture phase, ahead of Next's listener), and the refresh runs from an
// effect once the restored page has rendered -- the server then answers with today's permissions.
export default function RefreshOnHistoryNav() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const onPopState = () => {
      historyNavPending = true;
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

  // Runs after the restored page is committed: on a new instance's mount, or when the same instance sees the new path.
  useEffect(() => {
    if (!historyNavPending) return;
    historyNavPending = false;
    router.refresh();
  }, [pathname, router]);

  return null;
}
