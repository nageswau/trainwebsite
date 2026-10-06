import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TripItinerary from "@/components/TripItinerary";
import TripProductivity from "@/components/TripProductivity";
import TripWorkspace from "@/components/TripWorkspace";
import type { ItineraryItem } from "@/lib/bdmTravel";

import { metrics, trip } from "./tripFixtures";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
afterEach(cleanup);

const item = (over: Partial<ItineraryItem>): ItineraryItem => ({
  id: "a1", code: "APT-000001", starts_at: "2026-09-18T04:30:00Z", duration_minutes: 60, appointment_type: "course_promotion", status: "confirmed",
  organization: { id: "o1", name: "ABC College" }, expected_leads: null, expected_revenue: null, ...over,
});
// EVID-016 §4: Iqbal Khan, 18 Sep 2026, Hyderabad -> Vijayawada, 3 appointments ("Pending" is an appointment not yet confirmed).
const SOURCE_EXAMPLE = [
  item({}),
  item({ id: "a2", code: "APT-000002", starts_at: "2026-09-18T07:30:00Z", appointment_type: "mou_discussion", organization: { id: "o2", name: "XYZ College" } }),
  item({ id: "a3", code: "APT-000003", starts_at: "2026-09-18T10:30:00Z", appointment_type: "principal_meeting", status: "scheduled", organization: { id: "o3", name: "PQR College" } }),
];
const sourceTrip = (over = {}) => trip({ travel_date: "2026-09-18", return_date: "2026-09-18", approval_status: "approved", itinerary: SOURCE_EXAMPLE, ...over });
const rowsOf = () => screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell").map((c) => c.textContent));

describe("TripItinerary (bdm-011 AC4)", () => {
  it("renders the §4 example: time, organization, meeting and status for each appointment", () => {
    render(<TripItinerary trip={sourceTrip()} view="manager" />);
    expect(screen.getByRole("table", { name: "Appointments on this trip" })).toBeInTheDocument();
    expect(rowsOf()).toEqual([
      ["10:00 am", "ABC College", "Course Promotion", "Confirmed"],
      ["1:00 pm", "XYZ College", "MoU Discussion", "Confirmed"],
      ["4:00 pm", "PQR College", "Principal Meeting", "Scheduled"],
    ]);
    expect(screen.getByRole("link", { name: "ABC College" })).toHaveAttribute("href", "/bdm/manager/appointments/a1");
  });

  it("shows the day as well when the trip spans several days, and links the BDM to their appointment", () => {
    // January: en-GB's short September is "Sep" or "Sept" depending on the ICU version; January is "Jan" in every one.
    const january = [item({ starts_at: "2027-01-18T04:30:00Z" })];
    render(<TripItinerary trip={sourceTrip({ travel_date: "2027-01-18", return_date: "2027-01-19", itinerary: january })} view="owner" />);
    expect(rowsOf()[0][0]).toBe("18 Jan, 10:00 am");
    expect(screen.getByRole("link", { name: "ABC College" })).toHaveAttribute("href", "/bdm/appointments/a1");
  });

  it("an owner's empty trip says how to add appointments", () => {
    render(<TripItinerary trip={trip()} view="owner" />);
    expect(screen.getByText(/No appointments are linked to this trip yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Book an appointment" })).toHaveAttribute("href", "/bdm/appointments/new");
  });

  it("a manager's empty trip has no booking link", () => {
    render(<TripItinerary trip={trip()} view="manager" />);
    expect(screen.queryByRole("link", { name: "Book an appointment" })).toBeNull();
  });

  it("says when the trip is not approved yet (Q-05) or cancelled (L4)", () => {
    render(<TripItinerary trip={sourceTrip({ approval_status: "rejected" })} view="owner" />);
    expect(screen.getByRole("note")).toHaveTextContent("Trip not approved yet");
    cleanup();
    render(<TripItinerary trip={sourceTrip({ travel_status: "cancelled" })} view="owner" />);
    expect(screen.getByRole("note")).toHaveTextContent("This trip is cancelled");
  });

  it("an empty trip has no note -- there are no appointments for it to be about", () => {
    render(<TripItinerary trip={trip({ approval_status: "submitted" })} view="owner" />);
    expect(screen.queryByRole("note")).toBeNull();
  });
});

describe("TripProductivity (bdm-011 AC2, College §F)", () => {
  it("shows every figure, and says what can't be computed instead of a fabricated 0", () => {
    render(<TripProductivity metrics={metrics({ meetings_planned: 3, meetings_completed: 2, actual_cost: "3000.50", cost_per_completed_meeting: "1500.25",
      expected_leads: 15, expected_revenue: "1500.50", actual_leads: 4 })} />);
    const tile = (label: string) => screen.getByText(label, { selector: "dt" }).parentElement!;
    expect(tile("Meetings planned")).toHaveTextContent("3");
    expect(tile("Meetings completed")).toHaveTextContent("2");
    expect(tile("Estimated cost")).toHaveTextContent("₹2,500.00");
    expect(tile("Actual cost")).toHaveTextContent("₹3,000.50");
    expect(tile("Cost per completed meeting")).toHaveTextContent("₹1,500.25");
    expect(tile("Expected leads")).toHaveTextContent("15");
    expect(tile("Expected revenue")).toHaveTextContent("₹1,500.50");
    expect(tile("Actual leads")).toHaveTextContent("4");
    expect(tile("Actual revenue")).toHaveTextContent("Not tracked yet");
  });

  it("nothing completed or estimated reads as a sentence, not a number", () => {
    render(<TripProductivity metrics={metrics()} />);
    const tile = (label: string) => screen.getByText(label, { selector: "dt" }).parentElement!;
    expect(tile("Cost per completed meeting")).toHaveTextContent("No completed meetings yet");
    expect(tile("Expected leads")).toHaveTextContent("No estimates entered");
    expect(tile("Expected revenue")).toHaveTextContent("No estimates entered");
  });
});

describe("TripWorkspace sections (bdm-011)", () => {
  const ws = (view: "owner" | "manager", over = {}) =>
    render(<TripWorkspace initialTrip={trip(over)} view={view} today="2026-10-03" backHref="/x" backLabel="Back" />);

  it("has the reminder's deep-link targets: appointments, costs and remarks", () => {
    const { container } = ws("owner");
    for (const id of ["trip-appointments", "trip-costs", "trip-remarks"]) expect(container.querySelector(`section#${id}`)).not.toBeNull();
    expect(screen.getByRole("heading", { name: "Appointments" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Productivity" })).toBeInTheDocument();
  });

  it("offers the travel report only once the trip is completed", () => {
    ws("owner");
    expect(screen.queryByRole("link", { name: "View travel report" })).toBeNull();
    cleanup();
    ws("owner", { travel_status: "completed", approval_status: "approved" });
    expect(screen.getByRole("link", { name: "View travel report" })).toHaveAttribute("href", "/bdm/travel/t1/report");
    cleanup();
    ws("manager", { travel_status: "completed", approval_status: "approved" });
    expect(screen.getByRole("link", { name: "View travel report" })).toHaveAttribute("href", "/bdm/manager/trips/t1/report");
  });
});
