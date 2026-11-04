import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateMerge from "@/components/RecruiterCandidateMerge";
import RecruiterDuplicateQueue from "@/components/RecruiterDuplicateQueue";

// hrc-014 (DEC-SCOPE-377): the duplicate-review queue (D2/D9) and the side-by-side merge screen (D4/D6).
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const side = (id: string, code: string, name: string) => ({ id, candidate_code: code, name, location: "Pune", college: "NIT", status: "available", archived: false });
const pair = {
  id: "P1", signals: ["name_location_college", "phone_variant"], status: "open", created_at: "2026-11-04T05:00:00Z", decided_at: null, decided_by: null,
  candidate: side("A1", "CAN-000001", "Meera Rao"), other: side("B1", "CAN-000002", "MEERA RAO"),
};
let fetchMock: ReturnType<typeof vi.fn>;
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  push.mockReset();
});

describe("RecruiterDuplicateQueue", () => {
  let listStatus: number;
  beforeEach(() => {
    listStatus = 200;
    fetchMock = vi.fn((url: string) => {
      if (url.endsWith("/scan")) return Promise.resolve(res({ created: 3 }));
      if (url.endsWith("/dismiss")) return Promise.resolve(res({ ...pair, status: "dismissed" }));
      if (listStatus !== 200) return Promise.resolve(res({ detail: "Your role cannot review or merge duplicate candidates" }, listStatus));
      return Promise.resolve(res({ items: url.includes("status=open") ? [pair] : [], total: url.includes("status=open") ? 1 : 0, limit: 50, offset: 0 }));
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  it("lists open pairs with their signals and a merge link", async () => {
    render(<RecruiterDuplicateQueue />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    const row = (await screen.findByRole("link", { name: "Meera Rao" })).closest("tr")!;
    expect(within(row).getByText("Same name, location and college")).toBeInTheDocument();
    expect(within(row).getByText("Same mobile number written differently")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Review and merge Meera Rao and MEERA RAO" })).toHaveAttribute("href", "/recruiter/candidates/A1/merge?victim=CAN-000002");
  });

  it("dismisses a pair after a confirm and drops it from the list", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<RecruiterDuplicateQueue />);
    fireEvent.click(await screen.findByRole("button", { name: "Not the same person: Meera Rao and MEERA RAO" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: "Meera Rao" })).not.toBeInTheDocument());
    expect(screen.getByText("Marked as not the same person.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/recruiter/candidate-duplicates/P1/dismiss", expect.objectContaining({ method: "POST" }));
  });

  it("does nothing when the dismiss confirm is cancelled", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<RecruiterDuplicateQueue />);
    fireEvent.click(await screen.findByRole("button", { name: "Not the same person: Meera Rao and MEERA RAO" }));
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining("/dismiss"), expect.anything());
  });

  it("scans the whole pool and reports what it found", async () => {
    render(<RecruiterDuplicateQueue />);
    await screen.findByRole("link", { name: "Meera Rao" });
    fireEvent.click(screen.getByRole("button", { name: "Check the whole pool" }));
    expect(await screen.findByText("3 new pairs to review.")).toBeInTheDocument();
  });

  it("shows an empty state per tab", async () => {
    render(<RecruiterDuplicateQueue />);
    await screen.findByRole("link", { name: "Meera Rao" });
    fireEvent.click(screen.getByRole("button", { name: "Merged" }));
    expect(await screen.findByText("No merged pairs yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Merged" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows the API's refusal", async () => {
    listStatus = 403;
    render(<RecruiterDuplicateQueue />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Your role cannot review or merge duplicate candidates");
  });
});

describe("RecruiterCandidateMerge", () => {
  const mside = (over: Record<string, unknown>) => ({
    id: "S1", candidate_code: "CAN-000001", status: "available", created_at: "2026-01-01T00:00:00Z", mobile: "+919800000001", email: "a@x.in",
    name: "Meera Rao", location: null, qualification: "B.Tech", college: "IIT", passing_year: 2020, experience_months: 24, current_company: null,
    notice_days: null, preferred_role: null, linkedin: null, ...over,
  });
  const preview = {
    survivor: mside({}),
    victim: mside({ id: "V1", candidate_code: "CAN-000002", email: "b@x.in", college: "NIT", location: "Pune" }),
    fields: ["name", "location", "qualification", "college", "passing_year", "experience_months", "current_company", "notice_days", "preferred_role", "linkedin"],
    conflicts: [], moved: { applications: 2, share_items: 0, calls: 1, messages: 0, consents: 0, skills: 3, resumes: 1 },
  };
  let current: unknown;
  let mergeStatus: number;
  beforeEach(() => {
    current = preview;
    mergeStatus = 200;
    fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        return Promise.resolve(mergeStatus === 200 ? res({ id: "S1", victim_id: "V1", victim_code: "CAN-000002", moved: preview.moved, kept_applications: [] })
          : res({ detail: "Something changed while merging. Reload and try again" }, mergeStatus));
      }
      return Promise.resolve(res(current));
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  it("compares both side by side, takes the chosen values and goes to the survivor", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<RecruiterCandidateMerge survivorId="S1" victimCode="CAN-000002" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    await screen.findByRole("table", { name: "Compare the two candidates" });
    expect(screen.getByText("(filled from the duplicate)")).toBeInTheDocument(); // location
    expect(screen.getByText(/Moves to CAN-000001: requirements: 2, calls: 1, skills: 3, resumes: 1/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Keep NIT for College" }));
    fireEvent.change(screen.getByLabelText("Reason (optional)"), { target: { value: " same person " } });
    fireEvent.click(screen.getByRole("button", { name: "Merge CAN-000002 into CAN-000001" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/recruiter/candidates/S1?merged=CAN-000002"));
    const [, init] = fetchMock.mock.calls.find(([, i]) => i?.method === "POST")!;
    expect(JSON.parse(init.body)).toEqual({ victim_code: "CAN-000002", use_victim: ["college"], reason: "same person" });
  });

  it("links to the swapped direction", async () => {
    render(<RecruiterCandidateMerge survivorId="S1" victimCode="CAN-000002" />);
    expect(await screen.findByRole("link", { name: "Keep CAN-000002 instead" })).toHaveAttribute("href", "/recruiter/candidates/V1/merge?victim=CAN-000001");
  });

  it("blocks the merge while an open application on the same requirement exists", async () => {
    current = { ...preview, conflicts: [{ application_id: "A", job_id: "J", job_title: "Java Dev", status: "shortlisted", blocking: true }] };
    render(<RecruiterCandidateMerge survivorId="S1" victimCode="CAN-000002" />);
    expect(await screen.findByText(/Both are on Java Dev/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Merge CAN-000002 into CAN-000001" })).toBeDisabled();
  });

  it("keeps the form and shows the refusal when the merge fails", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mergeStatus = 409;
    render(<RecruiterCandidateMerge survivorId="S1" victimCode="CAN-000002" />);
    fireEvent.click(await screen.findByRole("button", { name: "Merge CAN-000002 into CAN-000001" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Something changed while merging");
    expect(push).not.toHaveBeenCalled();
  });

  it("shows a preview refusal without a merge button", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(res({ detail: "CAN-000002 is linked to a student login. Merge the other candidate into it instead" }, 409)));
    render(<RecruiterCandidateMerge survivorId="S1" victimCode="CAN-000002" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("linked to a student login");
    expect(screen.queryByRole("button", { name: /^Merge/ })).not.toBeInTheDocument();
  });
});
