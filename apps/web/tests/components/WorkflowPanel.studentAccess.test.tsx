import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkflowPanel from "@/components/WorkflowPanel";
import type { User } from "@/lib/types";

// nehn-018 (DEC-SCOPE-304): the IT admin's Payments page carries the student access rules; the Course page's live classes take the
// lock the page already knows. Pinned here because both live in WorkflowPanel's one render line (a merge once dropped them).
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams(), usePathname: () => "/it/admin/payments",
}));

const user = (role: string) => ({ id: "u1", email: `${role}@example.local`, full_name: "Ira", role, division: "it", profile: {} }) as unknown as User;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("WorkflowPanel and nehn-018", () => {
  it("shows the student access rules on the IT admin's Payments page", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    render(<WorkflowPanel user={user("it_admin")} section="payments" />);
    expect(screen.getByRole("heading", { name: "Student access by payment" })).toBeInTheDocument();
  });

  it("does not show them to the overseas admin", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    render(<WorkflowPanel user={{ ...user("overseas_admin"), division: "overseas" } as User} section="payments" />);
    expect(screen.queryByRole("heading", { name: "Student access by payment" })).toBeNull();
  });

  it("passes the known live-classes lock to the Course page's live classes, without fetching them", () => {
    const fetchMock = vi.fn(() => new Promise(() => {}));
    vi.stubGlobal("fetch", fetchMock);
    const lock = { feature: "live_classes", label: "Live classes", required_state: "partially_paid", current_state: "enrolled_pending_payment" } as const;
    render(<WorkflowPanel user={user("it_student")} section="course" liveClassesLock={lock} />);
    expect(screen.getByRole("heading", { name: "Live classes is locked" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith("/api/v1/communications/it/live-sessions");
  });
});
