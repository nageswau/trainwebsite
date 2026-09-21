import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

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
    const links = screen.getAllByRole("link", { name: "Open" });
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute("href")).toBe("/school/coordinator/transfers");
  });
});
