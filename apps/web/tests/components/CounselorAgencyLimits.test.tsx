import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CounselorEvaluationPanel from "@/components/CounselorEvaluationPanel";
import CounselorVisaPanel from "@/components/CounselorVisaPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown) => Promise.resolve({ ok: true, status: 200, json: async () => body });
const ROWS = [
  { id: "agency1", student: "Priya", university: "U1", reference: null, status: "status_tracking", next_action: null, is_agency: true },
  { id: "direct1", student: "Ravi", university: "U1", reference: null, status: "status_tracking", next_action: null, is_agency: false },
];

describe("counselor limits on agency applications (H12)", () => {
  // ccrm-027 (DEC-SCOPE-262, E3): no card advances to Enrolled; both confirm it through the Enrolment panel (CC4: agency too).
  it("never offers Enrolled as a stage, on agency or direct applications, and offers Enrolment instead", async () => {  // AC20
    vi.stubGlobal("fetch", vi.fn(() => json({ rows: ROWS })));
    render(<CounselorEvaluationPanel />);
    for (const name of ["Priya", "Ravi"]) {
      const card = (await screen.findByRole("heading", { name })).closest(".card") as HTMLElement;
      expect(within(card).queryByRole("button", { name: "Advance stage" })).toBeNull();
      expect(within(card).getByText("No further stage to advance to.")).toBeInTheDocument();
      expect(within(card).getByRole("button", { name: "Enrolment" })).toBeInTheDocument();
    }
  });

  it("offers every later stage but Enrolled on an agency application at Offer", async () => {  // T16
    vi.stubGlobal("fetch", vi.fn(() => json({ rows: [{ ...ROWS[0], status: "offer" }] })));
    render(<CounselorEvaluationPanel />);
    const agency = (await screen.findByRole("heading", { name: "Priya" })).closest(".card") as HTMLElement;
    fireEvent.click(within(agency).getByRole("button", { name: "Advance stage" }));
    expect(Array.from((within(agency).getByLabelText("Advance to") as HTMLSelectElement).options).map((o) => o.value)).toEqual(["visa_documentation", "status_tracking"]);
  });

  it("offers no visa stage once the agency case is locked, and shows the reason", async () => {  // AC21
    const locked = "The visa decision is recorded, so this case can no longer be changed";
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/counselor/applications")) return json({ rows: [ROWS[0]] });
      if (url.includes("/visa-checklist")) return json({ exists: true, id: "v1", status: "decision", checklist: [], locked_reason: locked });
      return json({ exists: true, status: "decision", appointment_date: null, tracking_reference: null, disclaimer: "" });
    }));
    render(<CounselorVisaPanel />);
    const card = (await screen.findByRole("heading", { name: "Priya" })).closest(".card") as HTMLElement;
    expect(await within(card).findByText(locked)).toBeInTheDocument();
    expect(within(card).queryByRole("form", { name: "Visa case" })).toBeNull();
  });

  // ccrm-026 (DEC-SCOPE-254): the stage buttons became the Appendix A "Next status" choice -- still forward only.
  it("offers only later visa statuses on an open agency case", async () => {  // AC21
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/counselor/applications")) return json({ rows: [ROWS[0]] });
      if (url.includes("/visa-checklist")) return json({ exists: true, id: "v1", status: "tracking", visa_status: "decision_pending", checklist: [], locked_reason: null });
      return json({ exists: true, status: "tracking", appointment_date: null, tracking_reference: null, disclaimer: "" });
    }));
    render(<CounselorVisaPanel />);
    const card = (await screen.findByRole("heading", { name: "Priya" })).closest(".card") as HTMLElement;
    const select = (await within(card).findByLabelText("Next status")) as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.value)).toEqual(["", "additional_info_requested", "approved", "refused", "withdrawn"]);
  });
});
