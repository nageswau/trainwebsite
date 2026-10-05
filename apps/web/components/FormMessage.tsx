"use client";

import { type CSSProperties, useEffect, useRef } from "react";

// ENH-022: a save's outcome, shown under the form it belongs to. A failure (e.g. a partnership-tier 403) is an alert so it is
// announced at once, and is scrolled into view (QA-022-04: on a phone it can land below the fold); a success stays a polite
// status where it is. Focus is not moved: the user stays on the control they used.
export type FormMessageState = { text: string; failed: boolean };

/** `style` is for spacing outside a grid card (e.g. under a table in a plain `.card`), as the panels already do inline. */
export default function FormMessage({ message, style }: { message: FormMessageState; style?: CSSProperties }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (message.failed) ref.current?.scrollIntoView?.({ block: "nearest" });
  }, [message]);
  return (
    <div ref={ref} className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} aria-live={message.failed ? "assertive" : "polite"} style={style}>
      {message.text}
    </div>
  );
}
