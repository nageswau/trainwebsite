import { cleanup, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";

import LocalDateTime from "@/components/LocalDateTime";
import { formatDate } from "@/lib/formatDate";

// ENH-018 (browser QA: React #418). A client component that is server-rendered must not put local-time text in its HTML: the
// server's timezone (UTC in the container) and the viewer's differ, so hydration would see different text. The server render is a
// neutral placeholder; the viewer's own local time appears once hydrated.
const ISO = "2026-09-20T21:30:00Z";

afterEach(cleanup);

describe("LocalDateTime", () => {
  it("server-renders no local-time text, only a machine-readable <time>", () => {
    const html = renderToString(<LocalDateTime value={ISO} withTime />);
    expect(html).toContain(`dateTime="${ISO}"`);
    expect(html).not.toContain(formatDate(ISO, true));
    expect(html).toMatch(/<time[^>]*>…<\/time>/); // the visible text is only the placeholder
  });

  it("shows the viewer's local date and time in the browser", () => {
    render(<LocalDateTime value={ISO} withTime />);
    expect(screen.getByText(formatDate(ISO, true))).toHaveAttribute("datetime", ISO);
  });

  it("date only when asked", () => {
    render(<LocalDateTime value={ISO} />);
    expect(screen.getByText(formatDate(ISO))).toBeTruthy();
  });
});
