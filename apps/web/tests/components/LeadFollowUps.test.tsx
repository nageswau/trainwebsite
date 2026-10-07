import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LeadFollowUps from "@/components/LeadFollowUps";
import type { FollowUp } from "@/lib/telecallerFollowUps";
import { followUp } from "@/tests/helpers/followUps";

// tel-011 (spec §4, F2/F4): the follow-ups section of a lead -- the list, add, done, cancel; read only for a manager or a handed-over lead.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pageOf = (items: unknown[]) => ({ items, total: items.length, limit: 50, offset: 0 });

let items: FollowUp[];
let listReply: () => Response;
let postReply: (url: string) => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  items = [followUp(), followUp({ id: "F2", status: "done", completed_at: "2026-10-05T09:00:00Z", completed_by: { id: "t1", full_name: "Tara Caller" },
    can_change: false, reason: "course_details", next_action: null, notes: null })];
  listReply = () => res(pageOf(items));
  postReply = (url) => res(followUp(url.endsWith("/complete") ? { status: "done", can_change: false, completed_at: "2026-10-06T09:00:00Z",
    completed_by: { id: "t1", full_name: "Tara Caller" } } : { status: "cancelled", can_change: false, cancelled_at: "2026-10-06T09:00:00Z", cancel_reason: "Joined elsewhere" }));
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") return Promise.resolve(postReply(url));
    if (url.startsWith("/api/v1/telecaller/leads/L1/follow-ups")) return Promise.resolve(listReply());
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LeadFollowUps (tel-011)", () => {
  it("lists the lead's follow-ups with reason, time, next action and state", async () => {
    render(<LeadFollowUps leadId="L1" leadStage="contacted" canWrite onStageChanged={vi.fn()} />);
    const list = await screen.findByRole("list", { name: "Follow-ups" });
    const [open, done] = within(list).getAllByRole("listitem");
    expect(open.textContent).toContain("Need fee details");
    expect(open.textContent).toContain("Call at 4 PM");
    expect(open.textContent).toContain("Send the fee sheet");
    expect(open.textContent).toContain("IST");
    expect(done.textContent).toContain("Need course details");
    expect(done.textContent).toContain("Done");
    expect(within(done).queryByRole("button")).toBeNull();
  });

  it("marks an overdue follow-up", async () => {
    items = [followUp({ overdue: true })];
    render(<LeadFollowUps leadId="L1" leadStage="contacted" canWrite onStageChanged={vi.fn()} />);
    expect(await screen.findByText("Overdue")).toBeTruthy();
  });

  it("marks one done and cancels another with a reason", async () => {
    render(<LeadFollowUps leadId="L1" leadStage="contacted" canWrite onStageChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Done" }));
    expect(await screen.findByText("Marked done.")).toBeTruthy();
    expect(fetchMock.mock.calls.some(([u, i]) => u === "/api/v1/telecaller/follow-ups/F1/complete" && i?.method === "POST")).toBe(true);
  });

  it("cancels with a reason", async () => {
    render(<LeadFollowUps leadId="L1" leadStage="contacted" canWrite onStageChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel follow-up" }));
    fireEvent.change(screen.getByLabelText("Reason (required)"), { target: { value: "Joined elsewhere" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel it" }));
    await waitFor(() => expect(screen.getByText("Follow-up cancelled.")).toBeTruthy());
    const [, init] = fetchMock.mock.calls.find(([u]) => u === "/api/v1/telecaller/follow-ups/F1/cancel")!;
    expect(JSON.parse(String(init.body))).toEqual({ reason: "Joined elsewhere" });
  });

  it("adds a follow-up and reports a stage move", async () => {
    const onStageChanged = vi.fn();
    const onChanged = vi.fn(); // tel-015: the page's timeline re-reads
    postReply = () => res(followUp({ id: "F3", lead: { ...followUp().lead, status: "follow_up", status_label: "Follow-up" } }), 201);
    render(<LeadFollowUps leadId="L1" leadStage="contacted" canWrite onStageChanged={onStageChanged} onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add follow-up" }));
    fireEvent.change(screen.getByLabelText(/Due date and time/), { target: { value: "2026-10-08T16:00" } });
    fireEvent.change(screen.getByLabelText("Reason (required)"), { target: { value: "fee_details" } });
    fireEvent.click(within(screen.getByRole("form", { name: "Add follow-up" })).getByRole("button", { name: "Add follow-up" }));
    await waitFor(() => expect(onStageChanged).toHaveBeenCalledWith("follow_up"));
    expect(screen.getByText("Follow-up added.")).toBeTruthy();
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("is read only without write access (the API's can_change is false too)", async () => {
    items = items.map((fu) => ({ ...fu, can_change: false }));
    render(<LeadFollowUps leadId="L1" leadStage="contacted" canWrite={false} onStageChanged={vi.fn()} />);
    await screen.findByRole("list", { name: "Follow-ups" });
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("says when there are none, and when the list fails offers a retry", async () => {
    items = [];
    render(<LeadFollowUps leadId="L1" leadStage="contacted" canWrite onStageChanged={vi.fn()} />);
    expect(await screen.findByText("No follow-ups yet.")).toBeTruthy();
    cleanup();
    listReply = () => res({}, 500);
    render(<LeadFollowUps leadId="L1" leadStage="contacted" canWrite onStageChanged={vi.fn()} />);
    expect((await screen.findByRole("alert")).textContent).toContain("Unable to load the follow-ups");
    listReply = () => res(pageOf([]));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No follow-ups yet.")).toBeTruthy();
  });
});
