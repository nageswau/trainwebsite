import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TripRemarks from "@/components/TripRemarks";

import { json, trip } from "./tripFixtures";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("TripRemarks (bdm-010)", () => {
  it("saves remarks in any state, clearing with null", async () => {
    const mock = vi.fn().mockResolvedValue(json({ id: "t1" }));
    vi.stubGlobal("fetch", mock);
    render(<TripRemarks trip={trip({ travel_status: "completed", approval_status: "approved", remarks: "Met the dean" })} />);
    const box = screen.getByLabelText("Remarks");
    expect(box).toHaveValue("Met the dean");
    fireEvent.change(box, { target: { value: "  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save remarks" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(JSON.parse(mock.mock.calls[0][1].body)).toEqual({ remarks: null });
    expect(screen.getByRole("status")).toHaveTextContent("Remarks saved");
  });
});
