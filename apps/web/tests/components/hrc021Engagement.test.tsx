import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateDetail from "@/components/RecruiterCandidateDetail";
import RecruiterCandidateList from "@/components/RecruiterCandidateList";
import RecruiterFindCandidates from "@/components/RecruiterFindCandidates";
import { ENGAGEMENTS, type CandidateDetail } from "@/lib/recruiterCandidates";
import { paramsOf, searchBody, stateOf } from "@/lib/recruiterCandidateSearch";
import { clearPermissions } from "@/lib/usePermissions";

// hrc-021 (DEC-SCOPE-397 E7): the derived engagement status as a chip on the list, the detail and the Find Candidates cards, and as a
// filter on the list (URL `engagement=`) and the search (body `engagement`). An older API answer without it renders nothing, not a crash.
let query = "";
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn() }), usePathname: () => "/recruiter/candidates", useSearchParams: () => new URLSearchParams(query),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const contacted = { key: "contacted", label: "Contacted" };
const item = {
  id: "c1", candidate_code: "CAN-000001", name: "Rahul", location: "Hyderabad", experience_months: 30, preferred_role: "Python Developer",
  source: { id: "s2", name: "Referral", active: true }, source_detail: null, status: "available", archived: false, created_at: "2026-10-08T06:00:00Z",
  owner: null, engagement: contacted,
};
let reply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  query = "";
  clearPermissions();
  push.mockReset();
  reply = () => res({ items: [item, { ...item, id: "c2", name: "Meena", engagement: undefined }], total: 2, limit: 50, offset: 0 });
  fetchMock = vi.fn((url: string) => {
    if (String(url).includes("/catalogue/")) return Promise.resolve(res({ items: [], total: 0, limit: 100, offset: 0 }));
    if (url === "/api/v1/auth/me/permissions") return Promise.resolve(res({ permissions: [] }));
    return Promise.resolve(reply());
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("hrc-021 engagement status", () => {
  it("lists every engagement in the design's order", () => {
    expect(ENGAGEMENTS.map((e) => e.key)).toEqual([
      "new", "uncontacted", "contacted", "screened", "shortlisted", "active", "inactive", "placed", "not_interested", "do_not_contact",
    ]);
  });

  it("the list shows an Engagement column chip, and a row without one shows a dash", async () => {
    render(<RecruiterCandidateList sourceFilter={false} />);
    const rows = await screen.findAllByRole("row");
    expect(screen.getByRole("columnheader", { name: "Engagement" })).toBeInTheDocument();
    expect(within(rows[1]).getByText("Contacted")).toHaveClass("badge");
    expect(within(rows[2]).queryByText("Contacted")).toBeNull();
  });

  it("the list's Engagement filter pushes ?engagement= and a URL value is sent to the API", async () => {
    render(<RecruiterCandidateList sourceFilter={false} />);
    await screen.findAllByRole("row");
    fireEvent.change(screen.getByLabelText("Engagement"), { target: { value: "screened" } });
    expect(push).toHaveBeenCalledWith("/recruiter/candidates?engagement=screened", { scroll: false });
    cleanup();
    fetchMock.mockClear();
    query = "engagement=inactive";
    render(<RecruiterCandidateList sourceFilter={false} />);
    await screen.findAllByRole("row");
    const url = String(fetchMock.mock.calls.find(([u]) => String(u).startsWith("/api/v1/recruiter/candidates?"))![0]);
    expect(new URLSearchParams(url.split("?")[1]).get("engagement")).toBe("inactive");
    expect(screen.getByLabelText("Engagement")).toHaveValue("inactive");
  });

  it("the list ignores a hand-edited engagement the API would refuse", async () => {
    query = "engagement=bogus";
    render(<RecruiterCandidateList sourceFilter={false} />);
    await screen.findAllByRole("row");
    const url = String(fetchMock.mock.calls.find(([u]) => String(u).startsWith("/api/v1/recruiter/candidates?"))![0]);
    expect(url).not.toContain("engagement");
  });

  it("the detail shows the engagement beside the stored status", () => {
    const detail = {
      ...item, mobile: null, email: "a@x.in", qualification: null, college: null, passing_year: null, current_company: null, notice_days: null,
      preferred_locations: [], linkedin: null, archived_at: null, created_by: null, updated_by: null, updated_at: "2026-11-02T00:00:00Z", resumes: [],
      can_edit: false, merged_into: null,
    } as unknown as CandidateDetail;
    render(<RecruiterCandidateDetail initial={detail} />);
    expect(screen.getByText("Available")).toHaveClass("badge");
    expect(screen.getByText("Engagement: Contacted")).toHaveClass("badge");
  });

  it("the search keeps engagement in the URL and the body, and drops an unknown value", () => {
    const state = stateOf(new URLSearchParams("all=java&engagement=shortlisted"));
    expect(state.engagement).toBe("shortlisted");
    expect(paramsOf(state).get("engagement")).toBe("shortlisted");
    expect(searchBody(state)).toEqual({ all: ["java"], engagement: "shortlisted" });
    expect(stateOf(new URLSearchParams("all=java&engagement=bogus")).engagement).toBe("");
  });

  it("Find Candidates shows the chip on each card and offers the Engagement filter", async () => {
    query = "all=java";
    const card = { ...item, current_company: null, notice_days: null, skills: [], snippet: null };
    reply = () => res({ items: [card], total: 1, limit: 50, offset: 0, facets: { experience: [], availability: [], location: [] }, terms: [] });
    render(<RecruiterFindCandidates writes={false} sourceFilter={false} />);
    const listItem = await screen.findByRole("listitem", { name: /Rahul/ });
    expect(within(listItem).getByText("Contacted")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Not interested" })).toBeInTheDocument();
    expect(screen.getByLabelText("Engagement")).toHaveValue("");
  });
});
