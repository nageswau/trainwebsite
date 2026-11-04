import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateDetail from "@/components/RecruiterCandidateDetail";
import type { CandidateDetail } from "@/lib/recruiterCandidates";

// hrc-012 browser QA-01: a collaborator-only change leaves `updated_at` as it was, yet the Change history must re-read (it was keyed on
// `updated_at` alone, so the new "Assign" entry only appeared after a refresh).
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }), usePathname: () => "/", useSearchParams: () => new URLSearchParams() }));

const ravi = { id: "u2", full_name: "Ravi", active: true };
const candidate = {
  id: "C1", candidate_code: "CAN-000001", name: "Asha Rao", location: null, experience_months: null, preferred_role: null,
  source: { id: "s1", name: "Referral", active: true }, source_detail: null, status: "available", archived: false, created_at: "2026-11-01T00:00:00Z",
  mobile: null, email: "a@x.in", qualification: null, college: null, passing_year: null, current_company: null,
  notice_days: null, preferred_locations: [], linkedin: null, archived_at: null, created_by: null, updated_by: null, updated_at: "2026-11-02T00:00:00Z",
  resumes: [], can_edit: true, merged_into: null,
  ownership: { owner: { id: "u1", full_name: "Asha", active: true }, placement_officer: null, collaborators: [ravi], shared_ownership: true, can_assign: true },
} as unknown as CandidateDetail;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn((_url: string, init?: RequestInit) =>
    Promise.resolve(init?.method === "PUT"
      ? new Response(JSON.stringify({ ...candidate, ownership: { ...candidate.ownership, collaborators: [] } }), { status: 200 })
      : new Response("{}", { status: 404 })));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("hrc-012 ownership change and the Change history", () => {
  it("re-reads the history after an ownership change that keeps updated_at", async () => {
    render(<RecruiterCandidateDetail initial={candidate} />);
    const historyCalls = () => fetchMock.mock.calls.filter(([u]) => String(u).includes("/C1/history")).length;
    await waitFor(() => expect(historyCalls()).toBe(1));
    fireEvent.click(screen.getByRole("button", { name: "Change ownership" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove Ravi" }));
    fireEvent.click(screen.getByRole("button", { name: "Save ownership" }));
    await screen.findByText("Ownership updated.");
    await waitFor(() => expect(historyCalls()).toBe(2));
  });
});
