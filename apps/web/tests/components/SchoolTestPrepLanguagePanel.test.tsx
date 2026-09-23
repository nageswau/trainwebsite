import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolTestPrepLanguagePanel from "@/components/SchoolTestPrepLanguagePanel";
import { NOT_COMPLETED } from "@/lib/apiErrors";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const IELTS_403 = "This school's Silver partnership does not include IELTS coaching (requires Gold or higher).";
const LANGUAGE_403 = "This school's Bronze partnership does not include Foreign language classes (requires Gold or higher).";
const STUDENTS = [{ id: "s1", full_name: "Asha", school_name: "Hill School" }];
const TEST_PREP = [{ id: "t1", school_student_id: "s1", test_type: "sat", mock_scores: [], target_score: null, actual_score: null, status: "in_progress" }];
const LANGUAGES = [{ id: "l1", school_student_id: "s1", language: "German", level: null, classes_attended: 3, assessment_score: null, certification_status: "in_progress" }];

function section(heading: string): HTMLElement {
  return screen.getByRole("heading", { name: heading }).closest(".card, .action-card") as HTMLElement;
}

function deny(detail: string) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail }) }));
}

function startPreparation() {
  fireEvent.change(within(section("Start test preparation")).getByLabelText("Student"), { target: { value: "s1" } });
  fireEvent.change(screen.getByLabelText("Test"), { target: { value: "ielts" } });
  fireEvent.click(screen.getByRole("button", { name: "Start preparation" }));
}

// ENH-022: a partnership-tier 403 (or any failed save) is announced as an alert beside the control that failed.
describe("SchoolTestPrepLanguagePanel save failures", () => {
  it("shows a start-preparation failure in its own card and keeps the input", async () => {
    deny(IELTS_403);
    render(<SchoolTestPrepLanguagePanel testPrepRecords={[]} languageRecords={[]} students={STUDENTS} />);
    fireEvent.change(screen.getByLabelText("Target score"), { target: { value: "7.5" } });
    startPreparation();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(IELTS_403);
    expect(within(section("Start test preparation")).getByRole("alert")).toBe(alert);
    expect(screen.getByLabelText("Target score")).toHaveValue("7.5");
  });

  it("shows a record-score failure in the test-preparation table card", async () => {
    deny(IELTS_403);
    render(<SchoolTestPrepLanguagePanel testPrepRecords={TEST_PREP} languageRecords={[]} students={STUDENTS} />);
    fireEvent.change(screen.getByLabelText("Actual score for Asha"), { target: { value: "1400" } });
    fireEvent.click(screen.getByRole("button", { name: "Record score" }));
    const alert = await screen.findByRole("alert");
    expect(within(section("Test preparation")).getByRole("alert")).toBe(alert);
  });

  it("shows language failures in the language cards, never in the test-prep cards", async () => {
    deny(LANGUAGE_403);
    render(<SchoolTestPrepLanguagePanel testPrepRecords={[]} languageRecords={LANGUAGES} students={STUDENTS} />);
    fireEvent.click(screen.getByRole("button", { name: "Mark certified" }));
    const certify = await screen.findByRole("alert");
    expect(within(section("Foreign language classes")).getByRole("alert")).toBe(certify);

    fireEvent.change(within(section("Start language classes")).getByLabelText("Student"), { target: { value: "s1" } });
    fireEvent.change(screen.getByLabelText("Language"), { target: { value: "French" } });
    fireEvent.click(screen.getByRole("button", { name: "Start classes" }));
    await within(section("Start language classes")).findByRole("alert");
    expect(within(section("Start test preparation")).queryByRole("alert")).toBeNull();
  });

  it("recovers from a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<SchoolTestPrepLanguagePanel testPrepRecords={[]} languageRecords={[]} students={STUDENTS} />);
    startPreparation();
    expect(await screen.findByRole("alert")).toHaveTextContent(NOT_COMPLETED);
    expect(screen.getByRole("button", { name: "Start preparation" })).toBeEnabled();
  });

  it("announces success politely", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "t2" }) }));
    render(<SchoolTestPrepLanguagePanel testPrepRecords={[]} languageRecords={[]} students={STUDENTS} />);
    startPreparation();
    expect(await screen.findByRole("status")).toHaveTextContent("IELTS preparation started.");
  });
});
