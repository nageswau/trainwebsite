import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import WorkflowPanel from "@/components/WorkflowPanel";
import type { User } from "@/lib/types";

// hrc-001 (DEC-SCOPE-371 H1/H6, browser QA-01): HR owns no requirement, so the legacy placement write forms (which now answer 403) are
// not offered to it; the recruiter keeps them.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

const user = (role: string) => ({ id: "u1", email: "u@example.local", full_name: "U", role, division: "it", profile: {} }) as unknown as User;
const WRITE_FORMS = ["Create job requirement", "Update job requirement", "Schedule interview", "Record interview result", "Create offer"];
const SECTIONS = ["job-requirements", "company-requirements", "interviews", "offers"];

beforeEach(() => vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("[]", { status: 200 })))));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("WorkflowPanel legacy placement writes (hrc-001)", () => {
  it("offers HR no legacy write form", () => {
    for (const section of SECTIONS) {
      const { unmount } = render(<WorkflowPanel user={user("hr_team")} section={section} />);
      for (const name of WRITE_FORMS) expect(screen.queryByRole("heading", { name })).toBeNull();
      unmount();
    }
  });

  it("still offers the recruiter the legacy write forms", () => {
    const seen = new Set<string>();
    for (const section of SECTIONS) {
      const { unmount } = render(<WorkflowPanel user={user("placement_team")} section={section} />);
      for (const name of WRITE_FORMS) if (screen.queryByRole("heading", { name })) seen.add(name);
      unmount();
    }
    expect([...seen].sort()).toEqual([...WRITE_FORMS].sort());
  });
});
