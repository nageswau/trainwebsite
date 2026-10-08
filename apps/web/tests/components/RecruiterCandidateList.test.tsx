import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateList from "@/components/RecruiterCandidateList";

// rec-009 (AC2, S2-§13; QA-03): the list shows the source on every row; a read-only role (hr_team) has no source picker, because the
// recruiter catalogues are closed to it (rec-002 C3) -- the list must not call them.
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/recruiter/candidates", useSearchParams: () => new URLSearchParams() }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const item = {
  id: "c1", candidate_code: "CAN-000001", name: "Rahul", location: "Hyderabad", experience_months: 30, preferred_role: "Python Developer",
  source: { id: "s2", name: "Edusphere students", active: true }, source_detail: "Python Full Stack", status: "available", archived: false,
  created_at: "2026-10-08T06:00:00Z",
};
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn((url: string) => {
    if (url.startsWith("/api/v1/recruiter/catalogue/candidate-sources")) {
      return Promise.resolve(res({ items: [{ id: "s2", name: "Edusphere students", active: true, sort_order: 2 }], total: 1, limit: 100, offset: 0 }));
    }
    return Promise.resolve(res({ items: [item], total: 1, limit: 50, offset: 0 }));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RecruiterCandidateList", () => {
  it("shows the source and its detail on the row, and offers the source filter to writers", async () => {
    render(<RecruiterCandidateList sourceFilter />);
    expect(await screen.findByRole("link", { name: "Rahul" })).toHaveAttribute("href", "/recruiter/candidates/c1");
    expect(screen.getByText("Python Full Stack")).toBeInTheDocument();
    expect(screen.getByText("2 yr 6 mo")).toBeInTheDocument();
    expect(await screen.findByRole("option", { name: "Edusphere students" })).toBeInTheDocument();
  });

  it("has no source picker and never calls the catalogue for a read-only role", async () => {
    render(<RecruiterCandidateList sourceFilter={false} />);
    expect(await screen.findByRole("link", { name: "Rahul" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Source")).toBeNull();
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("/catalogue/"))).toBe(false);
  });
});
