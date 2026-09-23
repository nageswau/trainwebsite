"use client";

import { useSyncExternalStore } from "react";

import { formatDate } from "@/lib/formatDate";

// ENH-018: a date/time in the VIEWER's timezone, safe inside a server-rendered client component. `formatDate` uses the runtime's
// local timezone, and the server (UTC in the container) and the browser differ, so rendering it during SSR made hydration fail
// (React #418). The server snapshot is a neutral placeholder; the browser's snapshot is the viewer's local time. The <time>
// element always carries the exact instant for assistive tech and copy/paste.
const noSubscription = () => () => {};

export default function LocalDateTime({ value, withTime = false }: { value: string; withTime?: boolean }) {
  const inBrowser = useSyncExternalStore(noSubscription, () => true, () => false);
  return <time dateTime={value}>{inBrowser ? formatDate(value, withTime) : "…"}</time>;
}
