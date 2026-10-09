import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PartnershipEventCancel from "@/components/PartnershipEventCancel";
import PartnershipEventForm from "@/components/PartnershipEventForm";
import type { PartnershipEvent } from "@/lib/partnershipCalendar";

// upc-011 (CL2-CL6): the event form and the cancel action.
const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pm = { id: "u1", full_name: "Asha Rao", active: true };
const event: PartnershipEvent = {
  id: "e1", code: "PEV-000001", kind: "education_fair", title: "QS Fair", university: null, starts_on: "2030-01-10", ends_on: "2030-01-12",
  location: "Delhi", notes: null, status: "scheduled", owner: pm, created_by: pm, participants: [], cancelled_at: null, cancel_reason: null,
  overlaps: [], permissions: { can_edit: true, can_cancel: true }, created_at: "2029-12-01T00:00:00Z", updated_at: "2029-12-01T00:00:00Z",
};

function serve(save: Response = res({ event: { id: "e9" } }, 201)) {
  const mock = vi.fn(() => Promise.resolve(save));
  vi.stubGlobal("fetch", mock);
  return mock;
}
const call = (mock: ReturnType<typeof vi.fn>) => mock.mock.calls.find(([u]) => String(u).includes("/partnership/events")) as [string, RequestInit] | undefined;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  push.mockReset();
  refresh.mockReset();
});

describe("PartnershipEventForm (upc-011)", () => {
  it("adds an event without a university and opens it", async () => {
    const mock = serve();
    render(<PartnershipEventForm canPickOwner={false} />);
    fireEvent.change(screen.getByLabelText("Event type"), { target: { value: "education_fair" } });
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: " QS Fair " } });
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2030-01-10" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2030-01-12" } });
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "Delhi" } });
    fireEvent.click(screen.getByRole("button", { name: "Add event" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/partnership/events/e9"));
    const [url, init] = call(mock)!;
    expect(url).toBe("/api/v1/partnership/events");
    expect(JSON.parse(String(init.body))).toEqual({
      kind: "education_fair", title: "QS Fair", starts_on: "2030-01-10", ends_on: "2030-01-12", location: "Delhi", participant_user_ids: [],
    });
    expect(screen.queryByLabelText("Owner")).toBeNull(); // a manager owns their own events (CL4)
  });

  it("never sends twice: a click after a successful save, before the page changes, is ignored (QA-01)", async () => {
    const mock = serve();
    render(<PartnershipEventForm event={event} canPickOwner={false} />);
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "QS Fair Delhi" } });
    fireEvent.click(screen.getByRole("button", { name: "Save event" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/partnership/events/e9"));
    fireEvent.click(screen.getByRole("button", { name: /Sav/ }));
    expect(mock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: /Sav/ })).toBeDisabled();
  });

  it("checks required fields and the date order before sending", () => {
    const mock = serve();
    render(<PartnershipEventForm canPickOwner />);
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2030-01-10" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2030-01-09" } });
    fireEvent.click(screen.getByRole("button", { name: "Add event" }));
    expect(screen.getByText("Choose the event type")).toBeInTheDocument();
    expect(screen.getByText("Give the event a title")).toBeInTheDocument();
    expect(screen.getByText("The end date can't be before the start date")).toBeInTheDocument();
    expect(screen.getByLabelText("End date")).toHaveAttribute("aria-invalid", "true");
    expect(call(mock)).toBeUndefined();
  });

  it("sends only what changed on edit and shows the API's field errors", async () => {
    const mock = serve(res({ detail: [{ loc: ["body", "ends_on"], msg: "An event can last at most 31 days", type: "value_error" }] }, 422));
    render(<PartnershipEventForm event={event} canPickOwner={false} />);
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2030-03-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save event" }));
    expect(await screen.findByText("An event can last at most 31 days")).toBeInTheDocument();
    const [url, init] = call(mock)!;
    expect(url).toBe("/api/v1/partnership/events/e1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({ ends_on: "2030-03-01" });
    expect(screen.getByRole("alert")).toHaveTextContent("Check the highlighted fields.");
  });

  it("returns to the event when nothing changed", () => {
    const mock = serve();
    render(<PartnershipEventForm event={event} canPickOwner={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Save event" }));
    expect(push).toHaveBeenCalledWith("/partnership/events/e1");
    expect(call(mock)).toBeUndefined();
  });
});

describe("PartnershipEventCancel (upc-011 CL6)", () => {
  it("asks for a reason, cancels and re-reads the page", async () => {
    const mock = serve(res({ event: { ...event, status: "cancelled" } }));
    render(<PartnershipEventCancel event={event} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel event" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm cancel" }));
    expect(screen.getByText("A reason is required")).toBeInTheDocument();
    expect(call(mock)).toBeUndefined();
    fireEvent.change(screen.getByLabelText("Why is the event cancelled?"), { target: { value: "Fair postponed" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm cancel" }));
    expect(await screen.findByText("Event cancelled.")).toBeInTheDocument();
    expect(refresh).toHaveBeenCalled();
    const [url, init] = call(mock)!;
    expect(url).toBe("/api/v1/partnership/events/e1/cancel");
    expect(JSON.parse(String(init.body))).toEqual({ reason: "Fair postponed" });
    expect(screen.queryByRole("button", { name: "Cancel event" })).toBeNull();
  });

  it("renders nothing without the permission", () => {
    const { container } = render(<PartnershipEventCancel event={{ ...event, permissions: { can_edit: false, can_cancel: false } }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
