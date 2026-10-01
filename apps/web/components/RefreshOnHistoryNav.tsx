"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

// AGN-003 browser QA-07: Back/Forward replays the client router's cached page, so a page whose access was just revoked (a staff
// member's Reports) reappeared without asking the server. After a history navigation -- or a restore from the browser's
// back/forward cache -- re-fetch the server components; the server then answers with today's permissions.
export default function RefreshOnHistoryNav() {
  const router = useRouter();
  useEffect(() => {
    // The page that hears Back is the one being left. Next's own popstate listener (registered earlier) swaps it out synchronously,
    // which removes ours mid-dispatch -- so ours listens in the capture phase (capture listeners on the target run first), and the
    // refresh it schedules runs after Next's restore and is deliberately NOT cancelled on unmount (the router is app-wide).
    const onPopState = () => {
      setTimeout(() => router.refresh(), 0);
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
  return null;
}
