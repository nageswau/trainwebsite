import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkflowPanel from "@/components/WorkflowPanel";
import type { User } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

const counselor = (division: string) => ({ id: "c1", email: "c@example.local", full_name: "Ritika Counselor", role: "counselor", division }) as unknown as User;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// csc-002 (DEC-SCOPE-227): the walk-in panel is on the overseas counselor's Students page only.
describe("WorkflowPanel walk-in students (csc-002)", () => {
  it("mounts on the overseas counselor's Students page", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0, limit: 20, offset: 0 }), { status: 200 })));
    render(<WorkflowPanel user={counselor("overseas")} section="students" />);
    expect(await screen.findByRole("form", { name: "Add a walk-in student" })).toBeInTheDocument();
  });

  it.each([
    ["overseas", "applications"],
    ["it", "students"],
  ])("is absent for a %s counselor on %s", (division, section) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("[]", { status: 200 })));
    render(<WorkflowPanel user={counselor(division)} section={section} />);
    expect(screen.queryByRole("form", { name: "Add a walk-in student" })).toBeNull();
  });
});
