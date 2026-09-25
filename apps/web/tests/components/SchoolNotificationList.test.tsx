import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SchoolNotificationList, { type NotificationItem } from "@/components/SchoolNotificationList";

// ENH-005 -- coordinators are told, in-app, when a transfer they filed is decided or a student joins their school. Those notices were being
// written but no coordinator screen could show them (found by the browser QA), so this feed is what makes them readable.
afterEach(cleanup);

const n = (id: string, over: Partial<NotificationItem> = {}): NotificationItem => ({ id, title: `Title ${id}`, body: `Body ${id}`, read: true, action_url: null, created_at: "2026-09-21T10:00:00Z", ...over });

describe("SchoolNotificationList", () => {
  it("says what will appear here when there is nothing yet", () => {
    render(<SchoolNotificationList notifications={[]} emptyText="No notifications yet. You will be told here when a transfer is decided." />);
    expect(screen.getByText("No notifications yet. You will be told here when a transfer is decided.")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  // A listitem takes no accessible name from its content, so notices are found by their text (as the other ENH-005 list tests do).
  const item = (text: RegExp) => screen.getAllByRole("listitem").find((li) => text.test(li.textContent ?? ""))!;

  it("lists each notice with its title, body and date, marking unread ones with text", () => {
    render(<SchoolNotificationList notifications={[n("1", { read: false }), n("2")]} emptyText="none" />);
    const first = item(/Title 1/);
    expect(within(first).getByText("new")).toBeTruthy();
    expect(within(first).getByText("Body 1")).toBeTruthy();
    expect(within(first).getByText(/21 Sep\w* 2026/)).toBeTruthy();
    expect(within(item(/Title 2/)).queryByText("new")).toBeNull();
  });

  it("is a list, not a table (AC-24: the new screens render no table; found by the final browser verification)", () => {
    render(<SchoolNotificationList notifications={[n("1"), n("2")]} emptyText="none" />);
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByRole("list", { name: "Notifications" })).toBeTruthy();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("offers Open only for a notice that has a link, and uses that link as is", () => {
    render(<SchoolNotificationList notifications={[n("1", { action_url: "/school/coordinator/transfers" }), n("2")]} emptyText="none" />);
    const links = screen.getAllByRole("link", { name: /^Open/ });
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute("href")).toBe("/school/coordinator/transfers");
  });

  // Now a client component, the list is rendered on the server (UTC) and hydrated in the browser: its time must be formatted in one
  // fixed zone or React reports hydration error #418 (found by the ENH-005 E2E; QA-022-06 precedent). 20:00Z is 01:30 next day in IST.
  it("shows the time in the school zone whatever the machine zone is", () => {
    render(<SchoolNotificationList notifications={[n("1", { created_at: "2026-09-21T20:00:00Z" })]} emptyText="none" />);
    expect(within(item(/Title 1/)).getByText(/22 Sep\w* 2026, 01:30/)).toBeTruthy();
  });

  // QA-023-06: every row said just "Open", so a screen reader's link list could not tell the notices apart.
  it("names each Open link after its notice while still showing Open", () => {
    render(<SchoolNotificationList notifications={[n("1", { action_url: "/a" }), n("2", { action_url: "/b" })]} emptyText="none" />);
    expect(screen.getByRole("link", { name: "Open: Title 1" })).toHaveTextContent("Open");
    expect(screen.getByRole("link", { name: "Open: Title 2" })).toHaveTextContent("Open");
  });

  // QA-023-06: the "new" badge never cleared. Opening an unread notice marks it read (fire-and-forget: navigation is never held up).
  describe("marking read on Open", () => {
    const stopNavigation = (e: Event) => e.preventDefault(); // jsdom cannot navigate; the real browser follows the href
    beforeEach(() => document.addEventListener("click", stopNavigation));
    afterEach(() => {
      document.removeEventListener("click", stopNavigation);
      vi.unstubAllGlobals();
    });

    it("marks an unread notice read when it is opened", () => {
      const mock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
      vi.stubGlobal("fetch", mock);
      render(<SchoolNotificationList notifications={[n("abc", { read: false, action_url: "/a" })]} emptyText="none" />);
      fireEvent.click(screen.getByRole("link", { name: "Open: Title abc" }));
      expect(mock).toHaveBeenCalledWith("/api/v1/workflows/notifications/abc/read", expect.objectContaining({ method: "PATCH", keepalive: true }));
    });

    it("sends nothing for a notice that is already read", () => {
      const mock = vi.fn();
      vi.stubGlobal("fetch", mock);
      render(<SchoolNotificationList notifications={[n("abc", { read: true, action_url: "/a" })]} emptyText="none" />);
      fireEvent.click(screen.getByRole("link", { name: "Open: Title abc" }));
      expect(mock).not.toHaveBeenCalled();
    });
  });
});
