import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TripActions from "@/components/TripActions";

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

describe("TripActions (bdm-010)", () => {
  it("offers only the actions the API allows", () => {
    render(<TripActions trip={trip({ can_submit: true, can_cancel: true })} />);
    expect(screen.getByRole("button", { name: "Submit for approval" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel trip" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Withdraw" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Start trip" })).toBeNull();
  });

  it("renders nothing when no action is allowed", () => {
    const { container } = render(<TripActions trip={trip()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("submits and refreshes", async () => {
    const mock = vi.fn().mockResolvedValue(json({ id: "t1" }));
    vi.stubGlobal("fetch", mock);
    render(<TripActions trip={trip({ can_submit: true })} />);
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(mock.mock.calls[0][0]).toBe("/api/v1/bdm/trips/t1/submit");
    expect(mock.mock.calls[0][1].method).toBe("POST");
    expect(screen.getByRole("status")).toHaveTextContent("Submitted for approval");
  });

  it("confirms a cancel inline; Escape backs out and returns focus", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<TripActions trip={trip({ can_cancel: true })} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel trip" }));
    const confirm = screen.getByRole("button", { name: "Confirm cancel" });
    expect(confirm).toHaveFocus();
    fireEvent.keyDown(confirm, { key: "Escape" });
    expect(screen.queryByRole("button", { name: "Confirm cancel" })).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "Cancel trip" })).toHaveFocus());
  });

  it("shows a 409 and refreshes so the new state appears", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "This trip is approved and can't be withdrawn" }, 409)));
    render(<TripActions trip={trip({ can_withdraw: true })} />);
    fireEvent.click(screen.getByRole("button", { name: "Withdraw" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This trip is approved and can't be withdrawn");
    expect(refresh).toHaveBeenCalled();
  });
});
