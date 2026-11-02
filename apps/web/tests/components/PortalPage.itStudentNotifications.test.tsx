import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PortalPage from "@/components/PortalPage";
import { ApiError, serverApi } from "@/lib/api";
import type { NavItem } from "@/lib/navigation";

// itc-002 (DEC-SCOPE-336): the IT student's Notifications section mounts the shared list under the header-only payload, with no
// workflow (send-notification) panel; a failed list shows the section-unavailable card.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, serverApi: vi.fn() };
});
vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("notFound"); }, useSearchParams: () => new URLSearchParams("") }));
vi.mock("@/components/PortalShell", () => ({
  default: ({ nav, children }: { nav: NavItem[]; children: React.ReactNode }) => (
    <div>
      <ul aria-label="test nav">{nav.map((i) => <li key={i.href}>{i.href}</li>)}</ul>
      {children}
    </div>
  ),
}));
vi.mock("@/components/WorkflowPanel", () => ({ default: ({ section }: { section: string }) => <p>workflow panel: {section}</p> }));
vi.mock("@/components/PortalSection", () => ({ default: ({ lead }: { lead?: React.ReactNode }) => <div><h1>Notifications</h1>{lead}</div> }));

const api = vi.mocked(serverApi);
const STUDENT = { id: "u1", role: "it_student", full_name: "Arjun Rao", email: "a@example.local", student_code: "EDU-1" };
const LIST = [{ id: "n1", title: "Payment received", body: "Your payment was received. Open EduSphere to view your receipt.", read: false, action_url: "/it/student/fees", created_at: "2026-11-02T04:30:00Z", event_type: "it.fee.payment_received", entity_type: "payment", entity_id: "p1" }];

function answer(list: unknown = LIST) {
  const settle = (value: unknown) => (value instanceof Error ? Promise.reject(value) : Promise.resolve(value));
  api.mockImplementation((path: string) => {
    if (path === "/api/v1/auth/me") return settle(STUDENT);
    if (path === "/api/v1/workflows/notifications") return settle(list);
    if (path === "/api/v1/workflows/it/student/access") return settle(null);
    return settle({ title: "Notifications", subtitle: "Your own notifications.", columns: [], rows: [] });
  });
}

beforeEach(() => {
  api.mockReset();
  answer();
});
afterEach(cleanup);

describe("PortalPage IT student notifications (itc-002)", () => {
  it("lists the student's own notices with their deep link and no workflow panel", async () => {
    render(await PortalPage({ division: "it", role: "student", section: "notifications" }));
    expect(screen.getByRole("link", { name: "Open: Payment received" })).toHaveAttribute("href", "/it/student/fees");
    expect(screen.getByLabelText("Type")).toBeInTheDocument();
    expect(screen.queryByText(/workflow panel/)).toBeNull();
    expect(screen.getByText("/it/student/notifications")).toBeInTheDocument();
  });

  it("says when there is nothing yet", async () => {
    answer([]);
    render(await PortalPage({ division: "it", role: "student", section: "notifications" }));
    expect(screen.getByText(/No notifications yet/)).toBeInTheDocument();
  });

  it("shows the section-unavailable card when the list fails", async () => {
    answer(new ApiError("Server error", 500));
    render(await PortalPage({ division: "it", role: "student", section: "notifications" }));
    expect(screen.queryByRole("list", { name: "Notifications" })).toBeNull();
    expect(screen.getByText(/unavailable|couldn.t load|try again/i)).toBeInTheDocument();
  });

  it("does not fetch the list on other student sections", async () => {
    render(await PortalPage({ division: "it", role: "student", section: "fees" }));
    expect(api.mock.calls.map((c) => c[0])).not.toContain("/api/v1/workflows/notifications");
  });
});
