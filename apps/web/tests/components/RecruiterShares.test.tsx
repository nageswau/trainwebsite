import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterShares from "@/components/RecruiterShares";
import type { Share, ShareItem } from "@/lib/recruiterShares";

// rec-019 (DEC-SCOPE-158; S9, S14): the Shared profiles section -- loading / error + retry / empty, each share with its candidates and
// responses, and the writer's response form.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const item = (over: Partial<ShareItem> = {}): ShareItem => ({
  id: "I1", candidate: { id: "C1", code: "CAN-000001", name: "Rahul" }, application_id: "A1", has_resume: true, link_expires_at: null,
  response: "pending", response_label: "Pending", feedback: null, responded_by: null, responded_at: null, ...over,
});
const share = (over: Partial<Share> = {}): Share => ({
  id: "S1", channel: "email", channel_label: "Email", requirement: { id: "J1", code: "REQ-000001", title: "Java Dev" }, company_id: "CO1",
  contact: { id: "K1", name: "Priya" }, note: "Top pick", message: { id: "M1", delivery_status: "sent" }, shared_by: { id: "U1", full_name: "Asha" },
  created_at: "2026-10-09T05:00:00Z", can_respond: true, items: [item()], ...over,
});

let page: unknown;
let status: number;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  page = { items: [share()], total: 1, limit: 20, offset: 0 };
  status = 200;
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "PATCH") return Promise.resolve(res(item({ response: "interested", response_label: "Interested", feedback: "Call Monday",
      responded_by: { id: "U1", full_name: "Asha" }, responded_at: "2026-10-09T06:00:00Z" })));
    return Promise.resolve(res(page, status));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RecruiterShares", () => {
  it("lists a requirement's shares with delivery, note and responses", async () => {
    render(<RecruiterShares source={{ kind: "requirement", requirementId: "J1" }} />);
    expect(await screen.findByText(/Email to Priya · 1 profile/)).toBeTruthy();
    expect(screen.getByText("Email Sent")).toBeTruthy();
    expect(screen.getByText("Note: Top pick")).toBeTruthy();
    expect(screen.getByText("Pending")).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/recruiter/requirements/J1/shares?limit=20&offset=0");
  });

  it("records a response and feedback", async () => {
    render(<RecruiterShares source={{ kind: "company", companyId: "CO1" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Record response for Rahul" }));
    const form = screen.getByRole("form", { name: "Response for Rahul" });
    fireEvent.change(within(form).getByLabelText("Company response"), { target: { value: "interested" } });
    fireEvent.change(within(form).getByLabelText(/Recruiter feedback/), { target: { value: "Call Monday" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save response" }));
    expect(await screen.findByText("Response saved for Rahul.")).toBeTruthy();
    expect(screen.getByText("Interested")).toBeTruthy();
    expect(screen.getByText("Feedback: Call Monday")).toBeTruthy();
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH")!;
    expect(patch[0]).toBe("/api/v1/recruiter/shares/S1/items/I1");
    expect(JSON.parse(patch[1].body as string)).toEqual({ response: "interested", feedback: "Call Monday" });
    expect(screen.getByText(/REQ-000001 Java Dev/)).toBeTruthy(); // the company list names the requirement
  });

  it("is read-only without can_respond", async () => {
    page = { items: [share({ can_respond: false })], total: 1, limit: 20, offset: 0 };
    render(<RecruiterShares source={{ kind: "requirement", requirementId: "J1" }} />);
    await screen.findByText(/Email to Priya/);
    expect(screen.queryByRole("button", { name: /Record response/ })).toBeNull();
  });

  it("shows the empty state, and an error with Retry", async () => {
    page = { items: [], total: 0, limit: 20, offset: 0 };
    render(<RecruiterShares source={{ kind: "requirement", requirementId: "J1" }} />);
    expect(await screen.findByText(/No profiles shared yet/)).toBeTruthy();
    cleanup();
    status = 500;
    render(<RecruiterShares source={{ kind: "requirement", requirementId: "J1" }} />);
    expect(await screen.findByText("Unable to load the shared profiles.")).toBeTruthy();
    status = 200;
    page = { items: [share()], total: 1, limit: 20, offset: 0 };
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(/Email to Priya/)).toBeTruthy();
  });
});
