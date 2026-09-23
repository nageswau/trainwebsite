import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolStudentDetailPanel from "@/components/SchoolStudentDetailPanel";
import { serverApi } from "@/lib/api";
import { loadPortfolio } from "@/lib/portfolio";

// ENH-005 -- the coordinator's student page gains an opt-in transfer request and history (spec §7.1, AC-25). `serverApi` reads next/headers
// cookies, so it is mocked and answers by path.
vi.mock("@/lib/api", () => ({ serverApi: vi.fn() }));
vi.mock("@/lib/portfolio", () => ({ loadPortfolio: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const student = { id: "s1", student_code: "A3F9C21B", full_name: "Aarav Mehta", date_of_birth: "2015-04-12", grade_or_class: "Grade 5" };
const SCHOOLS = [{ id: "b", name: "Lakeview School" }];
const HISTORY = { student: { id: "s1", full_name: "Aarav Mehta" }, history: [{ id: "t1", decided_at: "2026-09-21T10:00:00Z", from_school: { id: "a", name: "Sunrise School" }, to_school: { id: "b", name: "Lakeview School" } }] };
const PORTFOLIO = { student: { id: "s1", full_name: "Aarav Mehta" }, completion_percentage: 50, can_edit: true, profile_complete: false, academic_achievements: [], psychometric_report: [], career_guidance: [], languages: [], entries: {}, personal_statement: null };
const pendingFor = (studentId: string) => ({ items: [{ id: "r1", direction: "outgoing", status: "pending", student_id: studentId, student_code: "A3F9C21B", student_name: "Aarav Mehta", from_school: { id: "a", name: "Sunrise School" }, to_school: { id: "b", name: "Lakeview School" }, reason: null, decision_note: null, created_at: "2026-09-20T10:00:00Z", decided_at: null }], total: 1, limit: 100, offset: 0 });

type Overrides = { destinations?: unknown; pending?: unknown; history?: unknown; portfolio?: unknown };
function api(over: Overrides = {}) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    const pick = (key: keyof Overrides, fallback: unknown) => {
      const value = key in over ? over[key] : fallback;
      if (value instanceof Error) throw value;
      return value;
    };
    if (path.includes("transfer-destinations")) return pick("destinations", SCHOOLS) as never;
    if (path.includes("transfer-requests")) return pick("pending", { items: [], total: 0, limit: 100, offset: 0 }) as never;
    if (path.includes("transfer-history")) return pick("history", { student: HISTORY.student, history: [] }) as never;
    if (path.includes("grade-history")) return { student: HISTORY.student, history: [] } as never;
    return { events: [] } as never;
  });
  vi.mocked(loadPortfolio).mockImplementation(async () => {
    const value = "portfolio" in over ? over.portfolio : PORTFOLIO;
    if (value instanceof Error) throw value;
    return value as never;
  });
}
const paths = () => vi.mocked(serverApi).mock.calls.map(([p]) => String(p));
async function show(props: { showTransfer?: boolean; showGradeHistory?: boolean } = {}) {
  render(await SchoolStudentDetailPanel({ student, backHref: "/back", backLabel: "Back", ...props }));
}

afterEach(() => {
  cleanup();
  vi.mocked(serverApi).mockReset();
  vi.mocked(loadPortfolio).mockReset();
});

