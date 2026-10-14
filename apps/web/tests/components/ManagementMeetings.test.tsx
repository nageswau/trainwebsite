import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ManagementMeetingCalendar from "@/components/ManagementMeetingCalendar";
import ManagementMeetingChain from "@/components/ManagementMeetingChain";
import ManagementMeetingForm from "@/components/ManagementMeetingForm";
import MyManagementMeetings from "@/components/MyManagementMeetings";
import type { DiscussionOptions } from "@/lib/managementDiscussions";
import type { Meeting, MeetingDetail, MeetingPage, MyMeeting } from "@/lib/managementMeetings";

const router = { replace: vi.fn(), refresh: vi.fn(), push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router, redirect: vi.fn(), usePathname: () => "/management/meetings" }));

const PARTNER = { id: "u1", full_name: "Arjun Partner", role: "partner" };
const TRAINER = { id: "u2", full_name: "Ravi Trainer", role: "trainer" };
const options: DiscussionOptions = { users: [PARTNER, TRAINER] };

function meeting(overrides: Partial<Meeting> = {}): Meeting {
  return {
    id: "m1", title: "Monthly partner meeting", kind: "partner", starts_at: "2026-10-14T04:30:00Z", mode: "Online", location: null,
    meeting_url: "https://meet.example.com/abc", status: "scheduled", participant_count: 2, ...overrides,
  };
}
function detail(overrides: Partial<MeetingDetail> = {}): MeetingDetail {
  return {
    ...meeting({ status: "completed" }), agenda: "1. Targets", minutes: "Agreed the Japan plan.", minutes_recorded_at: "2026-10-14T06:00:00Z",
    participants: [TRAINER], decisions: [], tasks: [], progress: { done: 0, total: 0 }, created_by: PARTNER, updated_by: PARTNER,
    created_at: "2026-10-01T04:30:00Z", updated_at: "2026-10-14T06:00:00Z", ...overrides,
  };
}
function page(items: Meeting[], overrides: Partial<MeetingPage> = {}): MeetingPage {
  return { items, date_from: "2026-10-12", date_to: "2026-10-18", today: "2026-10-14", ...overrides };
}

type Call = { url: string; method: string; body: unknown };
let calls: Call[];
function respond(...answers: { status?: number; body?: unknown }[]) {
  const queue = [...answers];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url, method: init.method ?? "GET", body: init.body ? JSON.parse(String(init.body)) : undefined });
    const answer = queue.shift() ?? { body: { id: "m9" } };
    return new Response(JSON.stringify(answer.body ?? {}), { status: answer.status ?? 200, headers: { "Content-Type": "application/json" } });
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

