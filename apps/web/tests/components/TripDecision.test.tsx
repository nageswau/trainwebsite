import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TripDecision from "@/components/TripDecision";

import { json, trip } from "./tripFixtures";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

beforeEach(() => {
  refresh.mockReset();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("TripDecision (bdm-010)", () => {
  it("renders nothing when the caller may not decide", () => {
    const { container } = render(<TripDecision trip={trip()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("approves and refreshes", async () => {
    const mock = vi.fn().mockResolvedValue(json({ id: "t1" }));
    vi.stubGlobal("fetch", mock);
    render(<TripDecision trip={trip({ can_decide: true })} />);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(mock.mock.calls[0][0]).toBe("/api/v1/bdm/manager/trips/t1/approve");
  });

  it("asks for a reason before rejecting; Escape closes and returns focus", async () => {
    const mock = vi.fn().mockResolvedValue(json({ id: "t1" }));
    vi.stubGlobal("fetch", mock);
    render(<TripDecision trip={trip({ can_decide: true })} />);
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    const reason = screen.getByLabelText("Reason for rejecting");
    expect(reason).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Confirm reject" }));
    expect(mock).not.toHaveBeenCalled();
    expect(reason).toHaveAttribute("aria-invalid", "true");
    fireEvent.change(reason, { target: { value: "Combine with next week's trip" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm reject" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(JSON.parse(mock.mock.calls[0][1].body)).toEqual({ reason: "Combine with next week's trip" });
  });

  it("Escape on the reason closes it and focuses Reject", async () => {
    render(<TripDecision trip={trip({ can_decide: true })} />);
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    fireEvent.keyDown(screen.getByLabelText("Reason for rejecting"), { key: "Escape" });
    expect(screen.queryByLabelText("Reason for rejecting")).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "Reject" })).toHaveFocus());
  });
});
