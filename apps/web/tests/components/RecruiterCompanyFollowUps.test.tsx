import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCompanyFollowUps from "@/components/RecruiterCompanyFollowUps";
import type { RecFollowUp } from "@/lib/recruiterFollowUps";
import { recFollowUp } from "@/tests/helpers/recruiterFollowUps";

// rec-024 (spec §4; FU3, FU5, FU6): the company page's follow-ups -- list, add (with a contact), reschedule, cancel; read only without
// can_edit. Every change is reported up so the company's "Next follow-up" re-reads.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pageOf = (items: unknown[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const contact = (id: string, name: string, active = true) => ({ id, name, active, is_primary: false });

let items: RecFollowUp[];
let postReply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  items = [recFollowUp(), recFollowUp({ id: "F2", status: "done", completed_at: "2026-10-07T09:00:00Z", completed_by: { id: "r1", full_name: "Riya Recruiter" },
    outcome: "JD received", can_change: false, reason: "new_requirement" })];
  postReply = () => res(recFollowUp({ id: "F3" }), 201);
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST" || init?.method === "PATCH") return Promise.resolve(postReply());
    if (url.startsWith("/api/v1/recruiter/companies/C1/follow-ups")) return Promise.resolve(res(pageOf(items)));
    if (url === "/api/v1/recruiter/companies/C1/contacts") return Promise.resolve(res({ items: [contact("K1", "Priya HR"), contact("K2", "Old Contact", false)], can_edit: true }));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const sent = (method: string) => {
  const call = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === method)!;
  return { url: String(call[0]), body: JSON.parse(String((call[1] as RequestInit).body)) };
};

describe("RecruiterCompanyFollowUps (rec-024)", () => {
  it("lists open and closed follow-ups with reason, due time, contact and outcome", async () => {
    render(<RecruiterCompanyFollowUps companyId="C1" canWrite onChanged={vi.fn()} />);
    const [open, done] = within(await screen.findByRole("list", { name: "Follow-ups" })).getAllByRole("listitem");
    expect(open.textContent).toContain("Follow-up for JD");
    expect(open.textContent).toContain("Priya HR");
    expect(open.textContent).toContain("IST");
    expect(done.textContent).toContain("Done");
    expect(done.textContent).toContain("JD received");
    expect(within(done).queryByRole("button", { name: "Reschedule" })).toBeNull();
  });

  it("adds a follow-up with a reason, an IST due time and an active contact", async () => {
    const onChanged = vi.fn();
    render(<RecruiterCompanyFollowUps companyId="C1" canWrite onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add follow-up" }));
    const form = screen.getByRole("form", { name: "Add follow-up" });
    await waitFor(() => expect(within(form).getAllByRole("option", { name: "Priya HR" })).toHaveLength(1));
    expect(within(form).queryByRole("option", { name: "Old Contact" })).toBeNull(); // inactive contacts are not offered
    expect(within(form).getAllByRole("option").map((o) => o.textContent)).toContain("Payment/commercial discussion");
    fireEvent.click(within(form).getByRole("button", { name: "Add follow-up" }));
    expect(within(form).getByText("Choose a due date and time")).toBeTruthy(); // caught before any request
    fireEvent.change(within(form).getByLabelText("Due date and time (IST, required)"), { target: { value: "2026-12-01T10:30" } });
    fireEvent.change(within(form).getByLabelText("Reason (required)"), { target: { value: "jd" } });
    fireEvent.change(within(form).getByLabelText("Contact"), { target: { value: "K1" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add follow-up" }));
    await screen.findByText("Follow-up added.");
    expect(sent("POST")).toEqual({
      url: "/api/v1/recruiter/companies/C1/follow-ups",
      body: { due_at: "2026-12-01T10:30:00+05:30", reason: "jd", notes: null, contact_id: "K1" },
    });
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("places the server's 422 on the due field", async () => {
    postReply = () => res({ detail: [{ type: "value_error", loc: ["body", "due_at"], msg: "Choose a due time in the future" }] }, 422);
    render(<RecruiterCompanyFollowUps companyId="C1" canWrite onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add follow-up" }));
    const form = screen.getByRole("form", { name: "Add follow-up" });
    fireEvent.change(within(form).getByLabelText("Due date and time (IST, required)"), { target: { value: "2026-12-01T10:30" } });
    fireEvent.change(within(form).getByLabelText("Reason (required)"), { target: { value: "jd" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add follow-up" }));
    expect(await within(form).findByText("Choose a due time in the future")).toBeTruthy();
  });

  it("reschedules with only the changed field", async () => {
    postReply = () => res(recFollowUp());
    render(<RecruiterCompanyFollowUps companyId="C1" canWrite onChanged={vi.fn()} />);
    const [open] = within(await screen.findByRole("list", { name: "Follow-ups" })).getAllByRole("listitem");
    fireEvent.click(within(open).getByRole("button", { name: "Reschedule" }));
    const form = within(open).getByRole("form", { name: "Reschedule follow-up" });
    fireEvent.change(within(form).getByLabelText("Due date and time (IST, required)"), { target: { value: "2026-12-02T09:00" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save changes" }));
    await screen.findByText("Follow-up updated.");
    expect(sent("PATCH")).toEqual({ url: "/api/v1/recruiter/follow-ups/F1", body: { due_at: "2026-12-02T09:00:00+05:30" } });
  });

  it("is read only without can_edit (manager, BDM, archived)", async () => {
    items = [recFollowUp({ can_change: false })];
    render(<RecruiterCompanyFollowUps companyId="C1" canWrite={false} onChanged={vi.fn()} />);
    await screen.findByRole("list", { name: "Follow-ups" });
    expect(screen.queryByRole("button", { name: "Add follow-up" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Done" })).toBeNull();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/contacts"))).toBe(false);
  });

  it("says when there are none", async () => {
    items = [];
    render(<RecruiterCompanyFollowUps companyId="C1" canWrite onChanged={vi.fn()} />);
    expect(await screen.findByText("No follow-ups yet.")).toBeTruthy();
  });
});
