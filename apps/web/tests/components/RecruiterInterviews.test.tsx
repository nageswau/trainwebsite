import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterApplicationInterviews from "@/components/RecruiterApplicationInterviews";
import RecruiterInterviewsPanel from "@/components/RecruiterInterviewsPanel";
import type { RecInterview } from "@/lib/recruiterInterviews";
import { recInterview } from "@/tests/helpers/recruiterInterviews";

// rec-020 (spec §4; IV3-IV5, IV9, IV12; AC1, AC2): an application's interviews (schedule, the moves the API allows, reschedule with
// history, a refusal in the server's words, read-only) and the interviews list (tabs with counts, the Upcoming day grouping, retry).
let search = "";
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push }),
  usePathname: () => "/recruiter/interviews",
  useSearchParams: () => new URLSearchParams(search),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
let items: RecInterview[];
let canSchedule: boolean;
let writeReply: () => Response;
let listReply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  search = "";
  push.mockReset();
  items = [recInterview()];
  canSchedule = true;
  writeReply = () => res({ interview: recInterview({ id: "I2", code: "INT-000002" }), notifications: { candidate: "queued", contact: null } }, 201);
  listReply = () => res({ items: [recInterview(), recInterview({ id: "I3", code: "INT-000003", scheduled_at: "2026-10-13T05:30:00Z" })], total: 2, limit: 50, offset: 0,
    counts: { upcoming: 2, awaiting_update: 1, on_hold: 0, closed: 4 } });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method) return Promise.resolve(writeReply());
    if (url.endsWith("/applications/A1/interviews")) return Promise.resolve(res({ items, can_schedule: canSchedule }));
    if (url.startsWith("/api/v1/recruiter/interviews?")) return Promise.resolve(listReply());
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const writes = () => fetchMock.mock.calls.filter(([, init]) => init?.method).map(([url, init]) => [url, init.method, JSON.parse(init.body)]);
const section = (onChanged = vi.fn()) => render(<RecruiterApplicationInterviews applicationId="A1" candidateName="Rahul Kumar" contacts={[{ id: "K1", name: "Priya HR" }]} onChanged={onChanged} />);

