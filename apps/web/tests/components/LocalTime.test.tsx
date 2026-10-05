import { cleanup, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import LocalTime from "@/components/LocalTime";

// Date sweep: outside the school portals a time follows the viewer's zone. The server cannot know that zone, so the server render and
// the browser's first (hydrating) render both use India time -- identical text, so React never reports #418 -- and the browser then
// switches to the viewer's own zone after mount. 20:00Z on 21 Sept is 01:30 on the 22nd in India.
const AT = "2026-09-21T20:00:00Z";
let savedTz: string | undefined;
beforeEach(() => {
  savedTz = process.env.TZ;
});
afterEach(() => {
  cleanup();
  process.env.TZ = savedTz;
});

describe("LocalTime", () => {
  it("server-renders India time whatever zone the server runs in", () => {
    process.env.TZ = "UTC";
    const html = renderToString(<LocalTime value={AT} time label />);
    expect(html).toContain("22 Sept 2026, 01:30 IST");
    expect(html).toContain(`dateTime="${AT}"`);
  });

  it("switches to the viewer's zone after mount, with that zone's label", async () => {
    process.env.TZ = "America/New_York";
    render(<LocalTime value={AT} time label />);
    expect(await screen.findByText("21 Sept 2026, 16:00 EDT")).toBeTruthy();
  });

  it("shows only the date when no time is asked for, and no label", async () => {
    process.env.TZ = "America/New_York";
    render(<LocalTime value={AT} />);
    expect(await screen.findByText("21 Sept 2026")).toBeTruthy();
  });

  it("keeps India time instead of crashing when the browser reports a zone Intl cannot use", async () => {
    process.env.TZ = "Not/AZone";
    render(<LocalTime value={AT} time label />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.getByText("22 Sept 2026, 01:30 IST")).toBeTruthy();
  });

  it("renders a dash for a missing value", () => {
    render(<LocalTime value={null} time label />);
    expect(screen.getByText("-")).toBeTruthy();
  });
});
