import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolSkillAttendance from "@/components/SchoolSkillAttendance";

import { detail, enrolment, json, stubFetch } from "./skillFixtures";

// ENH-011 spec §7: sessions and per-session attendance -- labelled checkboxes for the students who can still be marked, Mark all
// present, an unsaved-changes warning, and a read-only view on a closed batch.
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const SESSION = { id: "ss1", session_date: "2026-10-05", topic: "Body language", attendance: [{ enrollment_id: "e1", present: true }] };
const withSession = (over = {}) =>
  detail({ sessions: [SESSION], enrollments: [enrolment("1"), enrolment("2"), enrolment("3", { status: "certified" }), enrolment("4", { frozen: true })], ...over });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("SchoolSkillAttendance", () => {
  it("explains what a session is for when there are none", () => {
    render(<SchoolSkillAttendance batch={detail()} />);
    expect(screen.getByText(/No sessions yet/)).toBeTruthy();
  });

  it("adds a session within the batch's dates", async () => {
    const fetchMock = stubFetch(() => json({ id: "ss2", session_date: "2026-10-12", topic: null, attendance: [] }, 201));
    render(<SchoolSkillAttendance batch={detail()} />);
    const date = screen.getByLabelText("Session date");
    expect(date.getAttribute("min")).toBe("2026-10-01");
    expect(date.getAttribute("max")).toBe("2026-12-01");
    fireEvent.change(date, { target: { value: "2026-10-12" } });
    fireEvent.click(screen.getByRole("button", { name: "Add session" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/school/career-counselor/skill-batches/b1/sessions");
    expect(JSON.parse(String(init?.body))).toEqual({ session_date: "2026-10-12", topic: null });
  });

  it("lists only students who can still be marked, with their saved marks", () => {
    render(<SchoolSkillAttendance batch={withSession()} />);
    const roster = screen.getByRole("group", { name: /Attendance for/ });
    expect((within(roster).getByLabelText("Student 1") as HTMLInputElement).checked).toBe(true);
    expect((within(roster).getByLabelText("Student 2") as HTMLInputElement).checked).toBe(false);
    expect(within(roster).queryByLabelText("Student 3")).toBeNull();
    expect(within(roster).queryByLabelText("Student 4")).toBeNull();
  });

  it("marks all present, warns about unsaved changes, and saves every listed student", async () => {
    const fetchMock = stubFetch(() => json({ ...SESSION, attendance: [{ enrollment_id: "e1", present: true }, { enrollment_id: "e2", present: true }] }));
    const add = vi.spyOn(window, "addEventListener");
    render(<SchoolSkillAttendance batch={withSession()} />);
    expect(screen.queryByText("Unsaved changes")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Mark all present" }));
    expect(screen.getByText("Unsaved changes")).toBeTruthy();
    expect(add.mock.calls.some(([type]) => type === "beforeunload")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/school/career-counselor/skill-sessions/ss1/attendance");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ records: [{ enrollment_id: "e1", present: true }, { enrollment_id: "e2", present: true }] });
    add.mockRestore();
  });

  it("keeps the marks when saving fails", async () => {
    stubFetch(() => json({ detail: "This batch is closed. Reopen it to make this change." }, 409));
    render(<SchoolSkillAttendance batch={withSession()} />);
    fireEvent.click(screen.getByLabelText("Student 2"));
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    expect((await screen.findByRole("alert")).textContent).toContain("closed");
    expect((screen.getByLabelText("Student 2") as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText("Unsaved changes")).toBeTruthy();
  });

  it("is read-only on a closed batch", () => {
    render(<SchoolSkillAttendance batch={withSession({ status: "closed" })} />);
    expect(screen.queryByRole("button", { name: "Add session" })).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.getByText("Student 1: Present")).toBeTruthy();
    expect(screen.getByText("Student 2: Not marked")).toBeTruthy();
  });
});
