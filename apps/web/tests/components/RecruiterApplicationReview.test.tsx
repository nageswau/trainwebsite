import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterRequirementCandidates from "@/components/RecruiterRequirementCandidates";
import type { RecApplication, RequirementCandidates } from "@/lib/recruiterApplications";

// hrc-009 (DEC-SCOPE-390 R4/R8/R9): after an eligibility change, flagged applications carry a "Needs review" badge, the section says how
// many, "Show only these" reads the review list, and a writer confirms one (or moves it with Change status).
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const STATUSES = [{ key: "sourced", label: "Sourced", initial: true }];
const application = (over: Partial<RecApplication> = {}): RecApplication => ({
  id: "A1", job_id: "J1", candidate: { id: "C1", code: "CAN-000001", name: "Rahul Kumar" }, status: "sourced", status_label: "Sourced",
  stage_changed_at: "2026-10-08T05:30:00Z", created_at: "2026-10-08T05:30:00Z", allowed_statuses: [{ key: "screened", label: "Screened" }],
  screening_result: null, needs_review_since: "2026-11-04T05:30:00Z", ...over,
});
const other = application({ id: "A2", candidate: { id: "C2", code: "CAN-000002", name: "Neha Shah" }, needs_review_since: null });

let list: RequirementCandidates;
let confirmReply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  list = { items: [application(), other], statuses: STATUSES, can_add: true, needs_review_count: 1 };
  confirmReply = () => res({ application: application({ needs_review_since: null }) });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST" && url.endsWith("/confirm-review")) return Promise.resolve(confirmReply());
    if (url === "/api/v1/recruiter/requirements/J1/candidates?needs_review=true")
      return Promise.resolve(res({ ...list, items: list.items.filter((a) => a.needs_review_since) }));
    if (url === "/api/v1/recruiter/requirements/J1/candidates") return Promise.resolve(res(list));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const item = (name: string) => screen.getByRole("listitem", { name });

describe("RecruiterRequirementCandidates — eligibility review", () => {
  it("badges flagged applications and says how many need review", async () => {
    render(<RecruiterRequirementCandidates requirementId="J1" />);
    await screen.findByRole("list", { name: "Candidates on this requirement" });
    expect(within(item("Rahul Kumar")).getByText("Needs review")).toBeTruthy();
    expect(within(item("Neha Shah")).queryByText("Needs review")).toBeNull();
    expect(screen.getByText("1 application needs review after an eligibility change. Confirm it or change its status.")).toBeTruthy();
    expect(within(item("Neha Shah")).queryByRole("button", { name: /Confirm review/ })).toBeNull();
  });

  it("shows only the review list, and all candidates again", async () => {
    render(<RecruiterRequirementCandidates requirementId="J1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Show only these" }));
    await waitFor(() => expect(screen.queryByRole("listitem", { name: "Neha Shah" })).toBeNull());
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/recruiter/requirements/J1/candidates?needs_review=true", expect.anything());
    expect(screen.getByRole("button", { name: "Show all candidates" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("heading", { name: "Candidates needing review (1)" })).toBeTruthy(); // QA-03: the count is the filtered list's
    fireEvent.click(screen.getByRole("button", { name: "Show all candidates" }));
    expect(await screen.findByRole("listitem", { name: "Neha Shah" })).toBeTruthy();
  });

  it("confirms a review and re-reads the list", async () => {
    render(<RecruiterRequirementCandidates requirementId="J1" />);
    await screen.findByRole("list", { name: "Candidates on this requirement" });
    list = { ...list, items: [application({ needs_review_since: null }), other], needs_review_count: 0 };
    fireEvent.click(within(item("Rahul Kumar")).getByRole("button", { name: "Confirm review of Rahul Kumar" }));
    expect(await screen.findByText("Review confirmed — Rahul Kumar stays Sourced.")).toBeTruthy();
    await waitFor(() => expect(screen.queryByText("Needs review")).toBeNull());
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/recruiter/applications/A1/confirm-review", expect.objectContaining({ method: "POST" }));
    expect(screen.queryByRole("button", { name: "Show only these" })).toBeNull();
  });

  it("shows the API's refusal", async () => {
    confirmReply = () => res({ detail: "This application does not need a review" }, 409);
    render(<RecruiterRequirementCandidates requirementId="J1" />);
    await screen.findByRole("list", { name: "Candidates on this requirement" });
    fireEvent.click(within(item("Rahul Kumar")).getByRole("button", { name: "Confirm review of Rahul Kumar" }));
    expect(await screen.findByText("This application does not need a review")).toBeTruthy();
  });

  it("says when nothing is left to review in the review list", async () => {
    render(<RecruiterRequirementCandidates requirementId="J1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Show only these" }));
    await screen.findByRole("button", { name: "Show all candidates" });
    list = { ...list, items: [other], needs_review_count: 0 };
    confirmReply = () => res({ application: application({ needs_review_since: null }) });
    fireEvent.click(screen.getByRole("button", { name: "Confirm review of Rahul Kumar" }));
    expect(await screen.findByText("No applications need review.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Show all candidates" })).toBeTruthy();
  });
});
