import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TripForm from "@/components/TripForm";
import { NOT_COMPLETED } from "@/lib/apiErrors";

import { json, trip } from "./tripFixtures";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

const TODAY = "2026-10-03";

function fill(values: Record<string, string>) {
  for (const [label, value] of Object.entries(values)) fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

const VALID = { "Travel date": "2026-10-10", "Return date": "2026-10-11", From: "Hyderabad", To: "Vijayawada", Purpose: "College visits", "Estimated cost (₹)": "2500" };

beforeEach(() => {
  push.mockReset();
  refresh.mockReset();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("TripForm (bdm-010)", () => {
  it("checks required fields and the return date before sending anything", () => {
    const mock = vi.fn();
    vi.stubGlobal("fetch", mock);
    render(<TripForm today={TODAY} />);
    fill({ "Travel date": "2026-10-10", "Return date": "2026-10-09" });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    expect(mock).not.toHaveBeenCalled();
    expect(screen.getByLabelText("From")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Return date must be on or after the travel date")).toBeInTheDocument();
    expect(screen.getByLabelText("Return date")).toHaveAccessibleDescription("Return date must be on or after the travel date");
    expect(screen.getByRole("alert")).toHaveTextContent("Check the highlighted fields");
  });

  it("limits the travel date to 30 days back", () => {
    render(<TripForm today={TODAY} />);
    expect(screen.getByLabelText("Travel date")).toHaveAttribute("min", "2026-09-03");
    expect(screen.getByLabelText("Estimated cost (₹)")).toHaveAttribute("inputmode", "decimal");
  });

  it("creates a draft and opens it", async () => {
    let release!: (r: Response) => void;
    const mock = vi.fn().mockReturnValue(new Promise<Response>((r) => { release = r; }));
    vi.stubGlobal("fetch", mock);
    render(<TripForm today={TODAY} />);
    fill(VALID);
    fireEvent.change(screen.getByLabelText("Mode of travel"), { target: { value: "bus" } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    const [url, init] = mock.mock.calls[0];
    expect(url).toBe("/api/v1/bdm/trips");
    expect(JSON.parse(init.body)).toEqual({
      travel_date: "2026-10-10", return_date: "2026-10-11", from_place: "Hyderabad", to_place: "Vijayawada", purpose: "College visits",
      mode: "bus", accommodation_required: false, estimated_cost: "2500",
    });
    release(json({ id: "new1" }, 201));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/bdm/travel/new1"));
  });

  it("puts a 422 next to its field", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: [{ loc: ["body", "purpose"], msg: "Value error, Purpose contains invalid characters" }] }, 422)));
    render(<TripForm today={TODAY} />);
    fill(VALID);
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    expect(await screen.findByText("Purpose contains invalid characters", { selector: "p" })).toBeInTheDocument();
    expect(screen.getByLabelText("Purpose")).toHaveAttribute("aria-invalid", "true");
  });

  it("keeps the entry when the network drops", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    render(<TripForm today={TODAY} />);
    fill(VALID);
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    expect(await screen.findByText(NOT_COMPLETED)).toBeInTheDocument();
    expect(screen.getByLabelText("From")).toHaveValue("Hyderabad");
  });

  it("edits only the changed fields and refreshes", async () => {
    const mock = vi.fn().mockResolvedValue(json({ id: "t1" }));
    vi.stubGlobal("fetch", mock);
    render(<TripForm today={TODAY} trip={trip({ can_edit: true })} />);
    expect(screen.getByLabelText("From")).toHaveValue("Hyderabad");
    fill({ To: "Guntur" });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = mock.mock.calls[0];
    expect([url, init.method, JSON.parse(init.body)]).toEqual(["/api/v1/bdm/trips/t1", "PATCH", { to_place: "Guntur" }]);
    expect(screen.getByRole("status")).toHaveTextContent("Trip saved");
  });
});
