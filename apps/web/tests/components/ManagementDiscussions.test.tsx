import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DiscussionAttachments from "@/components/DiscussionAttachments";
import DiscussionForm from "@/components/DiscussionForm";
import ManagementDiscussions from "@/components/ManagementDiscussions";
import MyManagementDecisions from "@/components/MyManagementDecisions";
import type { Discussion, DiscussionDetail, DiscussionOptions, MyDecision } from "@/lib/managementDiscussions";

const router = { replace: vi.fn(), refresh: vi.fn(), push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router, redirect: vi.fn(), usePathname: () => "/management/discussions" }));

const BDM = { id: "u2", full_name: "Uma BDM", role: "partnership_manager" };
const PARTNER = { id: "u1", full_name: "Arjun Partner", role: "partner" };
const options: DiscussionOptions = { users: [PARTNER, BDM] };

function discussion(overrides: Partial<Discussion> = {}): Discussion {
  return {
    id: "d1", topic: "Japan University Partnership", discussion_date: "2026-10-01", department: "Partnerships", decision: "Proceed with agreement",
    responsible: BDM, deadline: "2026-10-10", status: "in_progress", follow_up_date: null, meeting_id: null, created_at: "2026-10-01T04:30:00Z", updated_at: "2026-10-01T04:30:00Z",
    ...overrides,
  };
}
function detail(overrides: Partial<DiscussionDetail> = {}): DiscussionDetail {
  return { ...discussion(), points: "Terms discussed", participants: [PARTNER], attachments: [], created_by: PARTNER, updated_by: PARTNER, ...overrides };
}

type Call = { url: string; method: string; body: unknown };
let calls: Call[];
function respond(...answers: { status?: number; body?: unknown }[]) {
  const queue = [...answers];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url, method: init.method ?? "GET", body: init.body instanceof FormData ? init.body : init.body ? JSON.parse(String(init.body)) : undefined });
    const answer = queue.shift() ?? { body: { id: "d9" } };
    return new Response(answer.status === 204 ? null : JSON.stringify(answer.body ?? {}), { status: answer.status ?? 200, headers: { "Content-Type": "application/json" } });
  }));
}

beforeEach(() => {
  calls = [];
  router.push.mockReset();
  router.refresh.mockReset();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("mgmt-027 discussions list", () => {
  it("shows the pending decisions panel by deadline, overdue flagged, and the list rows", () => {
    const pending = [discussion({ id: "d2", deadline: "2026-10-05", decision: "Sign the MoU" }), discussion()];
    render(<ManagementDiscussions data={{ items: [discussion()], total: 1, limit: 25, offset: 0 }} pending={pending} error="" filters={{ status: "", offset: 0 }} today="2026-10-08" />);
    const panel = screen.getByRole("region", { name: "Pending decisions" });
    const items = within(panel).getAllByRole("listitem");
    expect(items[0].textContent).toContain("Sign the MoU");
    expect(items[0].textContent).toContain("Overdue");
    expect(items[1].textContent).not.toContain("Overdue");
    expect(screen.getByRole("link", { name: "Japan University Partnership" }).getAttribute("href")).toBe("/management/discussions/d1");
  });

  it("says when there is nothing pending and nothing listed", () => {
    render(<ManagementDiscussions data={{ items: [], total: 0, limit: 25, offset: 0 }} pending={[]} error="" filters={{ status: "open", offset: 0 }} today="2026-10-08" />);
    expect(screen.getByText("No pending decisions.")).toBeTruthy();
    expect(screen.getByText("No discussions match this filter.")).toBeTruthy();
  });

  it("keeps the filter usable when the read failed", () => {
    render(<ManagementDiscussions data={null} pending={[]} error="Discussions are unavailable right now. Please try again." filters={{ status: "", offset: 0 }} today="2026-10-08" />);
    expect(screen.getByRole("alert").textContent).toContain("unavailable");
    expect(screen.getByRole("combobox", { name: "Status" })).toBeTruthy();
  });
});

describe("mgmt-027 discussion form", () => {
  it("records the Japan example and opens it", async () => {
    respond({ status: 201, body: { id: "d9" } });
    render(<DiscussionForm options={options} today="2026-10-08" />);
    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "Japan University Partnership" } });
    fireEvent.change(screen.getByLabelText("Decision (optional)"), { target: { value: "Proceed with agreement" } });
    fireEvent.change(screen.getByLabelText("Person responsible (optional)"), { target: { value: "u2" } });
    fireEvent.change(screen.getByLabelText("Deadline (optional)"), { target: { value: "2026-10-10" } });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "in_progress" } });
    fireEvent.click(screen.getByLabelText("Arjun Partner (Partner)"));
    fireEvent.click(screen.getByRole("button", { name: "Save discussion" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/management/discussions/d9"));
    expect(calls[0]).toMatchObject({ url: "/api/v1/management/discussions", method: "POST" });
    expect(calls[0].body).toMatchObject({
      topic: "Japan University Partnership", discussion_date: "2026-10-08", decision: "Proceed with agreement", responsible_user_id: "u2",
      deadline: "2026-10-10", status: "in_progress", participant_ids: ["u1"], department: null, points: null, follow_up_date: null,
    });
  });

  it("checks fields before sending and places the API's field errors", async () => {
    render(<DiscussionForm options={options} today="2026-10-08" />);
    fireEvent.change(screen.getByLabelText("Person responsible (optional)"), { target: { value: "u2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save discussion" }));
    expect(await screen.findByText("Give the topic (2-200 characters)")).toBeTruthy();
    expect(screen.getByText("Record the decision before naming a responsible person")).toBeTruthy();
    respond({ status: 422, body: { detail: [{ loc: ["body", "responsible_user_id"], msg: "Value error, Choose an active staff member", type: "value_error" }] } });
    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "Weekly sync" } });
    fireEvent.change(screen.getByLabelText("Decision (optional)"), { target: { value: "Go" } });
    fireEvent.click(screen.getByRole("button", { name: "Save discussion" }));
    expect(await screen.findByText("Choose an active staff member")).toBeTruthy();
    expect(router.push).not.toHaveBeenCalled();
  });

  it("QA-01: a double click saves once", async () => {
    respond({ status: 201, body: { id: "d9" } });
    render(<DiscussionForm options={options} today="2026-10-08" />);
    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "Weekly sync" } });
    const save = screen.getByRole("button", { name: "Save discussion" });
    fireEvent.click(save);
    fireEvent.click(save);
    await waitFor(() => expect(router.push).toHaveBeenCalled());
    expect(calls).toHaveLength(1);
  });

  it("QA-02: a field's error clears once the field is changed", () => {
    render(<DiscussionForm options={options} today="2026-10-08" />);
    fireEvent.click(screen.getByRole("button", { name: "Save discussion" }));
    expect(screen.getByText("Give the topic (2-200 characters)")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "Weekly sync" } });
    expect(screen.queryByText("Give the topic (2-200 characters)")).toBeNull();
  });

  it("sends only what changed when editing", async () => {
    respond({ body: { id: "d1" } });
    render(<DiscussionForm options={options} today="2026-10-08" discussion={detail()} />);
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "completed" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/management/discussions/d1"));
    expect(calls[0]).toMatchObject({ url: "/api/v1/management/discussions/d1", method: "PATCH", body: { status: "completed" } });
  });
});

