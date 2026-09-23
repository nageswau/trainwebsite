import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolActivitiesPanel from "@/components/SchoolActivitiesPanel";
import { NOT_COMPLETED } from "@/lib/apiErrors";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const TIER_403 = "This school's Gold partnership does not include Monthly campus visits (requires Platinum or higher).";
const ACTIVITIES = [{ id: "a1", title: "Visit", scheduled_at: "2026-10-01T10:00:00Z" }];
const STUDENTS = [{ id: "s1", full_name: "Asha" }];

function card(heading: string): HTMLElement {
  return screen.getByRole("heading", { name: heading }).closest(".action-card") as HTMLElement;
}

function schedule() {
  fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Campus visit" } });
  fireEvent.change(screen.getByLabelText(/date & time/i), { target: { value: "2026-10-01T10:00" } });
  fireEvent.change(screen.getByLabelText(/entitlement category/i), { target: { value: "campus_visit" } });
  fireEvent.click(screen.getByRole("button", { name: "Schedule activity" }));
}

// ENH-022: a partnership-tier 403 (or any failed save) is announced as an alert beside the form that failed.
describe("SchoolActivitiesPanel save failures", () => {
  it("shows the tier 403 as an alert inside the schedule card and keeps the input", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: TIER_403 }) }));
    render(<SchoolActivitiesPanel activities={[]} students={[]} />);
    schedule();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(TIER_403);
    expect(within(card("Schedule an activity")).getByRole("alert")).toBe(alert);
    expect(screen.getByLabelText("Title")).toHaveValue("Campus visit");
  });

  it("recovers from a network failure instead of staying on Scheduling…", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<SchoolActivitiesPanel activities={[]} students={[]} />);
    schedule();
    expect(await screen.findByRole("alert")).toHaveTextContent(NOT_COMPLETED);
    expect(screen.getByRole("button", { name: "Schedule activity" })).toBeEnabled();
  });

  it("shows an attendance failure in the attendance card, not the schedule card", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: TIER_403 }) }));
    render(<SchoolActivitiesPanel activities={ACTIVITIES} students={STUDENTS} />);
    fireEvent.click(screen.getByRole("button", { name: "Mark attendance" }));
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    const alert = await screen.findByRole("alert");
    expect(within(card("Mark attendance")).getByRole("alert")).toBe(alert);
    expect(within(card("Schedule an activity")).queryByRole("alert")).toBeNull();
  });

  it("does not show an old attendance error again after Cancel and re-open (QA-022-01)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: TIER_403 }) }));
    render(<SchoolActivitiesPanel activities={[...ACTIVITIES, { id: "a2", title: "Seminar", scheduled_at: "2026-10-02T10:00:00Z" }]} students={STUDENTS} />);
    fireEvent.click(screen.getAllByRole("button", { name: "Mark attendance" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Mark attendance" })[0]);
    expect(screen.queryByRole("alert")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Mark attendance" })[1]);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("announces success politely", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "a2", title: "Campus visit" }) }));
    render(<SchoolActivitiesPanel activities={[]} students={[]} />);
    schedule();
    expect(await screen.findByRole("status")).toHaveTextContent("Campus visit scheduled.");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
