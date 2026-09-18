import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkflowPanel from "@/components/WorkflowPanel";
import type { User } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

const asUser = (role: string) => ({ id: "u1", email: `${role}@example.local`, full_name: "Test User", role, division: "it" }) as unknown as User;

function stubFetch() {
  const mock = vi.fn(() => Promise.resolve(new Response(JSON.stringify([]), { status: 200 })));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// ENH-003: the expired set-password links panel sits on the admin dashboards of all three admin roles
// (deliberately NOT gated by `isAdmin`, which excludes overseas_admin) and nowhere else.
describe("WorkflowPanel mounts the expired-links panel", () => {
  it.each(["it_admin", "overseas_admin", "super_admin"])("on the %s dashboard", async (role) => {
    const mock = stubFetch();
    render(<WorkflowPanel user={asUser(role)} section="dashboard" />);
    expect(await screen.findByRole("heading", { name: "Expired set-password links" })).toBeInTheDocument();
    await waitFor(() => expect(mock).toHaveBeenCalledWith("/api/v1/admin/users?provisioning_status=link_expired", expect.anything()));
  });

  it("not on other sections of an admin's portal", () => {
    stubFetch();
    render(<WorkflowPanel user={asUser("it_admin")} section="users" />);
    expect(screen.queryByRole("heading", { name: /Expired set-password links/ })).toBeNull();
  });

  it.each(["trainer", "it_student", "school_coordinator", "counselor"])("not on the %s dashboard", (role) => {
    stubFetch();
    render(<WorkflowPanel user={asUser(role)} section="dashboard" />);
    expect(screen.queryByRole("heading", { name: /Expired set-password links/ })).toBeNull();
  });
});