describe("SchoolStudentDetailPanel transfer wiring", () => {
  it("without showTransfer, renders no transfer UI and never reads a transfer endpoint (Principal and Teacher pages unchanged)", async () => {
    api();
    await show();
    expect(screen.queryByText("Request a transfer")).toBeNull();
    expect(screen.queryByText("Transfer history")).toBeNull();
    expect(paths().filter((p) => /transfer/.test(p))).toEqual([]);
  });

  it("with showTransfer, offers the request inside a collapsed disclosure right under the student header, before the record (browser QA N4)", async () => {
    api();
    await show({ showTransfer: true, showGradeHistory: true });
    const summary = screen.getByText("Request a transfer");
    expect(summary.closest("summary")).toBeTruthy(); // the text is wrapped in <strong> inside the <summary>
    const details = summary.closest("details") as HTMLDetailsElement;
    expect(details).toBeTruthy();
    expect(details.open).toBe(false); // a rare, consequential action: findable, but not competing with the record
    expect(screen.getByLabelText("Destination school")).toBeTruthy();
    const header = screen.getByRole("heading", { name: /Aarav Mehta/ });
    const before = (later: HTMLElement) => header.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING;
    expect(before(summary)).toBeTruthy(); // after the student's own header...
    for (const later of [screen.getByText("Journey timeline"), screen.getByRole("heading", { name: "Grade history" })]) {
      expect(summary.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy(); // ...and ahead of the timeline and grade history
    }
  });

  it("shows the pending request in the header and in place of the form", async () => {
    api({ pending: pendingFor("s1") });
    await show({ showTransfer: true });
    expect(screen.getByText("Transfer requested")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toMatch(/Transfer to Lakeview School requested/);
    expect(screen.queryByLabelText("Destination school")).toBeNull();
  });

  it("ignores a pending request that belongs to a different student", async () => {
    api({ pending: pendingFor("someone-else") });
    await show({ showTransfer: true });
    expect(screen.queryByText("Transfer requested")).toBeNull();
    expect(screen.getByLabelText("Destination school")).toBeTruthy();
  });

  it("shows the transfer history card only when there is a transfer", async () => {
    api({ history: HISTORY });
    await show({ showTransfer: true });
    expect(screen.getByRole("heading", { name: "Transfer history" })).toBeTruthy();
    expect(screen.getByText("Moved from Sunrise School to Lakeview School")).toBeTruthy();
    cleanup();
    api();
    await show({ showTransfer: true });
    expect(screen.queryByText("Transfer history")).toBeNull();
  });

  it("keeps failures visible instead of hiding the feature", async () => {
    api({ destinations: new Error("500"), history: new Error("500") });
    await show({ showTransfer: true });
    expect(screen.getByText("Transfers are unavailable right now.")).toBeTruthy();
    expect(screen.getByText("Transfer history is unavailable right now.")).toBeTruthy();
  });

  it("still offers the form when only the pending lookup fails (the server refuses a duplicate anyway)", async () => {
    api({ pending: new Error("500") });
    await show({ showTransfer: true });
    expect(screen.getByLabelText("Destination school")).toBeTruthy();
  });
});

describe("SchoolStudentDetailPanel profile (ENH-025)", () => {
  const master = { gender: "female", section: "A", roll_number: null, student_mobile: null, city: "Pune", subjects: ["Maths", "Physics"], career_interests: null, global_education_interest: false, preferred_countries: null, preferred_courses: null, has_photo: false };

  it("shows the Student Master profile with 'Not recorded' for empty values and no photo controls by default", async () => {
    api();
    render(await SchoolStudentDetailPanel({ student: { ...student, ...master }, backHref: "/back", backLabel: "Back" }));
    expect(screen.getByText("Female")).toBeTruthy();
    expect(screen.getByText("Maths, Physics")).toBeTruthy();
    expect(screen.getByText("No")).toBeTruthy();
    // roll number, mobile, career interests, preferred countries, preferred courses
    expect(screen.getAllByText("Not recorded").length).toBe(5);
    expect(screen.getByRole("img", { name: "No photo for Aarav Mehta" })).toBeTruthy();
    expect(screen.queryByLabelText(/upload a photo/i)).toBeNull();
  });

  it("offers photo controls only when canEditPhoto is set", async () => {
    api();
    render(await SchoolStudentDetailPanel({ student: { ...student, ...master }, backHref: "/back", backLabel: "Back", canEditPhoto: true }));
    expect(screen.getByLabelText(/upload a photo/i)).toBeTruthy();
  });

  it("still renders a student record that predates the new fields", async () => {
    api();
    await show();
    expect(screen.getByRole("img", { name: "No photo for Aarav Mehta" })).toBeTruthy();
    expect(screen.getAllByText("Not recorded").length).toBe(10);
  });
});
