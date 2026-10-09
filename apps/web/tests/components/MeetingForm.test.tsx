import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import MeetingForm from "@/components/MeetingForm";
import { meeting } from "./meetingFixtures";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const contacts = { items: [{ id: "k1", name: "Priya Raman", designation: "Director" }, { id: "k2", name: "James Hart", designation: null }], total: 2, limit: 50, offset: 0 };
const university = { id: "u1", label: "ABC University", detail: "UNV-000001 · London, United Kingdom" };

/** fetch: the contacts read, then whatever the save answers. */
function serve(save: Response = res({ meeting: { id: "m9" } }, 201)) {
  const mock = vi.fn((url: string) => Promise.resolve(url.includes("/contacts") ? res(contacts) : save));
  vi.stubGlobal("fetch", mock);
  return mock;
}
const saveCall = (mock: ReturnType<typeof vi.fn>) => mock.mock.calls.find(([u]) => String(u).includes("/partnership/meetings")) as [string, RequestInit];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  push.mockReset();
  refresh.mockReset();
});

describe("MeetingForm (upc-009)", () => {
  it("schedules a meeting with the §7 fields and opens it (AC1, P1)", async () => {
    const mock = serve();
    render(<MeetingForm university={university} canPickResponsible={false} />);
    await screen.findByLabelText("James Hart");
    fireEvent.change(screen.getByLabelText("Meeting type"), { target: { value: "mou_discussion" } });
    fireEvent.change(screen.getByLabelText("Date and time (IST)"), { target: { value: "2030-01-10T10:00" } });
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "Main campus" } });
    fireEvent.change(screen.getByLabelText("Contact person"), { target: { value: "k1" } });
    expect(screen.getByText("Designation: Director")).toBeInTheDocument(); // MG5: copied from the contact
    fireEvent.click(screen.getByLabelText("James Hart"));
    fireEvent.change(screen.getByLabelText("Agenda"), { target: { value: "MoU clauses" } });
    fireEvent.click(screen.getByRole("button", { name: "Schedule meeting" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/partnership/meetings/m9"));
    const [url, init] = saveCall(mock);
    expect(url).toBe("/api/v1/partnership/meetings");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      university_id: "u1", meeting_type: "mou_discussion", starts_at: "2030-01-10T10:00:00+05:30", mode: "offline", location: "Main campus",
      contact_id: "k1", agenda: "MoU clauses", participant_contact_ids: ["k2"], participant_user_ids: [],
    });
  });

  it("asks for the required fields before sending anything", async () => {
    const mock = serve();
    render(<MeetingForm university={university} canPickResponsible={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Schedule meeting" }));
    expect(screen.getByText("Choose the meeting type")).toBeInTheDocument();
    expect(screen.getByText("Choose the date and time")).toBeInTheDocument();
    expect(saveCall(mock)).toBeUndefined();
  });

  it("warns, without blocking, when an online meeting has no link (E1)", async () => {
    serve();
    render(<MeetingForm university={university} canPickResponsible={false} />);
    expect(screen.queryByText(/has no link yet/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Online"));
    expect(screen.getByText(/has no link yet/)).toHaveClass("form-warning"); // QA-03: styled as a warning
    fireEvent.change(screen.getByLabelText("Meeting link"), { target: { value: "https://meet.example.com/x" } });
    expect(screen.queryByText(/has no link yet/)).not.toBeInTheDocument();
  });

  it("on edit sends only what changed, with the reschedule reason when the time moved", async () => {
    const mock = serve(res({ meeting: { id: "m1" } }));
    render(<MeetingForm meeting={meeting()} canPickResponsible={false} />);
    await screen.findByLabelText("James Hart");
    expect(screen.queryByLabelText("Reason for the new time (optional)")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Date and time (IST)"), { target: { value: "2030-01-11T15:00" } });
    fireEvent.change(screen.getByLabelText("Reason for the new time (optional)"), { target: { value: "Dean travelling" } });
    fireEvent.click(screen.getByRole("button", { name: "Save meeting" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/partnership/meetings/m1"));
    expect(refresh).toHaveBeenCalled(); // QA-01: the detail page is re-read, never served from the router cache
    const [url, init] = saveCall(mock);
    expect(url).toBe("/api/v1/partnership/meetings/m1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({ starts_at: "2030-01-11T15:00:00+05:30", reschedule_reason: "Dean travelling" });
  });

  it("places a 422 on its field (N1: a contact of another university)", async () => {
    serve(res({ detail: [{ loc: ["body", "contact_id"], msg: "Value error, Choose contacts of this university" }] }, 422));
    render(<MeetingForm university={university} canPickResponsible={false} />);
    await screen.findByLabelText("James Hart");
    fireEvent.change(screen.getByLabelText("Meeting type"), { target: { value: "introduction" } });
    fireEvent.change(screen.getByLabelText("Date and time (IST)"), { target: { value: "2030-01-10T10:00" } });
    fireEvent.change(screen.getByLabelText("Contact person"), { target: { value: "k1" } });
    fireEvent.click(screen.getByRole("button", { name: "Schedule meeting" }));
    await waitFor(() => expect(screen.getByText("Choose contacts of this university")).toBeInTheDocument());
    expect(screen.getByLabelText("Contact person")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("Check the highlighted fields.");
    expect(push).not.toHaveBeenCalled();
  });
});
