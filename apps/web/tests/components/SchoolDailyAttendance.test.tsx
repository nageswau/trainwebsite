import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolDailyAttendance, { type DailyRoster } from "@/components/SchoolDailyAttendance";
import { SCHOOL_NAV } from "@/lib/navigation";

import { json, stubFetch } from "./skillFixtures";

// ENH-030 spec §6: one fieldset of four labelled radios per assigned student, no default for an unmarked student (C2), Mark all
// present fills only unmarked rows, one Save for the class, messages under the form, unsaved-changes flag, server-provided "today".
const push = vi.fn();
const refresh = vi.fn();
const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh, replace }) }));

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
    // (The scope refusal has its own wording and refresh since review I-2; any other refusal shows the server's reason as-is.)
    stubFetch(() => json({ detail: "Attendance cannot be marked for a future date" }, 422));
    render(<SchoolDailyAttendance roster={ROSTER} />);
    fireEvent.click(within(group("Ben Das")).getByLabelText("Late"));
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("Attendance cannot be marked for a future date"));
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
    render(<SchoolDailyAttendance roster={{ ...ROSTER, session_date: ROSTER.today, students: [] }} />);
    expect(screen.getByRole("status").textContent).toBe("No students assigned to you yet. Your School Coordinator assigns students to teachers.");
  });

  // --- Browser QA 2026-09-30 --------------------------------------------------------------------------------------------------

  it("QA30-01: refuses to save while the Date field shows a date that is not the one on screen", async () => {
    const fetchMock = stubFetch(() => json(ROSTER));
    render(<SchoolDailyAttendance roster={ROSTER} />);
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-09-10" } });
    fireEvent.click(within(group("Ben Das")).getByLabelText("Late"));
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/Press Show to open 10 Sept 2026/));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(document.querySelector(".form-warning")?.textContent).toBe("Showing 29 Sept 2026. Press Show to open 10 Sept 2026."); // shown before Save too
  });

  it("QA30-01: saving works again once the field matches the date on screen", async () => {
    const fetchMock = stubFetch(() => json(ROSTER));
    render(<SchoolDailyAttendance roster={ROSTER} />);
    const date = screen.getByLabelText("Date");
    fireEvent.change(date, { target: { value: "2026-09-10" } });
    fireEvent.change(date, { target: { value: "2026-09-29" } });
    expect(screen.queryByText(/Press Show to open/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it("QA30-02 / review I-1: a history move (Back, Forward, any distance) with unsaved marks asks; staying restores this page's URL", () => {
    const confirm = vi.fn(() => false);
    vi.stubGlobal("confirm", confirm);
    const go = vi.spyOn(window.history, "go");
    const router = vi.fn(); // stands in for Next's own (non-capture) popstate listener
    window.addEventListener("popstate", router);
    try {
      render(<SchoolDailyAttendance roster={ROSTER} />);
      fireEvent.click(within(group("Ben Das")).getByLabelText("Late"));
      // Back, Forward or a multi-step jump all arrive as one popstate: each one asks, and staying never assumes a direction --
      // the router is told to show this page's own URL again (no history.go guess, no swallowed follow-up event).
      for (let move = 1; move <= 2; move += 1) {
        window.dispatchEvent(new PopStateEvent("popstate"));
        expect(confirm).toHaveBeenCalledTimes(move);
        expect(router).not.toHaveBeenCalled();
        expect(replace).toHaveBeenLastCalledWith("/school/teacher/attendance?date=2026-09-29", { scroll: false });
      }
      expect(go).not.toHaveBeenCalled();
      expect(within(group("Ben Das")).getByLabelText("Late")).toBeChecked(); // the marks survive
      // Leaving on purpose: confirm -> the router handles the move.
      confirm.mockReturnValue(true);
      window.dispatchEvent(new PopStateEvent("popstate"));
      expect(router).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener("popstate", router);
      go.mockRestore();
      replace.mockReset();
    }
  });

  it("QA30-02: Back without unsaved marks is not interrupted", () => {
    const confirm = vi.fn(() => false);
    vi.stubGlobal("confirm", confirm);
    const router = vi.fn();
    window.addEventListener("popstate", router);
    try {
      render(<SchoolDailyAttendance roster={ROSTER} />);
      window.dispatchEvent(new PopStateEvent("popstate"));
      expect(confirm).not.toHaveBeenCalled();
      expect(router).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener("popstate", router);
    }
  });

  it("QA30-04: right after a save, the saved marks are current -- no stale 'Unsaved changes' or 'Not marked'", async () => {
    const savedRoster = { ...ROSTER, students: [{ ...ROSTER.students[0] }, { ...ROSTER.students[1], status: "late" as const }] };
    stubFetch(() => json(savedRoster));
    render(<SchoolDailyAttendance roster={ROSTER} />); // router.refresh() is mocked: the props never change in this test
    fireEvent.click(within(group("Ben Das")).getByLabelText("Late"));
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toMatch(/Attendance saved/));
    expect(screen.queryByText("Unsaved changes")).toBeNull();
    expect(screen.queryByText("Not marked")).toBeNull();
  });

  it("QA30-04: a student who appears after a refresh does not count as an unsaved change", () => {
    const { rerender } = render(<SchoolDailyAttendance roster={ROSTER} />);
    rerender(<SchoolDailyAttendance roster={{ ...ROSTER, students: [...ROSTER.students, { id: "s3", full_name: "New Kid", grade_or_class: null, status: null }] }} />);
    expect(screen.getByRole("group", { name: /New Kid/ })).toBeTruthy();
    expect(screen.queryByText("Unsaved changes")).toBeNull();
  });

  it("review I-2: a save refused because the class list changed refreshes the list in place and keeps the marks", async () => {
    stubFetch(() => json({ detail: "One or more students are not assigned to you" }, 403));
    render(<SchoolDailyAttendance roster={ROSTER} />);
    fireEvent.click(within(group("Ben Das")).getByLabelText("Late"));
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe("Your class list changed since this page was opened, so nothing was saved. The list has been updated — check the marks and save again."),
    );
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(within(group("Ben Das")).getByLabelText("Late")).toBeChecked();
  });

  it("review I-2: a busy class (409) also refreshes and keeps the server's own words", async () => {
    stubFetch(() => json({ detail: "This class's attendance is being changed elsewhere. Try again." }, 409));
    render(<SchoolDailyAttendance roster={ROSTER} />);
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("This class's attendance is being changed elsewhere. Try again."));
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("review I-2: other refusals (e.g. the partnership tier) do not refresh", async () => {
    stubFetch(() => json({ detail: "This school has no active partnership tier." }, 403));
    render(<SchoolDailyAttendance roster={ROSTER} />);
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("This school has no active partnership tier."));
    expect(refresh).not.toHaveBeenCalled();
  });

  it("review I-3: a past day before any of the class enrolled says so and keeps the date picker usable", () => {
    render(<SchoolDailyAttendance roster={{ ...ROSTER, session_date: "2026-01-05", students: [] }} />);
    expect(screen.getByRole("status").textContent).toBe("None of your current students were enrolled at your school on 05 Jan 2026.");
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-09-29" } });
    fireEvent.click(screen.getByRole("button", { name: "Show" }));
    expect(push).toHaveBeenCalledWith("/school/teacher/attendance?date=2026-09-29");
  });

  it("adds Attendance to the teacher's navigation only", () => {
    expect(SCHOOL_NAV.teacher.map((i) => [i.label, i.href])).toEqual([["Dashboard", "/school/teacher/dashboard"], ["Attendance", "/school/teacher/attendance"]]);
    expect(SCHOOL_NAV.parent.map((i) => i.label)).toEqual(["Dashboard", "Notifications"]);
  });
});
