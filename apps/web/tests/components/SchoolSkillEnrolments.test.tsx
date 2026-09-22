import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolSkillEnrolments from "@/components/SchoolSkillEnrolments";

import { detail, enrolment, json, stubFetch, student } from "./skillFixtures";

// ENH-011 spec §7: the roster (status in words, only the API's allowed changes, frozen rows read-only) and the enrol picker.
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const rowOf = (name: string) => screen.getAllByRole("row").find((r) => r.textContent?.includes(name))!;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("roster", () => {
  it("shows status, attendance and only the changes the API allows", () => {
    const batch = detail({ enrollments: [enrolment("1", { attendance: { present: 3, marked: 4 } }), enrolment("2", { status: "certified" }), enrolment("3", { status: "withdrawn" })] });
    render(<SchoolSkillEnrolments batch={batch} students={[]} />);
    const one = rowOf("Student 1");
    expect(within(one).getByText("Enrolled")).toBeTruthy();
    expect(within(one).getByText("Attended 3 of 4 sessions")).toBeTruthy();
    expect(within(one).getAllByRole("button").map((b) => b.textContent)).toEqual(["Mark completed", "Certify", "Withdraw"]);
    expect(within(one).getByRole("button", { name: "Certify Student 1" })).toBeTruthy();
    expect(within(rowOf("Student 2")).queryAllByRole("button")).toEqual([]);
    expect(within(rowOf("Student 2")).getByText("No further changes")).toBeTruthy(); // QA-12: not a blank cell
    expect(within(rowOf("Student 3")).getAllByRole("button").map((b) => b.textContent)).toEqual(["Re-enrol"]);
  });

  it("shows a transferred-out student as read-only, in words", () => {
    render(<SchoolSkillEnrolments batch={detail({ enrollments: [enrolment("1", { frozen: true })] })} students={[]} />);
    const row = rowOf("Student 1");
    expect(within(row).getByText("Transferred out")).toBeTruthy();
    expect(within(row).queryAllByRole("button")).toEqual([]);
  });

  it("asks before certifying, because a certificate cannot be undone", async () => {
    const fetchMock = stubFetch(() => json(enrolment("1", { status: "certified" })));
    render(<SchoolSkillEnrolments batch={detail()} students={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "Certify Student 1" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText(/cannot be undone/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm certify Student 1" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/school/career-counselor/skill-enrollments/e1");
    expect(JSON.parse(String(init?.body))).toEqual({ status: "certified" });
    expect(screen.getByRole("status").textContent).toBe("Student 1: Certified.");
    expect(document.activeElement).toBe(screen.getByRole("rowheader", { name: "Student 1" })); // QA-03: not <body>
  });

  it("keeps keyboard focus through the certify confirmation (QA-03)", () => {
    render(<SchoolSkillEnrolments batch={detail()} students={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "Certify Student 1" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Confirm certify Student 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Certify Student 1" }));
  });

  it("shows the server's reason when a change is refused", async () => {
    stubFetch(() => json({ detail: "This student has moved to another school; their record in this batch is read-only" }, 409));
    render(<SchoolSkillEnrolments batch={detail()} students={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "Withdraw Student 1" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("moved to another school");
    expect(document.activeElement).toBe(alert);
  });

  it("explains an empty roster", () => {
    render(<SchoolSkillEnrolments batch={detail({ enrollments: [], enrolled_count: 0 })} students={[student("1")]} />);
    expect(screen.getByText("No students enrolled yet.")).toBeTruthy();
  });
});

describe("enrol picker", () => {
  it("lists only students not yet enrolled, filters them and enrols the chosen ones", async () => {
    const fetchMock = stubFetch(() => json([enrolment("3"), enrolment("4")], 201));
    render(<SchoolSkillEnrolments batch={detail()} students={[student("1"), student("3"), student("4"), student("40")]} />);
    const picker = screen.getByRole("group", { name: "Enrol students" });
    expect(within(picker).queryByLabelText("Student 1")).toBeNull();
    fireEvent.change(within(picker).getByLabelText("Filter students"), { target: { value: "4" } });
    expect(within(picker).queryByLabelText("Student 3")).toBeNull();
    fireEvent.click(within(picker).getByLabelText("Student 4"));
    fireEvent.click(within(picker).getByLabelText("Student 40"));
    fireEvent.change(within(picker).getByLabelText("Filter students"), { target: { value: "" } });
    fireEvent.click(within(picker).getByLabelText("Student 3"));
    fireEvent.click(screen.getByRole("button", { name: "Enrol 3 students" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ school_student_ids: ["s3", "s4", "s40"] });
    expect(screen.getByRole("status").textContent).toBe("2 students enrolled.");
  });

  it("disables the button until a student is chosen", () => {
    render(<SchoolSkillEnrolments batch={detail()} students={[student("3")]} />);
    expect(screen.getByRole("button", { name: "Enrol 0 students" }).hasAttribute("disabled")).toBe(true);
  });

  it("says so when every student is already enrolled, and hides the picker on a closed batch", () => {
    const { rerender } = render(<SchoolSkillEnrolments batch={detail()} students={[student("1"), student("2")]} />);
    expect(screen.getByText("Every student at Sunrise School is already enrolled.")).toBeTruthy();
    rerender(<SchoolSkillEnrolments batch={detail({ status: "closed" })} students={[student("3")]} />);
    expect(screen.queryByRole("group", { name: "Enrol students" })).toBeNull();
  });
});