describe("RecruiterApplicationInterviews", () => {
  it("lists the interviews with their details and history", async () => {
    section();
    expect(screen.getByText("Loading interviews…")).toBeTruthy();
    const card = within(await screen.findByRole("list", { name: "Interviews of Rahul Kumar" })).getAllByRole("listitem")[0];
    for (const text of ["HR Round", "INT-000001", "Scheduled", "Online", "Meera (HR)"]) expect(card.textContent).toContain(text);
    expect(within(card).getByRole("link", { name: /Meeting link/ }).getAttribute("href")).toBe("https://meet.example.com/abc");
    expect(card.textContent).toContain("History (1)");
  });

  it("schedules an interview (round, IST time, contact, notify) and reports the notices", async () => {
    items = [];
    const onChanged = vi.fn();
    section(onChanged);
    expect(await screen.findByText("No interviews yet.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Schedule interview/ }));
    const form = screen.getByRole("form", { name: "Schedule interview" });
    fireEvent.click(within(form).getByRole("button", { name: "Schedule interview" }));
    expect(within(form).getByText("Choose a round")).toBeTruthy();
    expect(within(form).getByText("Choose a date and time")).toBeTruthy();
    fireEvent.change(within(form).getByLabelText("Round (required)"), { target: { value: "technical_round" } });
    fireEvent.change(within(form).getByLabelText("Date and time (IST, required)"), { target: { value: "2030-01-15T11:00" } });
    fireEvent.change(within(form).getByLabelText("Company contact"), { target: { value: "K1" } });
    expect(within(form).getByLabelText("Notify the candidate and the contact")).toBeTruthy();
    fireEvent.click(within(form).getByRole("button", { name: "Schedule interview" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("HR Round scheduled for Rahul Kumar. Candidate: email queued."));
    const [[url, method, body]] = writes();
    expect([url, method]).toEqual(["/api/v1/recruiter/interviews", "POST"]);
    expect(body).toEqual({ application_id: "A1", scheduled_at: "2030-01-15T11:00:00+05:30", notify: true, round: "technical_round", mode: "Online",
      meeting_url: null, interviewer: null, location: null, contact_id: "K1" });
  });

  it("sends one request when Schedule is clicked twice in a row (QA-01)", async () => {
    items = [];
    section();
    fireEvent.click(await screen.findByRole("button", { name: /Schedule interview/ }));
    const form = screen.getByRole("form", { name: "Schedule interview" });
    fireEvent.change(within(form).getByLabelText("Round (required)"), { target: { value: "hr_round" } });
    fireEvent.change(within(form).getByLabelText("Date and time (IST, required)"), { target: { value: "2030-01-15T11:00" } });
    const submit = within(form).getByRole("button", { name: "Schedule interview" });
    act(() => { submit.click(); submit.click(); }); // one task, as a fast double click: the second runs before React re-renders
    await waitFor(() => expect(writes()).toHaveLength(1));
  });

  it("sends one request when Save status is clicked twice in a row (QA-01)", async () => {
    section();
    fireEvent.click(await screen.findByRole("button", { name: /Change status/ }));
    const form = screen.getByRole("form", { name: "Change status of INT-000001" });
    fireEvent.change(within(form).getByLabelText("New status (required)"), { target: { value: "confirmed" } });
    const submit = within(form).getByRole("button", { name: "Save status" });
    act(() => { submit.click(); submit.click(); }); // one task, as a fast double click: the second runs before React re-renders
    await waitFor(() => expect(writes()).toHaveLength(1));
  });

  it("keeps the server's clash refusal on the form", async () => {
    items = [];
    writeReply = () => res({ detail: "This candidate already has an interview scheduled at this time" }, 409);
    section();
    fireEvent.click(await screen.findByRole("button", { name: /Schedule interview/ }));
    const form = screen.getByRole("form", { name: "Schedule interview" });
    fireEvent.change(within(form).getByLabelText("Round (required)"), { target: { value: "hr_round" } });
    fireEvent.change(within(form).getByLabelText("Date and time (IST, required)"), { target: { value: "2030-01-15T11:00" } });
    fireEvent.click(within(form).getByRole("button", { name: "Schedule interview" }));
    expect((await within(form).findByRole("alert")).textContent).toContain("already has an interview");
  });

  it("offers only the moves the API allows and posts the status with its note", async () => {
    const onChanged = vi.fn();
    section(onChanged);
    fireEvent.click(await screen.findByRole("button", { name: /Change status/ }));
    const form = screen.getByRole("form", { name: "Change status of INT-000001" });
    const options = within(form).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Choose a status", "Confirmed", "On Hold"]);
    fireEvent.change(within(form).getByLabelText("New status (required)"), { target: { value: "confirmed" } });
    fireEvent.change(within(form).getByLabelText("Note (optional)"), { target: { value: "Candidate replied" } });
    writeReply = () => res({ interview: recInterview({ status: "confirmed", status_label: "Confirmed" }) });
    fireEvent.click(within(form).getByRole("button", { name: "Save status" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Status saved."));
    expect(writes()[0]).toEqual(["/api/v1/recruiter/interviews/I1/status", "POST", { status: "confirmed", note: "Candidate replied" }]);
  });

  it("shows AC2's 'not yet' refusal on the status form", async () => {
    items = [recInterview({ allowed_statuses: [{ key: "no_show", label: "No Show" }] })];
    writeReply = () => res({ detail: "You can mark this once the interview time has passed" }, 422);
    section();
    fireEvent.click(await screen.findByRole("button", { name: /Change status/ }));
    const form = screen.getByRole("form", { name: "Change status of INT-000001" });
    fireEvent.change(within(form).getByLabelText("New status (required)"), { target: { value: "no_show" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save status" }));
    expect((await within(form).findByRole("alert")).textContent).toContain("time has passed");
  });

  it("reschedules with a reason and shows the old -> new history (AC1)", async () => {
    const onChanged = vi.fn();
    items = [recInterview({ history: [...recInterview().history, { event: "rescheduled", from_status: "scheduled", to_status: "rescheduled",
      old_scheduled_at: "2026-10-12T05:30:00Z", new_scheduled_at: "2026-10-14T08:30:00Z", note: "Panel unavailable", actor: { id: "r1", full_name: "Riya Recruiter" },
      created_at: "2026-10-10T05:30:00Z" }] })];
    section(onChanged);
    const card = within(await screen.findByRole("list", { name: "Interviews of Rahul Kumar" })).getAllByRole("listitem")[0];
    expect(card.textContent).toMatch(/Rescheduled from .* to .* by Riya Recruiter — Panel unavailable/);
    fireEvent.click(within(card).getByRole("button", { name: /Reschedule/ }));
    const form = screen.getByRole("form", { name: "Reschedule INT-000001" });
    fireEvent.change(within(form).getByLabelText("New date and time (IST, required)"), { target: { value: "2030-02-01T15:00" } });
    fireEvent.change(within(form).getByLabelText("Reason"), { target: { value: "Client asked" } });
    writeReply = () => res({ interview: recInterview({ status: "rescheduled" }), notifications: { candidate: "in_app", contact: null } });
    fireEvent.click(within(form).getByRole("button", { name: "Reschedule" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Interview rescheduled. Candidate: notified in the portal."));
    expect(writes()[0]).toEqual(["/api/v1/recruiter/interviews/I1/reschedule", "POST", { scheduled_at: "2030-02-01T15:00:00+05:30", reason: "Client asked", notify: true }]);
  });

  it("edits only the changed details", async () => {
    section();
    fireEvent.click(await screen.findByRole("button", { name: /^Edit/ }));
    const form = screen.getByRole("form", { name: "Edit interview INT-000001" });
    expect(within(form).queryByLabelText("Date and time (IST, required)")).toBeNull();
    fireEvent.change(within(form).getByLabelText("Interviewer"), { target: { value: "Ravi" } });
    writeReply = () => res(recInterview({ interviewer: "Ravi" }));
    fireEvent.click(within(form).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]).toEqual(["/api/v1/recruiter/interviews/I1", "PATCH", { interviewer: "Ravi" }]);
  });

  it("hides every write for a read-only viewer and an application that cannot be scheduled", async () => {
    items = [recInterview({ allowed_statuses: [], can_edit: false, can_reschedule: false })];
    canSchedule = false;
    section();
    await screen.findByRole("list", { name: "Interviews of Rahul Kumar" });
    for (const name of [/Schedule interview/, /Change status/, /Reschedule/, /^Edit/]) expect(screen.queryByRole("button", { name })).toBeNull();
  });
});

describe("RecruiterInterviewsPanel", () => {
  it("shows Upcoming grouped by IST day with the four counts, each card linking to its requirement", async () => {
    render(<RecruiterInterviewsPanel />);
    const tabs = within(await screen.findByRole("navigation", { name: "Interview lists" })).getAllByRole("button");
    await waitFor(() => expect(tabs.map((t) => t.textContent)).toEqual(["Upcoming (2)", "Awaiting update (1)", "On hold (0)", "Closed (4)"]));
    expect(screen.getByRole("heading", { name: "Mon, 12 Oct 2026" })).toBeTruthy();
    const day = screen.getByRole("list", { name: "Interviews on Tue, 13 Oct 2026" });
    expect(within(day).getByRole("link", { name: "Rahul Kumar" }).getAttribute("href")).toBe("/recruiter/requirements/J1");
    expect(day.textContent).toContain("Java Developer · Acme Technologies");
  });

  it("keeps the tab in the URL and shows the empty and error states", async () => {
    search = "view=closed";
    listReply = () => res({ items: [], total: 0, limit: 50, offset: 0, counts: { upcoming: 0, awaiting_update: 0, on_hold: 0, closed: 0 } });
    const { unmount } = render(<RecruiterInterviewsPanel />);
    expect(await screen.findByText("No closed interviews yet.")).toBeTruthy();
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("view=closed"))).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /On hold/ }));
    expect(push).toHaveBeenCalledWith("/recruiter/interviews?view=on_hold", { scroll: false });
    unmount();
    listReply = () => res({}, 500);
    render(<RecruiterInterviewsPanel />);
    expect(await screen.findByText("Unable to load interviews.")).toBeTruthy();
    listReply = () => res({ items: [], total: 0, limit: 50, offset: 0, counts: { upcoming: 0, awaiting_update: 0, on_hold: 0, closed: 0 } });
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No closed interviews yet.")).toBeTruthy();
  });
});
