import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ApplicationArrivalPanel from "@/components/ApplicationArrivalPanel";

// ccrm-028 (DEC-SCOPE-265): after enrolment the counselor records arrival and orientation.
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, ok = true, status = 200) => Promise.resolve({ ok, status, json: async () => body });
const VIEW = {
  status: "enrolled", can_record: true, arrival_date: null, arrival_confirmed: false, confirmed_at: null, confirmed_by: null,
  orientation_attended: false, notes: null,
};
const ARRIVAL = "/api/v1/workflows/overseas/applications/a1/arrival";

describe("ApplicationArrivalPanel", () => {
  it("shows loading, then a load failure with a retry, then the not-recorded state", async () => {
    const fetchMock = vi.fn().mockReturnValueOnce(json({ detail: "Application not found" }, false, 404)).mockReturnValue(json({ arrival: VIEW }));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationArrivalPanel applicationId="a1" onChanged={vi.fn()} />);
    expect(screen.getByText("Loading arrival…")).toBeInTheDocument();
    expect(await screen.findByText("Application not found")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Arrival not recorded yet.")).toBeInTheDocument();
  });

  it("keeps orientation off until arrival is confirmed, then saves the whole record", async () => {
    const onChanged = vi.fn();
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => (init?.method === "PUT" ? json({ changed: true, arrival: VIEW }) : json({ arrival: VIEW })));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationArrivalPanel applicationId="a1" onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Record arrival" }));
    const orientation = screen.getByLabelText("Orientation attended");
    expect(orientation).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Arrival date"), { target: { value: "2027-09-01" } });
    fireEvent.click(screen.getByLabelText("Arrival confirmed"));
    expect(orientation).toBeEnabled();
    fireEvent.click(orientation);
    fireEvent.change(screen.getByLabelText("Notes (optional)"), { target: { value: " Confirmed by phone " } });
    fireEvent.click(screen.getByRole("button", { name: "Save arrival" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Arrival saved."));
    const put = fetchMock.mock.calls.find(([url, init]) => url === ARRIVAL && init?.method === "PUT");
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({ arrival_date: "2027-09-01", arrival_confirmed: true, orientation_attended: true, notes: "Confirmed by phone" });
  });

  it("un-confirming arrival also clears orientation", async () => {
    const confirmed = { ...VIEW, arrival_date: "2027-09-01", arrival_confirmed: true, confirmed_by: "Asha Rao", confirmed_at: "2027-09-02T10:00:00Z", orientation_attended: true };
    vi.stubGlobal("fetch", vi.fn(() => json({ arrival: confirmed })));
    render(<ApplicationArrivalPanel applicationId="a1" onChanged={vi.fn()} />);
    expect(await screen.findByText(/Asha Rao/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit arrival" }));
    fireEvent.click(screen.getByLabelText("Arrival confirmed"));
    expect(screen.getByLabelText("Orientation attended")).not.toBeChecked();
    expect(screen.getByLabelText("Orientation attended")).toBeDisabled();
  });

  it("shows a refusal from the server and keeps the entry", async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) =>
      init?.method === "PUT" ? json({ detail: "A confirmed arrival date cannot be in the future" }, false, 422) : json({ arrival: VIEW }),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationArrivalPanel applicationId="a1" onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Record arrival" }));
    fireEvent.change(screen.getByLabelText("Arrival date"), { target: { value: "2099-01-01" } });
    fireEvent.click(screen.getByLabelText("Arrival confirmed"));
    fireEvent.click(screen.getByRole("button", { name: "Save arrival" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A confirmed arrival date cannot be in the future");
    expect(screen.getByLabelText("Arrival date")).toHaveValue("2099-01-01");
  });
});
