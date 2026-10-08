import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import VisitForm from "@/components/VisitForm";
import { visit } from "./visitFixtures";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const contacts = { items: [{ id: "c1", name: "Priya Raman", designation: "Regional Manager – India" }, { id: "c2", name: "Ben Ode", designation: null }], total: 2, limit: 50, offset: 0 };
const university = { id: "u1", label: "ABC University", detail: "UNV-000001 · London, United Kingdom" };

/** Contacts load on mount; every other call is the save. */
function api(save: Response) {
  const mock = vi.fn((url: string) => Promise.resolve(url.includes("/contacts") ? res(contacts) : save));
  vi.stubGlobal("fetch", mock);
  return mock;
}
const saves = (mock: ReturnType<typeof vi.fn>) => mock.mock.calls.filter(([url]) => !String(url).includes("/contacts")) as [string, RequestInit][];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  push.mockReset();
});

describe("VisitForm (upc-010)", () => {
  it("plans a visit for the given university with blanks left out, then opens it", async () => {
    const mock = api(res({ visit: visit({ id: "v9" }) }, 201));
    render(<VisitForm university={university} canPickLead={false} />);
    expect(screen.getByText("ABC University")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Visit purpose (required)"), { target: { value: "MoU discussion" } });
    fireEvent.change(screen.getByLabelText("Proposed visit date (required)"), { target: { value: "2030-01-10" } });
    fireEvent.click(screen.getByLabelText("Travel required"));
    fireEvent.change(screen.getByLabelText("Travel notes"), { target: { value: "Flight DEL-LHR" } });
    await waitFor(() => expect(screen.getByLabelText(/Priya Raman/)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/Priya Raman/));
    fireEvent.click(screen.getByRole("button", { name: "Save visit" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/partnership/visits/v9"));
    const [url, init] = saves(mock)[0];
    expect(url).toBe("/api/v1/partnership/visits");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      university_id: "u1", purpose: "MoU discussion", proposed_date: "2030-01-10", travel_required: true, hotel_required: false,
      travel_notes: "Flight DEL-LHR", participant_user_ids: [], contact_ids: ["c1"],
    });
  });

  it("checks the required fields before sending", () => {
    const mock = api(res({}));
    render(<VisitForm university={university} canPickLead={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Save visit" }));
    expect(screen.getByText("Visit purpose is required")).toBeInTheDocument();
    expect(screen.getByText("Proposed visit date is required")).toBeInTheDocument();
    expect(screen.getByLabelText("Visit purpose (required)")).toHaveAttribute("aria-invalid", "true");
    expect(saves(mock)).toHaveLength(0);
  });

  it("puts a 422 on its field", async () => {
    api(res({ detail: [{ loc: ["body", "proposed_date"], msg: "Value error, The proposed visit date can't be in the past" }] }, 422));
    render(<VisitForm university={university} canPickLead={false} />);
    fireEvent.change(screen.getByLabelText("Visit purpose (required)"), { target: { value: "MoU" } });
    fireEvent.change(screen.getByLabelText("Proposed visit date (required)"), { target: { value: "2020-01-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Save visit" }));
    await waitFor(() => expect(screen.getByText("The proposed visit date can't be in the past")).toBeInTheDocument());
    expect(screen.getByRole("alert")).toHaveTextContent("Check the highlighted fields.");
  });

  it("shows a sentence refusal as an alert", async () => {
    api(res({ detail: "Choose meeting contacts of this university" }, 422));
    render(<VisitForm university={university} canPickLead={false} />);
    fireEvent.change(screen.getByLabelText("Visit purpose (required)"), { target: { value: "MoU" } });
    fireEvent.change(screen.getByLabelText("Proposed visit date (required)"), { target: { value: "2030-01-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Save visit" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Choose meeting contacts of this university"));
    expect(push).not.toHaveBeenCalled();
  });

  it("edits an approved visit: the approved plan is locked and only changes are sent", async () => {
    const approved = visit({ status: "approved", approval_state: null, editable_fields: ["agenda", "confirmed_date", "contact_ids", "expected_outcome", "hotel_notes", "travel_notes"] });
    const mock = api(res({ visit: approved }));
    render(<VisitForm visit={approved} canPickLead={false} />);
    expect(screen.getByLabelText("Visit purpose (required)")).toBeDisabled();
    expect(screen.getByLabelText("Proposed visit date (required)")).toBeDisabled();
    expect(screen.getByLabelText("Travel required")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Confirmed visit date"), { target: { value: "2030-01-12" } });
    fireEvent.change(screen.getByLabelText("Hotel notes"), { target: { value: "Booked: Hotel X" } });
    fireEvent.click(screen.getByRole("button", { name: "Save visit" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/partnership/visits/v1"));
    const [url, init] = saves(mock)[0];
    expect(url).toBe("/api/v1/partnership/visits/v1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({ confirmed_date: "2030-01-12", hotel_notes: "Booked: Hotel X" });
  });
});
