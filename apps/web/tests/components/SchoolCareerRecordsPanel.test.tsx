import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { pickOption } from "../helpers/pickOption";
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
  pickOption(card, "Student", "s1");
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

// ENH-026: status column and inline edit (spec §11.2 F2/F3/F6).
describe("SchoolCareerRecordsPanel records table (ENH-026)", () => {
  const record = { id: "r1", school_student_id: "s1", record_type: "counselling_note", notes: "Met.", created_at: "2026-09-01T00:00:00Z", status: null, next_follow_up_date: null };

  // QA-12 (browser QA 2026-09-28): the Records card and the Add card touched; the panel now spaces its cards with a gap.
  it("lays its cards out with the spaced stack", () => {
    const { container } = render(<SchoolCareerRecordsPanel records={[record]} students={STUDENTS} />);
    expect(container.firstElementChild).toHaveClass("portal-content", "card-stack");
  });

  it("labels a record made before tracking", () => {
    render(<SchoolCareerRecordsPanel records={[record]} students={STUDENTS} />);
    expect(screen.getByText("No status (recorded before tracking)")).toBeInTheDocument();
  });

  // QA-15 (browser QA 2026-09-28): two records of one student produced two identical "Edit record for Asha" buttons, so a screen
  // reader user could not tell them apart. The name now carries the record's type and date.
  it("gives each Edit button a distinct accessible name", () => {
    const guidance = { ...record, id: "r2", record_type: "guidance_session", created_at: "2026-09-10T00:00:00Z" };
    render(<SchoolCareerRecordsPanel records={[record, guidance]} students={STUDENTS} />);
    expect(screen.getByRole("button", { name: "Edit counselling note of 01 Sept 2026 for Asha" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit guidance session of 10 Sept 2026 for Asha" })).toBeInTheDocument();
  });

  it("opens the edit form and returns focus to the Edit button on cancel", async () => {
    render(<SchoolCareerRecordsPanel records={[record]} students={STUDENTS} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit counselling note of 01 Sept 2026 for Asha" }));
    expect(screen.getByRole("heading", { name: "Edit record for Asha" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await vi.waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Edit counselling note of 01 Sept 2026 for Asha" })));
  });

  it("closes with Escape while focus is still on the edit heading (FV-01)", async () => {
    render(<SchoolCareerRecordsPanel records={[record]} students={STUDENTS} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit counselling note of 01 Sept 2026 for Asha" }));
    fireEvent.keyDown(screen.getByRole("heading", { name: "Edit record for Asha" }), { key: "Escape" });
    expect(screen.queryByRole("heading", { name: "Edit record for Asha" })).not.toBeInTheDocument();
    await vi.waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Edit counselling note of 01 Sept 2026 for Asha" })));
  });
});
