"use client";

import { useEffect, useState } from "react";

import { formatDate, formatDateTimeIn, SCHOOL_TIME_ZONE } from "@/lib/formatDate";

// A timestamp shown in the viewer's own zone (outside the school portals). The server cannot know that zone, so the server render and the
// browser's first, hydrating render both use India time -- identical text, so React never reports hydration error #418 -- and the browser
// switches to the viewer's zone right after mount (no visible change for viewers in India). `label` adds the zone name to a time people
// act on (webinars, events, live classes, interviews). Calendar dates without a time of day use formatCalendarDate instead.
export default function LocalTime({ value, time = false, label = false }: { value: string | null | undefined; time?: boolean; label?: boolean }) {
  const [zone, setZone] = useState(SCHOOL_TIME_ZONE);
  useEffect(() => setZone(Intl.DateTimeFormat().resolvedOptions().timeZone), []);
  if (!value) return <>-</>;
  return <time dateTime={value}>{time ? formatDateTimeIn(value, zone, label) : formatDate(value, false, zone)}</time>;
}
