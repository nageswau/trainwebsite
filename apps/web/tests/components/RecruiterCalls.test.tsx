import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCalls from "@/components/RecruiterCalls";
import type { RecCall } from "@/lib/recruiterCalls";

// rec-025 (spec §4; CA2-CA8): the Calls section on the company and candidate pages -- loading/empty/error states, log a contact call with
// a next follow-up, a candidate call (no follow-up offered), same-day edit/delete only when `can_change`, server field errors on fields.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pageOf = (items: unknown[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const call = (over: Partial<RecCall> = {}): RecCall => ({
  id: "L1", kind: "contact", company_id: "C1", contact: { id: "K1", name: "Priya HR" }, candidate: null, occurred_at: "2026-10-08T05:30:00Z",
  duration_seconds: 185, direction: "outgoing", outcome: "connected", outcome_label: "Connected", connected: true, notes: "Discussed the JD",
  caller: { id: "r1", full_name: "Riya Recruiter" }, created_at: "2026-10-08T05:31:00Z", can_change: true, ...over,
});

let items: RecCall[];
let listReply: () => Promise<Response>;
let postReply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  items = [call(), call({ id: "L2", outcome: "no_answer", outcome_label: "No answer", connected: false, notes: null, duration_seconds: null, can_change: false })];
  listReply = () => Promise.resolve(res(pageOf(items)));
  postReply = () => res({ call: call({ id: "L3" }), follow_up_id: "F1" }, 201);
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST" || init?.method === "PATCH") return Promise.resolve(postReply());
    if (init?.method === "DELETE") return Promise.resolve(new Response(null, { status: 204 }));
    if (url.includes("/calls")) return listReply();
    if (url === "/api/v1/recruiter/companies/C1/contacts")
      return Promise.resolve(res({ items: [{ id: "K1", name: "Priya HR", active: true }, { id: "K2", name: "Old Contact", active: false }], can_edit: true }));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const sent = (method: string) => {
  const found = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === method)!;
  return { url: String(found[0]), body: JSON.parse(String((found[1] as RequestInit).body)) };
};
const contactParty = { kind: "contact", companyId: "C1" } as const;