describe("ManagementMeetingCalendar (MM11)", () => {
  it("lists every day of the week and places each meeting on its IST day", () => {
    render(<ManagementMeetingCalendar data={page([meeting(), meeting({ id: "m2", title: "School review", kind: "school", starts_at: "2026-10-15T18:45:00Z" })])} view="week" date="2026-10-14" />);
    expect(screen.getAllByRole("heading", { level: 4 })).toHaveLength(7);
    const wednesday = screen.getByRole("region", { name: /Wednesday 14 Oct/ });
    expect(within(wednesday).getByRole("link", { name: /Monthly partner meeting/ })).toHaveAttribute("href", "/management/meetings/m1");
    expect(within(wednesday).getByText("10:00 IST")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: /Friday 16 Oct/ })).getByText("School meeting")).toBeInTheDocument(); // 00:15 IST
    expect(screen.getByRole("link", { name: "Next week" })).toHaveAttribute("href", "/management/meetings?view=week&date=2026-10-21");
  });

  it("lists only days with meetings in the month view", () => {
    render(<ManagementMeetingCalendar data={page([meeting()], { date_from: "2026-10-01", date_to: "2026-10-31" })} view="month" date="2026-10-14" />);
    expect(screen.getAllByRole("heading", { level: 4 })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Previous month" })).toHaveAttribute("href", "/management/meetings?view=month&date=2026-09-01");
  });

  it("shows the empty and error states", () => {
    const { unmount } = render(<ManagementMeetingCalendar data={page([])} view="week" date="2026-10-14" />);
    expect(screen.getByText("No meetings this week.")).toBeInTheDocument();
    unmount();
    render(<ManagementMeetingCalendar data={null} view="week" date="2026-10-14" />);
    expect(screen.getByText("Unable to load the calendar.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute("href", "/management/meetings?view=week&date=2026-10-14");
  });
});

describe("ManagementMeetingForm (MM2-MM5)", () => {
  it("checks the required fields before sending", async () => {
    respond();
    render(<ManagementMeetingForm options={options} />);
    fireEvent.click(screen.getByRole("button", { name: "Schedule meeting" }));
    expect(await screen.findByText("Give the title (2-200 characters)")).toBeInTheDocument();
    expect(screen.getByText("Choose the date and time")).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it("schedules a meeting in IST with its participants", async () => {
    respond({ status: 201, body: { id: "m9" } });
    render(<ManagementMeetingForm options={options} />);
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Monthly partner meeting" } });
    fireEvent.change(screen.getByLabelText("Kind"), { target: { value: "marketing_review" } });
    fireEvent.change(screen.getByLabelText("Date and time (IST)"), { target: { value: "2026-10-20T10:00" } });
    fireEvent.change(screen.getByLabelText("Meeting link (optional)"), { target: { value: "https://meet.example.com/x" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /Ravi Trainer/ }));
    fireEvent.click(screen.getByRole("button", { name: "Schedule meeting" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/management/meetings/m9"));
    expect(calls[0]).toMatchObject({ method: "POST", url: "/api/v1/management/meetings" });
    expect(calls[0].body).toMatchObject({ title: "Monthly partner meeting", kind: "marketing_review", starts_at: "2026-10-20T10:00:00+05:30", mode: "Online", meeting_url: "https://meet.example.com/x", participant_ids: ["u2"] });
  });

  it("refuses a link that is not http(s) and shows the API's field errors", async () => {
    respond({ status: 422, body: { detail: [{ loc: ["body", "starts_at"], msg: "Value error, Choose a time within a year from now, before or after" }] } });
    render(<ManagementMeetingForm options={options} />);
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Review" } });
    fireEvent.change(screen.getByLabelText("Date and time (IST)"), { target: { value: "2030-10-20T10:00" } });
    fireEvent.change(screen.getByLabelText("Meeting link (optional)"), { target: { value: "ftp://x" } });
    fireEvent.click(screen.getByRole("button", { name: "Schedule meeting" }));
    expect(await screen.findByText("Use a link starting with http:// or https://")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Meeting link (optional)"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Schedule meeting" }));
    expect(await screen.findByText("Choose a time within a year from now, before or after")).toBeInTheDocument();
  });

  it("sends only the changed fields on an edit", async () => {
    respond({ body: { id: "m1" } });
    render(<ManagementMeetingForm options={options} meeting={detail({ status: "scheduled", minutes: null })} />);
    fireEvent.change(screen.getByLabelText("Location (optional)"), { target: { value: "Board room" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/management/meetings/m1"));
    expect(calls[0]).toMatchObject({ method: "PATCH", url: "/api/v1/management/meetings/m1", body: { location: "Board room" } });
  });
});

describe("ManagementMeetingChain (MM6-MM10, AC)", () => {
  const chain = detail({
    decisions: [{
      id: "d1", decision: "Proceed with Japan agreement", responsible: TRAINER, deadline: "2026-10-20", status: "in_progress",
      tasks: [{ id: "t1", title: "Send the draft MoU", owner: TRAINER, priority: "high", deadline: "2026-10-16", status: "completed" }],
    }],
    tasks: [{ id: "t2", title: "Book the next review", owner: PARTNER, priority: "low", deadline: "2026-10-30", status: "open" }],
    progress: { done: 1, total: 3 },
  });

  it("shows the minutes' decisions with their tasks, the meeting's tasks and the roll-up", () => {
    render(<ManagementMeetingChain meeting={chain} options={options} started />);
    expect(screen.getByText("1 of 3 completed")).toBeInTheDocument();
    const decision = screen.getByRole("listitem", { name: "Proceed with Japan agreement" });
    expect(within(decision).getByText("Ravi Trainer (Trainer) · Due 20 Oct 2026")).toBeInTheDocument();
    expect(within(decision).getByText("In Progress")).toBeInTheDocument();
    expect(within(decision).getByText(/Send the draft MoU/)).toBeInTheDocument();
    expect(within(decision).getByText("Completed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open decision Proceed with Japan agreement" })).toHaveAttribute("href", "/management/discussions/d1");
    expect(screen.getByText(/Book the next review/)).toBeInTheDocument();
  });

  it("saves the minutes", async () => {
    respond({ body: chain });
    render(<ManagementMeetingChain meeting={detail({ status: "scheduled", minutes: null, minutes_recorded_at: null })} options={options} started />);
    expect(screen.queryByRole("button", { name: "Add decision" })).not.toBeInTheDocument(); // the chain starts from the minutes
    fireEvent.change(screen.getByRole("textbox", { name: "Minutes" }), { target: { value: "Agreed the plan." } });
    fireEvent.click(screen.getByRole("button", { name: "Save minutes" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
    expect(calls[0]).toMatchObject({ method: "POST", url: "/api/v1/management/meetings/m1/minutes", body: { minutes: "Agreed the plan." } });
  });

  it("adds a decision and a task under it from the minutes", async () => {
    respond({ status: 201, body: chain }, { status: 201, body: chain });
    render(<ManagementMeetingChain meeting={chain} options={options} started />);
    fireEvent.change(screen.getByLabelText("Decision"), { target: { value: "Hire two trainers" } });
    fireEvent.change(screen.getByLabelText("Person responsible (optional)"), { target: { value: "u2" } });
    fireEvent.click(screen.getByRole("button", { name: "Add decision" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]).toMatchObject({ method: "POST", url: "/api/v1/management/meetings/m1/decisions", body: { decision: "Hire two trainers", responsible_user_id: "u2", deadline: null } });
    fireEvent.change(screen.getByLabelText("Task"), { target: { value: "Post the job" } });
    fireEvent.change(screen.getByLabelText("Owner"), { target: { value: "u2" } });
    fireEvent.change(screen.getByLabelText("Deadline"), { target: { value: "2026-10-20" } });
    fireEvent.change(screen.getByLabelText("Under decision (optional)"), { target: { value: "d1" } });
    fireEvent.click(screen.getByRole("button", { name: "Add task" }));
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1].body).toEqual({ title: "Post the job", owner_user_id: "u2", priority: "medium", deadline: "2026-10-20", decision_id: "d1" });
  });

  it("waits for the start before minutes, and a cancelled meeting takes nothing", () => {
    const { unmount } = render(<ManagementMeetingChain meeting={detail({ status: "scheduled", minutes: null, minutes_recorded_at: null })} options={options} started={false} />);
    expect(screen.getByText("Minutes can be recorded once the meeting has started.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel meeting" })).toBeInTheDocument();
    unmount();
    render(<ManagementMeetingChain meeting={detail({ status: "cancelled", minutes: null, minutes_recorded_at: null })} options={options} started />);
    expect(screen.getByText("This meeting was cancelled.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("cancels a scheduled meeting after confirming", async () => {
    respond({ body: detail({ status: "cancelled" }) });
    vi.stubGlobal("confirm", vi.fn(() => true));
    render(<ManagementMeetingChain meeting={detail({ status: "scheduled", minutes: null, minutes_recorded_at: null })} options={options} started={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel meeting" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
    expect(calls[0]).toMatchObject({ method: "PATCH", url: "/api/v1/management/meetings/m1", body: { status: "cancelled" } });
  });
});

describe("MyManagementMeetings (MM12)", () => {
  const mine = (overrides: Partial<MyMeeting> = {}): MyMeeting => ({
    id: "m1", title: "Monthly partner meeting", kind: "partner", starts_at: "2026-10-14T04:30:00Z", mode: "Online", location: "Board room",
    meeting_url: "https://meet.example.com/abc", agenda: "1. Targets", status: "scheduled", ...overrides,
  });

  it("lists the participant's meetings with time, place, link and agenda", () => {
    render(<MyManagementMeetings items={[mine(), mine({ id: "m2", title: "Old review", meeting_url: "javascript:alert(1)", status: "cancelled" })]} />);
    expect(screen.getByText("Monthly partner meeting")).toBeInTheDocument();
    expect(screen.getAllByText(/14 Oct 2026, 10:00 IST/)).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Join Monthly partner meeting" })).toHaveAttribute("href", "https://meet.example.com/abc");
    expect(screen.queryByRole("link", { name: "Join Old review" })).not.toBeInTheDocument();
    expect(screen.getByText("Cancelled")).toBeInTheDocument();
  });

  it("says when there are none", () => {
    render(<MyManagementMeetings items={[]} />);
    expect(screen.getByText("No management meetings for you this week or later.")).toBeInTheDocument();
  });
});
