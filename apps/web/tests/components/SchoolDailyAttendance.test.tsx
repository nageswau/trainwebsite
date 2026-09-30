import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolDailyAttendance, { type DailyRoster } from "@/components/SchoolDailyAttendance";
import { SCHOOL_NAV } from "@/lib/navigation";

import { json, stubFetch } from "./skillFixtures";

// ENH-030 spec §6: one fieldset of four labelled radios per assigned student, no default for an unmarked student (C2), Mark all
// present fills only unmarked rows, one Save for the class, messages under the form, unsaved-changes flag, server-provided "today".
const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

const ROSTER: DailyRoster = {
  session_date: "2026-09-29",
  today: "2026-09-30",
  students: [
    { id: "s1", full_name: "Asha Rao", grade_or_class: "Grade 5-A", status: "absent" },
    { id: "s2", full_name: "Ben Das", grade_or_class: "Grade 5-A", status: null },
  ],
};
const group = (name: string) => screen.getByRole("group", { name: new RegExp(name) });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  push.mockReset();
  refresh.mockReset();
});

describe("SchoolDailyAttendance", () => {
  it("prefills saved marks and leaves unmarked students unselected", () => {
    render(<SchoolDailyAttendance roster={ROSTER} />);
    expect((within(group("Asha Rao")).getByLabelText("Absent") as HTMLInputElement).checked).toBe(true);
    expect(within(group("Ben Das")).getAllByRole("radio").some((r) => (r as HTMLInputElement).checked)).toBe(false);
    expect(within(group("Ben Das")).getByText("Not marked")).toBeTruthy();
    expect(screen.queryByText("Unsaved changes")).toBeNull();
  });

  it("caps the date at the server's today", () => {
    render(<SchoolDailyAttendance roster={ROSTER} />);
    expect(screen.getByLabelText("Date").getAttribute("max")).toBe("2026-09-30");
  });

  it("lets a date be typed without navigating, then shows it on request (final review I2: keyboard entry)", () => {
    render(<SchoolDailyAttendance roster={ROSTER} />);
    const date = screen.getByLabelText("Date") as HTMLInputElement;
    // Keyboard entry fires change per segment ("1", then "15"); none of these may navigate or disable the field.
    fireEvent.change(date, { target: { value: "2026-09-01" } });
    fireEvent.change(date, { target: { value: "2026-09-15" } });
    expect(push).not.toHaveBeenCalled();
    expect(date.value).toBe("2026-09-15");
    expect(date.disabled).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Show" }));
    expect(push).toHaveBeenCalledWith("/school/teacher/attendance?date=2026-09-15");
  });

  it("shows the chosen date on Enter (form submit) and ignores the current date", () => {
    render(<SchoolDailyAttendance roster={ROSTER} />);
    const date = screen.getByLabelText("Date");
    fireEvent.submit(date.closest("form")!);
    expect(push).not.toHaveBeenCalled();
    fireEvent.change(date, { target: { value: "2026-09-28" } });
    fireEvent.submit(date.closest("form")!);
    expect(push).toHaveBeenCalledWith("/school/teacher/attendance?date=2026-09-28");
  });

  it("asks before leaving the date with unsaved marks", () => {
    const confirm = vi.fn(() => false);
    vi.stubGlobal("confirm", confirm);
    render(<SchoolDailyAttendance roster={ROSTER} />);
    fireEvent.click(within(group("Ben Das")).getByLabelText("Late"));
    expect(screen.getByText("Unsaved changes")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-09-28" } });
    fireEvent.click(screen.getByRole("button", { name: "Show" }));
    expect(confirm).toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });

  it("shows how many students are marked (spec §11 F2)", () => {
    render(<SchoolDailyAttendance roster={ROSTER} />);
    expect(screen.getByText("1 of 2 students marked")).toBeTruthy();
    fireEvent.click(within(group("Ben Das")).getByLabelText("Present"));
    expect(screen.getByText("2 of 2 students marked")).toBeTruthy();
  });

  it("Mark all present fills only unmarked students", () => {
    render(<SchoolDailyAttendance roster={ROSTER} />);
    fireEvent.click(screen.getByRole("button", { name: "Mark all present" }));
    expect((within(group("Asha Rao")).getByLabelText("Absent") as HTMLInputElement).checked).toBe(true);
    expect((within(group("Ben Das")).getByLabelText("Present") as HTMLInputElement).checked).toBe(true);
  });

  it("saves the whole class in one PUT and confirms", async () => {
    const fetchMock = stubFetch(() => json({ ...ROSTER, students: ROSTER.students.map((s) => ({ ...s, status: s.status ?? "present" })) }));
    render(<SchoolDailyAttendance roster={ROSTER} />);
    fireEvent.click(screen.getByRole("button", { name: "Mark all present" }));
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/school/attendance");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ session_date: "2026-09-29", records: [{ student_id: "s1", status: "absent" }, { student_id: "s2", status: "present" }] });
    expect(screen.getByRole("status").textContent).toMatch(/Attendance saved for 2 students on/);
  });

  it("sends only chosen students and says how many are left unmarked", async () => {
    const fetchMock = stubFetch(() => json(ROSTER));
    render(<SchoolDailyAttendance roster={ROSTER} />);
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body)).records).toEqual([{ student_id: "s1", status: "absent" }]);
    expect(screen.getByRole("status").textContent).toMatch(/1 student on .* 1 left unmarked\./);
  });

  it("keeps the marks and shows the server's reason when a save fails", async () => {
    stubFetch(() => json({ detail: "One or more students are not assigned to you" }, 403));
    render(<SchoolDailyAttendance roster={ROSTER} />);
    fireEvent.click(within(group("Ben Das")).getByLabelText("Late"));
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("One or more students are not assigned to you"));
    expect((within(group("Ben Das")).getByLabelText("Late") as HTMLInputElement).checked).toBe(true);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("does not send a request when nothing is chosen", () => {
    const fetchMock = stubFetch(() => json(ROSTER));
    render(<SchoolDailyAttendance roster={{ ...ROSTER, students: [{ ...ROSTER.students[1] }] }} />);
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toBe("Choose a status for at least one student.");
  });

  it("disables the form while saving", async () => {
    let resolve: (r: Response) => void = () => {};
    stubFetch(() => new Promise<Response>((r) => { resolve = r; }));
    render(<SchoolDailyAttendance roster={ROSTER} />);
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    expect(screen.getByRole("button", { name: "Saving…" }).hasAttribute("disabled")).toBe(true);
    expect((screen.getByLabelText("Date") as HTMLInputElement).disabled).toBe(true);
    resolve(json(ROSTER));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save attendance" })).toBeTruthy());
  });

  it("explains an empty class", () => {
    render(<SchoolDailyAttendance roster={{ ...ROSTER, students: [] }} />);
    expect(screen.getByRole("status").textContent).toBe("No students assigned to you yet. Your School Coordinator assigns students to teachers.");
  });

  it("adds Attendance to the teacher's navigation only", () => {
    expect(SCHOOL_NAV.teacher.map((i) => [i.label, i.href])).toEqual([["Dashboard", "/school/teacher/dashboard"], ["Attendance", "/school/teacher/attendance"]]);
    expect(SCHOOL_NAV.parent.map((i) => i.label)).toEqual(["Dashboard", "Notifications"]);
  });
});
