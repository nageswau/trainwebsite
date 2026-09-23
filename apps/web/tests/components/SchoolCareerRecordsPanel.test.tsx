import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolCareerRecordsPanel from "@/components/SchoolCareerRecordsPanel";
import { NOT_COMPLETED } from "@/lib/apiErrors";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const TIER_403 = "This school's Bronze partnership does not include Individual counselling (requires Silver or higher).";
const STUDENTS = [{ id: "s1", full_name: "Asha", school_name: "Hill School" }];

// Scoped to the "Add a record" card: the page also carries ENH-025's career-preferences card, which has its own "Student" select.
function save() {
  const card = within(screen.getByRole("heading", { name: "Add a record" }).closest(".action-card") as HTMLElement);
  fireEvent.change(card.getByLabelText("Student"), { target: { value: "s1" } });
  fireEvent.change(card.getByLabelText("Type"), { target: { value: "guidance_session" } });
  fireEvent.change(card.getByLabelText("Notes"), { target: { value: "Discussed options." } });
  fireEvent.click(card.getByRole("button", { name: "Save record" }));
}

// ENH-022: a partnership-tier 403 (or any failed save) is announced as an alert beside the form that failed.
describe("SchoolCareerRecordsPanel save failures", () => {
  it("shows the tier 403 as an alert inside the form card and keeps the notes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: TIER_403 }) }));
    render(<SchoolCareerRecordsPanel records={[]} students={STUDENTS} />);
    save();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(TIER_403);
    const card = screen.getByRole("heading", { name: "Add a record" }).closest(".action-card") as HTMLElement;
    expect(within(card).getByRole("alert")).toBe(alert);
    expect(screen.getByLabelText("Notes")).toHaveValue("Discussed options.");
  });

  it("recovers from a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<SchoolCareerRecordsPanel records={[]} students={STUDENTS} />);
    save();
    expect(await screen.findByRole("alert")).toHaveTextContent(NOT_COMPLETED);
    expect(screen.getByRole("button", { name: "Save record" })).toBeEnabled();
  });

  it("announces success politely", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "r1" }) }));
    render(<SchoolCareerRecordsPanel records={[]} students={STUDENTS} />);
    save();
    expect(await screen.findByRole("status")).toHaveTextContent("Record saved.");
  });
});
