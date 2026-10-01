import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkflowPanel from "@/components/WorkflowPanel";
import type { User } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

const asUser = (role: string) => ({ id: "u1", email: `${role}@example.local`, full_name: "Test User", role, division: "overseas" }) as unknown as User;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// ENH-029: the bulk onboarding panel sits on the Admin Schools page under the same role gate. QA-029-02/09: it comes after
// Create school and Edit school profile (which keep sharing a row, as before ENH-029) and spans the full width, so its result
// table has room for every column.
describe("WorkflowPanel mounts the bulk school onboarding panel", () => {
  it.each(["overseas_admin", "super_admin"])("on the %s schools page, after Create school and Edit school profile", (role) => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify([]), { status: 200 }))));
    render(<WorkflowPanel user={asUser(role)} section="schools" />);
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    const create = headings.indexOf("Create school");
    expect(create).toBeGreaterThanOrEqual(0);
    expect(headings.slice(create, create + 3)).toEqual(["Create school", "Edit school profile", "Onboard several schools (CSV)"]);
  });

  it.each([
    ["overseas_admin", "dashboard"],
    ["school_coordinator", "schools"],
    ["it_admin", "schools"],
  ])("not for %s on %s", (role, section) => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify([]), { status: 200 }))));
    render(<WorkflowPanel user={asUser(role)} section={section} />);
    expect(screen.queryByRole("heading", { name: "Onboard several schools (CSV)" })).toBeNull();
  });
});
