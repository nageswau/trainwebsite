import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import TripActions from "@/components/TripActions";
import TripDecision from "@/components/TripDecision";
import TripForm from "@/components/TripForm";
import TripRemarks from "@/components/TripRemarks";
import TripTable from "@/components/TripTable";
import MyTrips from "@/app/bdm/travel/page";
import TravelListLoading from "@/app/bdm/travel/loading";
import TripLoading from "@/app/bdm/travel/[id]/loading";
import QueueLoading from "@/app/bdm/manager/approvals/loading";
import ManagerTripLoading from "@/app/bdm/manager/trips/[id]/loading";
import AdminQueueLoading from "@/app/admin/bdm-travel-approvals/loading";
import PortalLoading from "@/components/PortalLoading";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { elements } from "@/tests/helpers/elementTree";

import { json, row, trip } from "./tripFixtures";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const TODAY = "2026-10-03";
function fill(values: Record<string, string>) {
  for (const [label, value] of Object.entries(values)) fireEvent.change(screen.getByLabelText(label), { target: { value } });
}
const VALID = { From: "Hyderabad", To: "Vijayawada", Purpose: "College visits", "Estimated cost (₹)": "2500" };

describe("bdm-010 browser QA fixes (components)", () => {
  it("QA10-03: after a 409 the reject form closes once the trip can no longer be decided; the message stays", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "This trip is still a draft and can't be decided" }, 409)));
    const { rerender } = render(<TripDecision trip={trip({ can_decide: true })} />);
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    fireEvent.change(screen.getByLabelText("Reason for rejecting"), { target: { value: "Combine trips" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm reject" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("still a draft");
    rerender(<TripDecision trip={trip({ can_decide: false, approval_status: "draft" })} />); // the re-read trip
    expect(screen.queryByLabelText("Reason for rejecting")).toBeNull();
    expect(screen.getByRole("alert")).toHaveTextContent("still a draft");
  });

  it("QA10-06: the pressed action says Saving… while its request runs", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => undefined)));
    render(<TripActions trip={trip({ can_submit: true, can_cancel: true })} />);
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel trip" })).toBeDisabled();
  });

  it("QA10-07: a trip longer than 31 days is stopped next to Return date, and the picker caps it", () => {
    const mock = vi.fn();
    vi.stubGlobal("fetch", mock);
    render(<TripForm today={TODAY} />);
    fill({ ...VALID, "Travel date": "2026-10-10", "Return date": "2026-11-10" });
    expect(screen.getByLabelText("Return date")).toHaveAttribute("max", "2026-11-09");
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    expect(mock).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Return date")).toHaveAccessibleDescription("A trip can last at most 31 days");
  });

  it("QA10-07: the API's date rules land on their field", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "Travel date can be at most 30 days in the past" }, 422)));
    render(<TripForm today={TODAY} />);
    fill({ ...VALID, "Travel date": "2026-10-10", "Return date": "2026-10-10" });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(screen.getByLabelText("Travel date")).toHaveAttribute("aria-invalid", "true"));
    expect(screen.getByLabelText("Travel date")).toHaveAccessibleDescription("Travel date can be at most 30 days in the past");
  });

  it("QA10-08: a year longer than 4 digits is refused in plain words before sending", () => {
    const mock = vi.fn();
    vi.stubGlobal("fetch", mock);
    render(<TripForm today={TODAY} />);
    fill({ ...VALID, "Travel date": "20266-10-10", "Return date": "20266-10-10" });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    expect(mock).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Travel date")).toHaveAccessibleDescription("Enter a valid travel date");
  });

  it("QA10-11: the mode select keeps its own height in the grid", () => {
    render(<TripForm today={TODAY} />);
    expect(screen.getByLabelText("Mode of travel")).toHaveStyle({ alignSelf: "start" });
  });

  it("QA10-12: Status is the second column, so it shows on a phone before the table scrolls", () => {
    render(<TripTable page={{ items: [row()], total: 1, limit: 50, offset: 0 }} label="My trips" basePath="/bdm/travel" detailHref={(id) => id} />);
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Trip", "Status", "Dates", "Route", "Estimated", "Actual", "Mode"]);
  });

  it("QA10-14: the remarks field is named Remarks without repeating the section heading on screen", () => {
    render(<TripRemarks trip={trip()} />);
    expect(screen.getByRole("textbox", { name: "Remarks" })).toBeInTheDocument();
    expect(screen.getByText("Remarks", { selector: "label" })).toHaveClass("visually-hidden");
  });

  it("QA10-17: the form renders disabled until it is interactive, so early typing can't be wiped", () => {
    expect(renderToString(<TripForm today={TODAY} />)).toMatch(/<fieldset[^>]*disabled/);
    render(<TripForm today={TODAY} />);
    expect(screen.getByLabelText("From")).toBeEnabled();
  });

  it("QA10-17 follow-up: the remarks box (also server-rendered) is disabled until interactive, too", () => {
    expect(renderToString(<TripRemarks trip={trip({ remarks: "x" })} />)).toMatch(/<fieldset[^>]*disabled/);
    render(<TripRemarks trip={trip()} />);
    expect(screen.getByRole("textbox", { name: "Remarks" })).toBeEnabled();
  });

  it("QA10-05: empty-state links look like links", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/bdm/me"
      ? { full_name: "Asha", bdm_profile: { bdm_type: "college", reporting_manager: { full_name: "Meera" } } }
      : { items: [], total: 0, limit: 50, offset: 0 }) as never);
    const links = elements(await MyTrips({ searchParams: Promise.resolve({}) })).filter((el) => el.props.href === "/bdm/travel/new");
    expect(links.some((el) => el.props.className === "text-link")).toBe(true);
  });

  it("QA10-15: loading skeletons show a neutral label, not a guessed role", () => {
    for (const Loading of [TravelListLoading, TripLoading, QueueLoading, ManagerTripLoading, AdminQueueLoading]) {
      const loading = Loading();
      expect(loading.type).toBe(PortalLoading);
      const shell = elements(PortalLoading(loading.props)).find((el) => el.type === PortalShell)!;
      expect(shell.props.roleLabel).toBe("Loading…");
    }
  });
});
