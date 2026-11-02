import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PortalPage from "@/components/PortalPage";
import { ApiError, serverApi } from "@/lib/api";
import { PORTAL_NAV, type NavItem } from "@/lib/navigation";

// itc-025 (DEC-SCOPE-347): a batch, course or timetable change of an IT counselor's student reaches the counselor's own Notifications
// page -- the shared list (GET /workflows/notifications), with no workflow panel, as itc-002 (student) and itc-009 (IT admin) did.
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
const COUNSELOR = { id: "c1", role: "counselor", division: "it", full_name: "Kavya Counselor", email: "k@example.local" };
const NOTICE = { id: "n1", title: "Student's batch updated", read: false, action_url: "/it/counselor/timetable", created_at: "2026-11-02T04:30:00Z",
  body: "The course, batch or timetable of your student was updated. Open EduSphere to see what changed. Changed: trainer.",
  event_type: "it.batch.student_changed", entity_type: "batch", entity_id: "b1" };

function answer(me: unknown, list: unknown = [NOTICE]) {
  const settle = (value: unknown) => (value instanceof Error ? Promise.reject(value) : Promise.resolve(value));
  api.mockImplementation((path: string) => {
    if (path === "/api/v1/auth/me") return settle(me);
    if (path === "/api/v1/workflows/notifications") return settle(list);
    return settle({ title: "Notifications", subtitle: "Your own notifications.", columns: [], rows: [] });
  });
}

beforeEach(() => api.mockReset() && undefined);
afterEach(cleanup);

describe("itc-025 IT counselor notifications", () => {
  it("lists Notifications in the IT counselor navigation", () => {
    expect(PORTAL_NAV["it/counselor"].map((i) => i.href)).toContain("/it/counselor/notifications");
  });

  it("mounts the shared list with the batch-change notice and no workflow panel", async () => {
    answer(COUNSELOR);
    render(await PortalPage({ division: "it", role: "counselor", section: "notifications" }));
    expect(screen.getByText(NOTICE.body)).toBeInTheDocument();
    expect(screen.queryByText(/workflow panel/)).toBeNull();
  });

  it("says what lands there when the list is empty", async () => {
    answer(COUNSELOR, []);
    render(await PortalPage({ division: "it", role: "counselor", section: "notifications" }));
    expect(screen.getByText(/No notifications yet\. Batch and timetable changes of your students appear here\./)).toBeInTheDocument();
  });

  it("a failed list read shows the section-unavailable card, not an empty list", async () => {
    answer(COUNSELOR, new ApiError("Server error", 500));
    render(await PortalPage({ division: "it", role: "counselor", section: "notifications" }));
    expect(screen.queryByText(/No notifications yet/)).toBeNull();
    expect(screen.queryByText(NOTICE.body)).toBeNull();
  });
});
