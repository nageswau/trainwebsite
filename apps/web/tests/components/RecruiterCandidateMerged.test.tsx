import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateDetail from "@/components/RecruiterCandidateDetail";
import type { CandidateDetail } from "@/lib/recruiterCandidates";

// hrc-014 (DEC-SCOPE-377 D8): the candidate page after a merge -- the survivor's one-time notice, the victim's banner and no Restore.
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }), usePathname: () => "/", useSearchParams: () => new URLSearchParams() }));

const candidate = {
  id: "C1", candidate_code: "CAN-000001", name: "Asha Rao", location: null, experience_months: null, preferred_role: null,
  source: { id: "s1", name: "Referral", active: true }, source_detail: null, status: "available", archived: false, created_at: "2026-11-01T00:00:00Z",
  mobile: null, email: "a@x.in", qualification: null, college: null, passing_year: null, current_company: null,
  notice_days: null, preferred_locations: [], linkedin: null, archived_at: null, created_by: null, updated_by: null, updated_at: "2026-11-02T00:00:00Z",
  resumes: [], can_edit: true, merged_into: null,
} as unknown as CandidateDetail;

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}", { status: 404 }))));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("hrc-014 merged candidates", () => {
  it("shows the survivor's notice once and drops ?merged from the address (browser QA-02)", () => {
    window.history.pushState({}, "", "/recruiter/candidates/C1?merged=CAN-000002");
    const replace = vi.spyOn(window.history, "replaceState");
    render(<RecruiterCandidateDetail initial={candidate} merged="CAN-000002" />);
    expect(screen.getByText("CAN-000002 was merged into this candidate.")).toBeInTheDocument();
    expect(replace).toHaveBeenCalledWith(expect.anything(), "", "/recruiter/candidates/C1");
  });

  it("points a merged candidate at the survivor and offers no Restore", () => {
    const merged = { ...candidate, archived: true, archived_at: "2026-11-04T00:00:00Z", merged_into: { id: "S9", candidate_code: "CAN-000009" } } as CandidateDetail;
    render(<RecruiterCandidateDetail initial={merged} />);
    expect(screen.getByRole("link", { name: "CAN-000009" })).toHaveAttribute("href", "/recruiter/candidates/S9");
    expect(screen.queryByRole("button", { name: "Restore" })).toBeNull();
  });
});