describe("RecruiterCalls (rec-025)", () => {
  it("lists calls with outcome, contact, duration, direction and notes; Edit/Delete only when can_change", async () => {
    render(<RecruiterCalls party={contactParty} canWrite />);
    expect(screen.getByText("Loading calls…")).toBeTruthy();
    const [first, second] = within(await screen.findByRole("list", { name: "Calls" })).getAllByRole("listitem");
    expect(first.textContent).toContain("Connected");
    expect(first.textContent).toContain("Priya HR");
    expect(first.textContent).toContain("3 min 5 s");
    expect(first.textContent).toContain("Outgoing");
    expect(first.textContent).toContain("Discussed the JD");
    expect(within(first).getByRole("button", { name: /Edit/ })).toBeTruthy();
    expect(second.textContent).toContain("Not connected");
    expect(within(second).queryByRole("button", { name: /Edit/ })).toBeNull();
  });

  it("shows the empty state and the error state with Retry", async () => {
    items = [];
    const { unmount } = render(<RecruiterCalls party={contactParty} canWrite={false} />);
    expect(await screen.findByText("No calls logged yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Log call" })).toBeNull(); // readers never get the form
    unmount();
    listReply = () => Promise.reject(new Error("offline"));
    render(<RecruiterCalls party={contactParty} canWrite />);
    expect(await screen.findByText("Unable to load the calls.")).toBeTruthy();
    listReply = () => Promise.resolve(res(pageOf(items)));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No calls logged yet.")).toBeTruthy();
  });

  it("logs a contact call with a next follow-up and reports it up", async () => {
    const onChanged = vi.fn();
    render(<RecruiterCalls party={contactParty} canWrite onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Log call" }));
    const form = screen.getByRole("form", { name: "Log call" });
    await waitFor(() => expect(within(form).getAllByRole("option", { name: "Priya HR" })).toHaveLength(1));
    expect(within(form).queryByRole("option", { name: "Old Contact" })).toBeNull();
    fireEvent.click(within(form).getByRole("button", { name: "Save call" }));
    expect(within(form).getByText("Choose a contact")).toBeTruthy(); // caught before any request
    expect(within(form).getByText("Choose an outcome")).toBeTruthy();
    fireEvent.change(within(form).getByLabelText("Contact (required)"), { target: { value: "K1" } });
    fireEvent.change(within(form).getByLabelText("Outcome (required)"), { target: { value: "call_back_requested" } });
    fireEvent.change(within(form).getByLabelText("Minutes"), { target: { value: "2" } });
    fireEvent.change(within(form).getByLabelText("Notes"), { target: { value: "  Call back after 4 PM  " } });
    fireEvent.click(within(form).getByLabelText("Add a next follow-up"));
    fireEvent.change(within(form).getByLabelText("Follow-up due (IST, required)"), { target: { value: "2099-01-02T10:30" } });
    fireEvent.change(within(form).getByLabelText("Follow-up reason (required)"), { target: { value: "jd" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save call" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    const { url, body } = sent("POST");
    expect(url).toBe("/api/v1/recruiter/calls");
    expect(body).toMatchObject({ contact_id: "K1", outcome: "call_back_requested", direction: "outgoing", duration_seconds: 120, notes: "Call back after 4 PM" });
    expect(body.next_follow_up).toEqual({ due_at: "2099-01-02T10:30:00+05:30", reason: "jd", notes: null });
    expect(await screen.findByText("Call logged. Follow-up added.")).toBeTruthy();
  });

  it("logs a candidate call without offering a follow-up or a contact", async () => {
    render(<RecruiterCalls party={{ kind: "candidate", candidateId: "D1" }} canWrite />);
    fireEvent.click(await screen.findByRole("button", { name: "Log call" }));
    const form = screen.getByRole("form", { name: "Log call" });
    expect(within(form).queryByLabelText("Contact (required)")).toBeNull();
    expect(within(form).queryByLabelText("Add a next follow-up")).toBeNull();
    fireEvent.change(within(form).getByLabelText("Outcome (required)"), { target: { value: "busy" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save call" }));
    await waitFor(() => expect(sent("POST").body).toMatchObject({ candidate_id: "D1", outcome: "busy", duration_seconds: null }));
    expect(sent("POST").body.next_follow_up).toBeNull();
  });

  it("places the server's field errors on their fields and keeps typed text", async () => {
    postReply = () => res({ detail: [{ loc: ["body", "occurred_at"], msg: "The call time can't be in the future" }] }, 422);
    render(<RecruiterCalls party={{ kind: "candidate", candidateId: "D1" }} canWrite />);
    fireEvent.click(await screen.findByRole("button", { name: "Log call" }));
    const form = screen.getByRole("form", { name: "Log call" });
    fireEvent.change(within(form).getByLabelText("Outcome (required)"), { target: { value: "busy" } });
    fireEvent.change(within(form).getByLabelText("Notes"), { target: { value: "keep me" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save call" }));
    expect(await within(form).findByText("The call time can't be in the future")).toBeTruthy();
    expect((within(form).getByLabelText("Notes") as HTMLTextAreaElement).value).toBe("keep me");
  });

  it("edits only what changed and deletes after a confirm", async () => {
    postReply = () => res(call({ notes: "Updated" }));
    render(<RecruiterCalls party={contactParty} canWrite />);
    const [first] = within(await screen.findByRole("list", { name: "Calls" })).getAllByRole("listitem");
    fireEvent.click(within(first).getByRole("button", { name: /Edit/ }));
    const form = within(first).getByRole("form", { name: "Edit call" });
    expect(within(form).queryByLabelText("Outcome (required)")).toBeNull(); // CA4: the outcome is locked
    fireEvent.change(within(form).getByLabelText("Notes"), { target: { value: "Updated" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(sent("PATCH")).toEqual({ url: "/api/v1/recruiter/calls/L1", body: { notes: "Updated" } }));
    expect(await screen.findByText("Call updated.")).toBeTruthy();
    const [again] = within(await screen.findByRole("list", { name: "Calls" })).getAllByRole("listitem");
    fireEvent.click(within(again).getByRole("button", { name: /Delete/ }));
    fireEvent.click(within(again).getByRole("button", { name: "Yes, delete" }));
    expect(await screen.findByText("Call deleted.")).toBeTruthy();
    expect(fetchMock.mock.calls.some(([u, i]) => u === "/api/v1/recruiter/calls/L1" && (i as RequestInit)?.method === "DELETE")).toBe(true);
  });
});
