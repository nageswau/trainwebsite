import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkflowPanel from "@/components/WorkflowPanel";
import type { User } from "@/lib/types";

// itc-003 browser QA-03: the IT counselor's new Students page must not mount the overseas counselor's application panels (they read
// overseas APIs the IT counselor is refused); the overseas counselor's Students page keeps them.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const counselor = (division: string) => ({ id: "c1", role: "counselor", division, full_name: "Ravi", email: "r@example.local" }) as unknown as User;

describe("WorkflowPanel on the counselor's Students page (itc-003)", () => {
  it("shows no overseas application panel to an IT counselor", () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify([]), { status: 200 })));
    vi.stubGlobal("fetch", fetchMock);
    render(<WorkflowPanel user={counselor("it")} section="students" />);
    expect(screen.queryByText("Evaluate Applications")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps the panel for an overseas counselor", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    render(<WorkflowPanel user={counselor("overseas")} section="students" />);
    expect(screen.getByText("Evaluate Applications")).toBeTruthy();
  });
});
