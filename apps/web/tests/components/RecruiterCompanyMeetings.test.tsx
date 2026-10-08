import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCompanyMeetings from "@/components/RecruiterCompanyMeetings";
import type { RecMeeting } from "@/lib/recruiterMeetings";
import { recMeeting } from "@/tests/helpers/recruiterMeetings";

// rec-028 (spec §4; MT1-MT7): the company page's meetings -- list, schedule with two contacts, the field-placed 422, reschedule with
// history, the outcome with a next action (AC2), cancel; read only without can_edit. Every change is reported up (stage, follow-ups).
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pageOf = (items: unknown[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const contact = (id: string, name: string, active = true) => ({ id, name, active, is_primary: false });

let items: RecMeeting[];
let postReply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  items = [
    recMeeting(),
    recMeeting({ id: "M2", code: "MTG-000003", meeting_type: "hr_meeting", status: "completed", outcome: "Agreed on terms", next_action: "Send MoU",
      follow_up: { id: "F1", due_at: "2026-10-12T05:30:00Z" }, can_change: false, completed_at: "2026-10-07T09:00:00Z" }),
  ];
  postReply = () => res(recMeeting({ id: "M3", code: "MTG-000009" }), 201);
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST" || init?.method === "PATCH") return Promise.resolve(postReply());
    if (url.startsWith("/api/v1/recruiter/companies/C1/meetings")) return Promise.resolve(res(pageOf(items)));
    if (url === "/api/v1/recruiter/companies/C1/contacts") {
      return Promise.resolve(res({ items: [contact("K1", "Priya HR"), contact("K2", "Ravi Finance"), contact("K9", "Old Contact", false)], can_edit: true }));
    }
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

async function openSchedule() {
  fireEvent.click(await screen.findByRole("button", { name: "Schedule meeting" }));
  const form = screen.getByRole("form", { name: "Schedule meeting" });
  await waitFor(() => expect(within(form).getAllByRole("option", { name: "Priya HR" })).toHaveLength(1));
  return form;
}

describe("RecruiterCompanyMeetings (rec-028)", () => {
  it("lists scheduled and completed meetings with type, mode, contact, link and outcome", async () => {
    render(<RecruiterCompanyMeetings companyId="C1" canWrite onChanged={vi.fn()} />);
    const [scheduled, done] = within(await screen.findByRole("list", { name: "Meetings" })).getAllByRole("listitem");
    expect(scheduled.textContent).toContain("Contract discussion");
    expect(scheduled.textContent).toContain("MTG-000007");
    expect(scheduled.textContent).toContain("Priya HR");
    expect(scheduled.textContent).toContain("IST");
    expect(within(scheduled).getByRole("link", { name: /Meeting link/ }).getAttribute("href")).toBe("https://meet.example.com/abc");
    expect(within(scheduled).queryByRole("button", { name: "Record outcome" })).toBeNull(); // not started yet
    expect(done.textContent).toContain("Agreed on terms");
    expect(done.textContent).toContain("Send MoU");
    expect(within(done).queryByRole("button", { name: "Reschedule / edit" })).toBeNull();
  });

  it("schedules a contract discussion with two contacts (the positive scenario)", async () => {
    const onChanged = vi.fn();
    render(<RecruiterCompanyMeetings companyId="C1" canWrite onChanged={onChanged} />);
    const form = await openSchedule();
    expect(within(form).queryByRole("option", { name: "Old Contact" })).toBeNull(); // inactive contacts are not offered
    expect(within(form).getAllByRole("option").map((o) => o.textContent)).toContain("Placement drive discussion");
    fireEvent.click(within(form).getByRole("button", { name: "Schedule meeting" }));
    expect(within(form).getByText("Choose a meeting type")).toBeTruthy(); // caught before any request
    fireEvent.change(within(form).getByLabelText("Meeting type (required)"), { target: { value: "contract_discussion" } });
    fireEvent.change(within(form).getByLabelText("Date and time (IST, required)"), { target: { value: "2026-12-01T10:30" } });
    fireEvent.change(within(form).getByLabelText("Mode (required)"), { target: { value: "In person" } });
    fireEvent.change(within(form).getByLabelText("Location"), { target: { value: "Pune office" } });
    fireEvent.change(within(form).getByLabelText("Contact"), { target: { value: "K1" } });
    fireEvent.click(within(form).getByRole("checkbox", { name: "Ravi Finance" }));
    fireEvent.click(within(form).getByRole("button", { name: "Schedule meeting" }));
    await screen.findByText("Meeting MTG-000009 scheduled.");
    expect(sent("POST")).toEqual({
      url: "/api/v1/recruiter/companies/C1/meetings",
      body: { meeting_type: "contract_discussion", starts_at: "2026-12-01T10:30:00+05:30", mode: "In person", location: "Pune office", meeting_url: null,
        purpose: null, contact_id: "K1", participant_contact_ids: ["K2"], participant_user_ids: [] },
    });
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("places the server's 422 on the participants", async () => {
    postReply = () => res({ detail: [{ type: "value_error", loc: ["body", "participant_contact_ids"], msg: "Choose an active contact of this company" }] }, 422);
    render(<RecruiterCompanyMeetings companyId="C1" canWrite onChanged={vi.fn()} />);
    const form = await openSchedule();
    fireEvent.change(within(form).getByLabelText("Meeting type (required)"), { target: { value: "hr_meeting" } });
    fireEvent.change(within(form).getByLabelText("Date and time (IST, required)"), { target: { value: "2026-12-01T10:30" } });
    fireEvent.click(within(form).getByRole("button", { name: "Schedule meeting" }));
    expect(await within(form).findByText("Choose an active contact of this company")).toBeTruthy();
  });

  it("reschedules with only the changed time and its reason", async () => {
    postReply = () => res(recMeeting());
    render(<RecruiterCompanyMeetings companyId="C1" canWrite onChanged={vi.fn()} />);
    const [scheduled] = within(await screen.findByRole("list", { name: "Meetings" })).getAllByRole("listitem");
    fireEvent.click(within(scheduled).getByRole("button", { name: "Reschedule / edit" }));
    const form = within(scheduled).getByRole("form", { name: "Edit meeting" });
    fireEvent.change(within(form).getByLabelText("Date and time (IST, required)"), { target: { value: "2026-12-02T09:00" } });
    fireEvent.change(within(form).getByLabelText("Reason for rescheduling"), { target: { value: "Client asked" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save changes" }));
    await screen.findByText("Meeting updated.");
    expect(sent("PATCH")).toEqual({ url: "/api/v1/recruiter/meetings/M1", body: { starts_at: "2026-12-02T09:00:00+05:30", reschedule_reason: "Client asked" } });
  });

  it("records an outcome with a next action that becomes a follow-up (AC2)", async () => {
    items = [recMeeting({ can_record_outcome: true })];
    postReply = () => res(recMeeting({ status: "completed", outcome: "Agreed", can_change: false, follow_up: { id: "F9", due_at: "2026-12-03T04:30:00Z" } }));
    const onChanged = vi.fn();
    render(<RecruiterCompanyMeetings companyId="C1" canWrite onChanged={onChanged} />);
    const [m] = within(await screen.findByRole("list", { name: "Meetings" })).getAllByRole("listitem");
    expect(m.textContent).toContain("Awaiting outcome");
    fireEvent.click(within(m).getByRole("button", { name: "Record outcome" }));
    const form = within(m).getByRole("form", { name: "Record outcome" });
    fireEvent.change(within(form).getByLabelText("Outcome (required)"), { target: { value: "Agreed" } });
    fireEvent.change(within(form).getByLabelText("Next action"), { target: { value: "Send the MoU draft" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save outcome" }));
    expect(within(form).getByText("Choose when the next action is due")).toBeTruthy();
    fireEvent.change(within(form).getByLabelText("Follow-up due (IST, required)"), { target: { value: "2026-12-03T10:00" } });
    fireEvent.change(within(form).getByLabelText("Follow-up reason (required)"), { target: { value: "contract_mou" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save outcome" }));
    await screen.findByText("Outcome saved and follow-up added.");
    expect(sent("POST")).toEqual({
      url: "/api/v1/recruiter/meetings/M1/outcome",
      body: { outcome: "Agreed", next_action: "Send the MoU draft", next_action_due_at: "2026-12-03T10:00:00+05:30", next_action_reason: "contract_mou" },
    });
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("shows the reschedule history", async () => {
    items = [recMeeting({ history: [...recMeeting().history, { event: "rescheduled", old_starts_at: "2026-10-09T05:30:00Z", new_starts_at: "2026-10-10T05:30:00Z",
      reason: "HR on leave", actor: { id: "r1", full_name: "Riya Recruiter" }, created_at: "2026-10-08T06:00:00Z" }] })];
    render(<RecruiterCompanyMeetings companyId="C1" canWrite onChanged={vi.fn()} />);
    const [m] = within(await screen.findByRole("list", { name: "Meetings" })).getAllByRole("listitem");
    expect(m.textContent).toContain("History (2)");
    expect(m.textContent).toContain("HR on leave");
  });

  it("is read only without can_edit (manager, BDM, archived)", async () => {
    items = [recMeeting({ can_change: false })];
    render(<RecruiterCompanyMeetings companyId="C1" canWrite={false} onChanged={vi.fn()} />);
    await screen.findByRole("list", { name: "Meetings" });
    expect(screen.queryByRole("button", { name: "Schedule meeting" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Cancel meeting" })).toBeNull();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/contacts"))).toBe(false);
  });

  it("says when there are none and offers retry on a failed load", async () => {
    items = [];
    render(<RecruiterCompanyMeetings companyId="C1" canWrite onChanged={vi.fn()} />);
    expect(await screen.findByText("No meetings yet.")).toBeTruthy();
    cleanup();
    fetchMock.mockImplementation(() => Promise.resolve(res({}, 500)));
    render(<RecruiterCompanyMeetings companyId="C1" canWrite onChanged={vi.fn()} />);
    expect(await screen.findByText("Unable to load the meetings.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });
});
