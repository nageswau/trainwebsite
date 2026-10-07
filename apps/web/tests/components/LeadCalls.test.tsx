import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LeadCalls from "@/components/LeadCalls";
import type { LeadCall } from "@/lib/telecallerCalls";
import { call } from "@/tests/helpers/calls";

// tel-010 (spec §5): the calls section of a lead -- the list, Log call with its outcome rules and next follow-up, edit and delete.
const res = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status });
const pageOf = (items: unknown[]) => ({ items, total: items.length, limit: 50, offset: 0 });

let items: LeadCall[];
let postReply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  items = [call(), call({ id: "C2", outcome: "no_answer", outcome_label: "No Answer", connected: false, duration_seconds: 0, remarks: null, can_change: false })];
  postReply = () => res({ call: call({ id: "C3", outcome: "call_back_requested" }), lead: { id: "L1", status: "contacted", status_label: "Contacted" },
    follow_up_id: "F9" }, 201);
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") return Promise.resolve(postReply());
    if (init?.method === "DELETE") return Promise.resolve(res(null, 204));
    if (init?.method === "PATCH") return Promise.resolve(res(call({ remarks: "Edited" })));
    if (url.startsWith("/api/v1/telecaller/leads/L1/calls")) return Promise.resolve(res(pageOf(items)));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const sent = (method: string) => {
  const found = fetchMock.mock.calls.find(([, i]) => i?.method === method);
  return found ? { url: found[0] as string, body: JSON.parse((found[1] as RequestInit).body as string || "null") } : null;
};

describe("LeadCalls (tel-010)", () => {
  it("lists the lead's calls with outcome, duration, caller and remarks; only changeable ones offer actions", async () => {
    render(<LeadCalls leadId="L1" leadStage="contacted" canWrite openSignal={0} onLogged={vi.fn()} />);
    const list = await screen.findByRole("list", { name: "Calls" });
    const [first, second] = within(list).getAllByRole("listitem");
    expect(first.textContent).toContain("Connected – Need Information");
    expect(first.textContent).toContain("4 min 5 s");
    expect(first.textContent).toContain("Tara Caller");
    expect(first.textContent).toContain("Wants the fee sheet");
    expect(within(first).getByRole("button", { name: "Edit" })).toBeTruthy();
    expect(second.textContent).toContain("No Answer");
    expect(within(second).queryByRole("button")).toBeNull();
  });

  it("shows the empty state, and no Log call when the viewer can't write", async () => {
    items = [];
    render(<LeadCalls leadId="L1" leadStage="contacted" canWrite={false} openSignal={0} onLogged={vi.fn()} />);
    expect(await screen.findByText("No calls logged yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Log call" })).toBeNull();
  });

  it("logs a call-back with its required next follow-up and reports the result", async () => {
    const onLogged = vi.fn();
    render(<LeadCalls leadId="L1" leadStage="contacted" canWrite openSignal={0} onLogged={onLogged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Log call" }));
    const form = screen.getByRole("form", { name: "Log call" });
    fireEvent.click(within(form).getByRole("button", { name: "Save call" }));
    expect(await within(form).findByText("Choose an outcome")).toBeTruthy();
    fireEvent.change(within(form).getByLabelText("Outcome (required)"), { target: { value: "call_back_requested" } });
    fireEvent.change(within(form).getByLabelText("Minutes"), { target: { value: "2" } });
    fireEvent.change(within(form).getByLabelText("Seconds"), { target: { value: "30" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save call" }));
    expect(await within(form).findByText("Choose a due date and time")).toBeTruthy(); // D4: required for this outcome
    fireEvent.change(within(form).getByLabelText(/Follow-up due/), { target: { value: "2099-01-02T16:00" } });
    fireEvent.change(within(form).getByLabelText("Follow-up reason"), { target: { value: "fee_details" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save call" }));
    await waitFor(() => expect(onLogged).toHaveBeenCalled());
    const post = sent("POST");
    expect(post?.url).toBe("/api/v1/telecaller/leads/L1/calls");
    expect(post?.body).toMatchObject({ outcome: "call_back_requested", duration_seconds: 150, call_type: "outgoing",
      next_follow_up: { due_at: "2099-01-02T16:00:00+05:30", reason: "fee_details" } });
    expect(post?.body.occurred_at).toMatch(/\+05:30$/);
    expect(onLogged.mock.calls[0][0].follow_up_id).toBe("F9");
    expect(await screen.findByText("Call logged.")).toBeTruthy();
  });

  it("warns that a closing outcome closes the lead and offers no follow-up", async () => {
    render(<LeadCalls leadId="L1" leadStage="contacted" canWrite openSignal={0} onLogged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Log call" }));
    const form = screen.getByRole("form", { name: "Log call" });
    fireEvent.change(within(form).getByLabelText("Outcome (required)"), { target: { value: "already_joined" } });
    expect(within(form).getByText(/closes the lead as Lost/)).toBeTruthy();
    expect(within(form).queryByLabelText("Add a next follow-up")).toBeNull();
  });

  it("places the API's field errors and keeps what was typed", async () => {
    postReply = () => res({ detail: [{ loc: ["body", "occurred_at"], msg: "Value error, The call time can't be in the future", type: "value_error" }] }, 422);
    render(<LeadCalls leadId="L1" leadStage="contacted" canWrite openSignal={0} onLogged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Log call" }));
    const form = screen.getByRole("form", { name: "Log call" });
    fireEvent.change(within(form).getByLabelText("Outcome (required)"), { target: { value: "busy" } });
    fireEvent.change(within(form).getByLabelText("Remarks"), { target: { value: "Line busy twice" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save call" }));
    expect(await within(form).findByText("The call time can't be in the future")).toBeTruthy();
    expect((within(form).getByLabelText("Remarks") as HTMLTextAreaElement).value).toBe("Line busy twice");
  });

  it("opens the form when the page's Call button signals", async () => {
    const { rerender } = render(<LeadCalls leadId="L1" leadStage="contacted" canWrite openSignal={0} onLogged={vi.fn()} />);
    await screen.findByRole("list", { name: "Calls" });
    expect(screen.queryByRole("form", { name: "Log call" })).toBeNull();
    rerender(<LeadCalls leadId="L1" leadStage="contacted" canWrite openSignal={1} onLogged={vi.fn()} />);
    expect(screen.getByRole("form", { name: "Log call" })).toBeTruthy();
  });

  it("edits a call's remarks without offering the outcome", async () => {
    render(<LeadCalls leadId="L1" leadStage="contacted" canWrite openSignal={0} onLogged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const form = screen.getByRole("form", { name: "Edit call" });
    expect(within(form).queryByLabelText("Outcome (required)")).toBeNull();
    fireEvent.change(within(form).getByLabelText("Remarks"), { target: { value: "Edited" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Call updated.")).toBeTruthy();
    expect(sent("PATCH")).toEqual({ url: "/api/v1/telecaller/calls/C1", body: { remarks: "Edited" } });
  });

  it("deletes a call after confirming", async () => {
    render(<LeadCalls leadId="L1" leadStage="contacted" canWrite openSignal={0} onLogged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    expect(await screen.findByText("Call deleted.")).toBeTruthy();
    expect(sent("DELETE")?.url).toBe("/api/v1/telecaller/calls/C1");
  });
});