describe("mgmt-027 attachments", () => {
  it("uploads a shareable file and removes one after confirming", async () => {
    respond({ status: 201, body: {} }, { status: 204 });
    const attached = detail({ attachments: [{ id: "a1", name: "terms.pdf", content_type: "application/pdf", shareable: true, created_at: "2026-10-01T04:30:00Z" }] });
    render(<DiscussionAttachments discussion={attached} />);
    expect(screen.getByRole("link", { name: /terms\.pdf/ }).getAttribute("href")).toBe("/api/v1/management/discussions/d1/attachments/a1");
    expect(screen.getByText(/· Shared with the responsible person/)).toBeTruthy();
    const file = new File(["%PDF-1.4"], "minutes.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("Add a file"), { target: { files: [file] } });
    fireEvent.click(screen.getByLabelText("Share with the responsible person"));
    const upload = screen.getByRole("button", { name: "Upload" });
    fireEvent.click(upload);
    fireEvent.click(upload); // QA-01: one upload
    await waitFor(() => expect(screen.getByText("File attached.")).toBeTruthy());
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("/api/v1/management/discussions/d1/attachments");
    expect((calls[0].body as FormData).get("shareable")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Remove terms.pdf" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm removal" }));
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1]).toMatchObject({ url: "/api/v1/management/discussions/d1/attachments/a1", method: "DELETE" });
  });
});

describe("mgmt-027 my management decisions", () => {
  const mine: MyDecision = { id: "d1", decision: "Proceed with agreement", deadline: "2026-10-10", status: "in_progress", attachments: [{ id: "a1", name: "terms.pdf", content_type: "application/pdf" }], updated_at: "2026-10-01T04:30:00Z" };

  it("shows only the decision line and updates its status", async () => {
    respond({ body: { ...mine, status: "completed" } });
    render(<MyManagementDecisions items={[mine]} today="2026-10-08" />);
    expect(screen.getByText("Proceed with agreement — 10 Oct 2026 — In Progress")).toBeTruthy();
    expect(screen.getByRole("link", { name: /terms\.pdf/ }).getAttribute("href")).toBe("/api/v1/me/management-decisions/d1/attachments/a1");
    fireEvent.change(screen.getByLabelText("Status of “Proceed with agreement”"), { target: { value: "completed" } });
    fireEvent.click(screen.getByRole("button", { name: "Update status" }));
    expect(await screen.findByText("Status updated.")).toBeTruthy();
    expect(calls[0]).toMatchObject({ url: "/api/v1/me/management-decisions/d1", method: "PATCH", body: { status: "completed" } });
    expect(router.refresh).toHaveBeenCalled();
  });

  it("says when nothing is assigned", () => {
    render(<MyManagementDecisions items={[]} today="2026-10-08" />);
    expect(screen.getByText("No management decisions are assigned to you.")).toBeTruthy();
  });
});
