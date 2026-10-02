import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import AgentNotificationsSection from "@/components/AgentNotificationsSection";
import type { NotificationItem } from "@/components/SchoolNotificationList";
import type { User } from "@/lib/types";

// AGN-017 (DEC-SCOPE-055 N8, spec §9): the agency Notifications page -- the list, and its empty, failed, at-window and non-agency states.
afterEach(cleanup);

const master = { id: "m1", role: "agent", full_name: "Master", email: "m@example.local", agent_member_role: "master" } as unknown as User;
const staff = { ...master, id: "s1", agent_member_role: "staff" } as unknown as User;
const root = { id: "r1", role: "super_admin", full_name: "Root", email: "r@example.local" } as unknown as User;
const notice = (id: string, over: Partial<NotificationItem> = {}): NotificationItem => ({
  id, title: `Notice ${id}`, body: `Body ${id}`, read: false, action_url: "/overseas/agent/tasks", created_at: "2026-10-02T04:30:00Z", ...over,
});

describe("AgentNotificationsSection", () => {
  it("lists notices under one Notifications heading with an Open link each", () => {
    render(<AgentNotificationsSection user={staff} items={[notice("1"), notice("2", { read: true })]} />);
    expect(screen.getByRole("heading", { level: 1, name: "Notifications" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Notifications" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open: Notice 1" })).toHaveAttribute("href", "/overseas/agent/tasks");
    expect(screen.getAllByText("new")).toHaveLength(1);
    expect(screen.queryByText(/Showing your latest/)).toBeNull();
  });

  it("says what will appear when there is nothing yet", () => {
    render(<AgentNotificationsSection user={master} items={[]} />);
    expect(screen.getByText(/No notifications yet\. You'll be told here about assignments/)).toBeInTheDocument();
  });

  it("shows the section-unavailable state when the list could not load", () => {
    render(<AgentNotificationsSection user={master} items={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("This section couldn't load. Refresh to try again.");
    expect(screen.queryByRole("list", { name: "Notifications" })).toBeNull();
  });

  it("says the list is the latest 100 when it is full", () => {
    render(<AgentNotificationsSection user={master} items={Array.from({ length: 100 }, (_, i) => notice(String(i)))} />);
    expect(screen.getByText("Showing your latest 100 notifications.")).toBeInTheDocument();
  });

  it("shows a non-agency viewer a note instead of a list", () => {
    render(<AgentNotificationsSection user={root} items={[notice("1")]} />);
    expect(screen.getByText("Agency notifications go to the agency's own Masters and Staff.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Notifications" })).toBeNull();
  });
});
