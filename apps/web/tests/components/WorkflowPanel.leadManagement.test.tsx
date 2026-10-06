import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkflowPanel from "@/components/WorkflowPanel";
import type { User } from "@/lib/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams(), usePathname: () => "/it/admin/leads",
}));

const asUser = (role: string, division: string) => ({ id: "u1", email: `${role}@example.local`, full_name: "Test User", role, division }) as unknown as User;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// ADM-002 + bdm-017 (L1, QA17-02): every division admin manages its own division's leads -- the Overseas Admin's School / Agent BDM leads
// need the organization column and the explicit link as much as the IT Admin's College ones. QA17-03: the panel spans the full width, so
// its columns (organization, student, action) fit.
describe("WorkflowPanel mounts the lead management panel", () => {
  it.each([["it_admin", "it"], ["overseas_admin", "overseas"], ["super_admin", "global"]])("for %s on the leads page, full width", (role, division) => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify([]), { status: 200 }))));
    render(<WorkflowPanel user={asUser(role, division)} section="leads" />);
    const heading = screen.getByRole("heading", { name: "Manage leads" });
    expect(heading.closest(".action-card")).toHaveClass("lead-management");
  });

  it.each([["counselor", "overseas", "leads"], ["overseas_admin", "overseas", "dashboard"]])("not for %s on %s", (role, division, section) => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify([]), { status: 200 }))));
    render(<WorkflowPanel user={asUser(role, division)} section={section} />);
    expect(screen.queryByRole("heading", { name: "Manage leads" })).toBeNull();
  });
});
