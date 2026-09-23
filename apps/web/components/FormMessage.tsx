import type { CSSProperties } from "react";

// ENH-022: a save's outcome, shown under the form it belongs to. A failure (e.g. a partnership-tier 403) is an alert so it is
// announced at once; a success stays a polite status. Focus is not moved: the user stays on the control they used.
export type FormMessageState = { text: string; failed: boolean };

/** `style` is for spacing outside a grid card (e.g. under a table in a plain `.card`), as the panels already do inline. */
export default function FormMessage({ message, style }: { message: FormMessageState; style?: CSSProperties }) {
  return (
    <div className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} aria-live={message.failed ? "assertive" : "polite"} style={style}>
      {message.text}
    </div>
  );
}
