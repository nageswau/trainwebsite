"use client";

import { useEffect } from "react";

// ENH-017 QA17-01: a route with loading.tsx streams its content, so the element a `#fragment` link targets is still hidden
// when the browser performs the fragment scroll and the page stays at the top. Once the element is on screen, scroll it into
// view if the URL targets it (scrollIntoView honours the element's scroll-margin-top). Renders nothing; without JS the
// links and forms still work, only this landing is lost.
export default function ScrollIntoViewOnHash({ id }: { id: string }) {
  useEffect(() => {
    if (window.location.hash === `#${id}`) document.getElementById(id)?.scrollIntoView({ block: "start" });
  }, [id]);
  return null;
}
