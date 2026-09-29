"use client";

import { useEffect } from "react";

// ENH-016 QA-016-02: the reports forms are plain GET forms whose action ends in #development / #scorecards, but the browser's own
// jump to the fragment does not happen on these server-rendered portal pages, so the user was left at the top of a long page.
// Once mounted, bring the fragment's section into view. Renders nothing.
export default function ScrollToHash() {
  useEffect(() => {
    const id = decodeURIComponent(window.location.hash.slice(1));
    if (id) document.getElementById(id)?.scrollIntoView();
  }, []);
  return null;
}
