import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import MeetingActions from "@/components/MeetingActions";
import { meeting } from "./meetingFixtures";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const call = (mock: ReturnType<typeof vi.fn>, i = 0) => mock.mock.calls[i] as [string, RequestInit];
const can = (p: Partial<ReturnType<typeof meeting>["permissions"]>) => meeting({ permissions: { can_edit: true, can_complete: false, can_cancel: true, ...p } });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("MeetingActions (upc-009)", () => {
  it("renders nothing for a reader without rights", () => {
    const { container } = render(<MeetingActions meeting={meeting()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("before the start: Cancel only, with a hint that the outcome comes later", () => {
    render(<MeetingActions meeting={can({})} />);
    expect(screen.getByRole("button", { name: "Cancel meeting" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record outcome" })).not.toBeInTheDocument();
    expect(screen.getByText(/once the meeting has started/)).toBeInTheDocument();
  });

  it("an outcome needs notes, discussion points or decisions, and a next action needs its due date (nothing sent)", () => {
    const mock = vi.fn();
    vi.stubGlobal("fetch", mock);
    render(<MeetingActions meeting={can({ can_complete: true })} />);
    fireEvent.click(screen.getByRole("button", { name: "Record outcome" }));
    fireEvent.click(screen.getByRole("button", { name: "Save outcome" }));
    expect(screen.getByText("Record notes, discussion points or decisions")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Decisions"), { target: { value: "Go ahead" } });
    fireEvent.change(screen.getByLabelText("Next action"), { target: { value: "Send MoU" } });
    fireEvent.click(screen.getByRole("button", { name: "Save outcome" }));
    expect(screen.getByText("Choose when the next action is due")).toBeInTheDocument();
    expect(mock).not.toHaveBeenCalled();
  });

  it("records the outcome with the follow-ups (AC2, Q-12), announces it and refreshes", async () => {
    const mock = vi.fn(() => Promise.resolve(res({ meeting: meeting({ status: "completed" }) })));
    vi.stubGlobal("fetch", mock);
    render(<MeetingActions meeting={can({ can_complete: true })} />);
    fireEvent.click(screen.getByRole("button", { name: "Record outcome" }));
    fireEvent.change(screen.getByLabelText("Discussion points"), { target: { value: "Clauses 4-7" } });
    fireEvent.change(screen.getByLabelText("Next action"), { target: { value: "Send the revised MoU" } });
    fireEvent.change(screen.getByLabelText("Next action due date"), { target: { value: "2030-01-12" } });
    fireEvent.change(screen.getByLabelText("Next meeting date"), { target: { value: "2030-02-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save outcome" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Outcome recorded."));
    expect(call(mock)[0]).toBe("/api/v1/partnership/meetings/m1/complete");
    expect(JSON.parse(String(call(mock)[1].body))).toEqual({
      discussion_points: "Clauses 4-7", next_action: "Send the revised MoU", next_action_due_on: "2030-01-12", next_meeting_date: "2030-02-01",
    });
    expect(refresh).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Record outcome" })).not.toBeInTheDocument(); // stale actions hidden until the re-read
  });

  it("places a server field error on its field and keeps the typed text", async () => {
    const detail = [{ loc: ["body", "next_action_due_on"], msg: "Value error, Choose today or a later date" }];
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail }, 422))));
    render(<MeetingActions meeting={can({ can_complete: true })} />);
    fireEvent.click(screen.getByRole("button", { name: "Record outcome" }));
    fireEvent.change(screen.getByLabelText("Notes"), { target: { value: "Met" } });
    fireEvent.change(screen.getByLabelText("Next action"), { target: { value: "Call" } });
    fireEvent.change(screen.getByLabelText("Next action due date"), { target: { value: "2020-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save outcome" }));
    await waitFor(() => expect(screen.getByText("Choose today or a later date")).toBeInTheDocument());
    expect(screen.getByLabelText("Next action due date")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Notes")).toHaveValue("Met");
  });

  it("cancelling needs a reason; Escape backs out", async () => {
    const mock = vi.fn(() => Promise.resolve(res({ meeting: meeting({ status: "cancelled" }) })));
    vi.stubGlobal("fetch", mock);
    render(<MeetingActions meeting={can({})} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel meeting" }));
    fireEvent.keyDown(screen.getByLabelText("Why is the meeting cancelled?"), { key: "Escape" });
    expect(screen.getByRole("button", { name: "Cancel meeting" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel meeting" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm cancel" }));
    expect(screen.getByText("A reason is required")).toBeInTheDocument();
    expect(mock).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Why is the meeting cancelled?"), { target: { value: "Dean unavailable" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm cancel" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Meeting cancelled."));
    expect(call(mock)[0]).toBe("/api/v1/partnership/meetings/m1/cancel");
    expect(JSON.parse(String(call(mock)[1].body))).toEqual({ reason: "Dean unavailable" });
  });

  it("a failure is shown as an alert", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "This meeting was cancelled" }, 409))));
    render(<MeetingActions meeting={can({})} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel meeting" }));
    fireEvent.change(screen.getByLabelText("Why is the meeting cancelled?"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm cancel" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("This meeting was cancelled"));
  });
});
