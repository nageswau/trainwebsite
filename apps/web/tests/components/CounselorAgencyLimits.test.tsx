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
  it("never offers Enrolled on an agency application, and says why", async () => {  // AC20
    vi.stubGlobal("fetch", vi.fn(() => json({ rows: ROWS })));
    render(<CounselorEvaluationPanel />);
    const agency = (await screen.findByRole("heading", { name: "Priya" })).closest(".card") as HTMLElement;
    expect(within(agency).getByText("Enrollment is confirmed by the agency.")).toBeInTheDocument();
    expect(within(agency).queryByRole("button", { name: "Advance stage" })).toBeNull();
    const direct = screen.getByRole("heading", { name: "Ravi" }).closest(".card") as HTMLElement;
    fireEvent.click(within(direct).getByRole("button", { name: "Advance stage" }));
    expect(Array.from((within(direct).getByLabelText("Advance to") as HTMLSelectElement).options).map((o) => o.value)).toEqual(["enrolled"]);
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
    expect(within(card).queryByRole("button", { name: /^Advance to/ })).toBeNull();
  });

  it("offers only later visa stages on an open agency case", async () => {  // AC21
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/counselor/applications")) return json({ rows: [ROWS[0]] });
      if (url.includes("/visa-checklist")) return json({ exists: true, id: "v1", status: "interview_prep", checklist: [], locked_reason: null });
      return json({ exists: true, status: "interview_prep", appointment_date: null, tracking_reference: null, disclaimer: "" });
    }));
    render(<CounselorVisaPanel />);
    const card = (await screen.findByRole("heading", { name: "Priya" })).closest(".card") as HTMLElement;
    const buttons = await within(card).findAllByRole("button", { name: /^Advance to/ });
    expect(buttons.map((b) => b.textContent)).toEqual(["Advance to Tracking", "Advance to Decision"]);
  });
});
