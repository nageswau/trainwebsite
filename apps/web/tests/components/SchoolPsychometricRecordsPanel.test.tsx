import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolPsychometricRecordsPanel from "@/components/SchoolPsychometricRecordsPanel";
import { NOT_COMPLETED } from "@/lib/apiErrors";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const EXPIRED_403 = "This school's partnership expired on 22 Sep 2026.";
const STUDENTS = [{ id: "s1", full_name: "Asha", school_name: "Hill School" }];
const RECORDS = [{ id: "r1", school_student_id: "s1", assessment_type: "Aptitude", report_url: null, status: "assigned", created_at: "2026-09-01T00:00:00Z" }];

function card(heading: string): HTMLElement {
  return screen.getByRole("heading", { name: heading }).closest(".action-card") as HTMLElement;
}

function assign() {
  fireEvent.change(screen.getByLabelText("Student"), { target: { value: "s1" } });
  fireEvent.change(screen.getByLabelText("Assessment type"), { target: { value: "Aptitude Test" } });
  fireEvent.click(screen.getByRole("button", { name: "Assign assessment" }));
}

// ENH-022: a partnership-tier 403 (or any failed save) is announced as an alert beside the form that failed.
describe("SchoolPsychometricRecordsPanel save failures", () => {
  it("shows an assign failure as an alert in the assign card and keeps the input", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: EXPIRED_403 }) }));
    render(<SchoolPsychometricRecordsPanel records={[]} students={STUDENTS} />);
    assign();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(EXPIRED_403);
    expect(within(card("Assign an assessment")).getByRole("alert")).toBe(alert);
    expect(screen.getByLabelText("Assessment type")).toHaveValue("Aptitude Test");
  });

  it("shows an attach-report failure in the attach card, not the assign card", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: EXPIRED_403 }) }));
    render(<SchoolPsychometricRecordsPanel records={RECORDS} students={STUDENTS} />);
    fireEvent.click(screen.getByRole("button", { name: "Attach report" }));
    fireEvent.change(screen.getByLabelText("Report URL"), { target: { value: "/r.pdf" } });
    fireEvent.click(screen.getByRole("button", { name: "Attach" }));
    const alert = await screen.findByRole("alert");
    expect(within(card("Attach report")).getByRole("alert")).toBe(alert);
    expect(within(card("Assign an assessment")).queryByRole("alert")).toBeNull();
  });

  it("recovers from a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<SchoolPsychometricRecordsPanel records={[]} students={STUDENTS} />);
    assign();
    expect(await screen.findByRole("alert")).toHaveTextContent(NOT_COMPLETED);
    expect(screen.getByRole("button", { name: "Assign assessment" })).toBeEnabled();
  });

  it("announces success politely", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "r2" }) }));
    render(<SchoolPsychometricRecordsPanel records={[]} students={STUDENTS} />);
    assign();
    expect(await screen.findByRole("status")).toHaveTextContent("Assessment assigned.");
  });
});
