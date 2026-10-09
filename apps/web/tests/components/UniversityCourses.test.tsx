import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CourseForm from "@/components/CourseForm";
import CourseImportPanel from "@/components/CourseImportPanel";
import UniversityCourses from "@/components/UniversityCourses";
import type { Course, CoursePage } from "@/lib/courseMaster";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const res = (body: unknown, status = 200) => new Response(body === null ? null : JSON.stringify(body), { status });
const course = (over: Partial<Course> = {}): Course => ({
  id: "c1", university_id: "u1", title: "MSc Cyber Security", level: "PG", category: "Computer Science", duration: "1 year", tuition_fee: "GBP 18,000",
  intake: "Jan, Sep", tuition_amount: "18000.00", tuition_currency: "GBP", application_fee: "75.00", application_fee_currency: "GBP", intakes: ["Jan", "Sep"],
  entry_requirements: "2:1 honours degree", english_test: "IELTS", english_score: "6.5", scholarships: [{ id: "s1", title: "Global Award", amount: "£5,000" }],
  application_process: "Apply online", deadline: "2027-06-30", active: true, permissions: { can_edit: true }, ...over,
});
const page = (items: Course[], can_edit = true): CoursePage => ({ items, total: items.length, limit: 50, offset: 0, can_edit });
const options = { scholarships: [{ id: "s1", title: "Global Award", amount: "£5,000" }] };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("UniversityCourses (upc-017)", () => {
  it("shows an empty state, with Add and Import only for writers", () => {
    const { unmount } = render(<UniversityCourses universityId="u1" page={page([])} options={options} canSetCommission={false} />);
    expect(screen.getByText("No courses recorded yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add course" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import courses (CSV)" })).toBeInTheDocument();
    unmount();
    render(<UniversityCourses universityId="u1" page={page([], false)} options={null} canSetCommission={false} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("lists every §16 field; inactive courses are marked; commission only when the API sent it", () => {
    render(<UniversityCourses universityId="u1" page={page([course({ permissions: { can_edit: false } }), course({ id: "c2", title: "MBA", active: false, permissions: { can_edit: false } })], false)} options={null} canSetCommission={false} />);
    const [first, second] = screen.getAllByRole("listitem").filter((li) => li.parentElement?.getAttribute("aria-label") === "Courses");
    for (const text of ["MSc Cyber Security", "PG", "Computer Science", "1 year", "Jan, Sep", "GBP 18,000", "GBP 75", "IELTS 6.5", "2:1 honours degree", "Apply online", "30 Jun 2027", "Global Award (£5,000)"]) {
      expect(within(first).getByText(text)).toBeInTheDocument();
    }
    expect(within(first).queryByText(/commission/i)).not.toBeInTheDocument();
    expect(within(second).getByText("Inactive")).toBeInTheDocument();
    cleanup();
    render(<UniversityCourses universityId="u1" page={page([course({ commission: { percent: "12.50", amount: null, currency: null } })])} options={options} canSetCommission />);
    expect(screen.getByText("Commission (restricted)")).toBeInTheDocument();
    expect(screen.getByText("12.5%")).toBeInTheDocument();
  });

  it("adds a course and refreshes the page", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ course: course() }, 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<UniversityCourses universityId="u1" page={page([])} options={options} canSetCommission={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Add course" }));
    const form = screen.getByRole("form", { name: "New course" });
    fireEvent.change(within(form).getByLabelText("Course title (required)"), { target: { value: "MSc Cyber Security" } });
    fireEvent.change(within(form).getByLabelText("Level (required)"), { target: { value: "PG" } });
    fireEvent.change(within(form).getByLabelText("Category (required)"), { target: { value: "Computer Science" } });
    fireEvent.change(within(form).getByLabelText("Duration (required)"), { target: { value: "1 year" } });
    fireEvent.click(within(form).getByLabelText("Sep"));
    fireEvent.click(within(form).getByLabelText("Jan"));
    fireEvent.change(within(form).getByLabelText("Tuition fee"), { target: { value: "18000" } });
    fireEvent.change(within(form).getByLabelText("Tuition currency"), { target: { value: "GBP" } });
    fireEvent.change(within(form).getByLabelText("English test"), { target: { value: "IELTS" } });
    fireEvent.change(within(form).getByLabelText("Minimum score"), { target: { value: "6.5" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save course" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/partnership/universities/u1/courses");
    expect(JSON.parse(init.body)).toEqual({
      title: "MSc Cyber Security", level: "PG", category: "Computer Science", duration: "1 year", intakes: ["Jan", "Sep"], tuition_amount: "18000",
      tuition_currency: "GBP", english_test: "IELTS", english_score: "6.5", active: true,
    });
    expect(screen.getByRole("status")).toHaveTextContent("Course added.");
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });
});

describe("CourseForm (upc-017)", () => {
  const renderForm = (props: Partial<Parameters<typeof CourseForm>[0]> = {}) => {
    const onSaved = vi.fn();
    render(<CourseForm universityId="u1" options={options} canSetCommission={false} label="Course form" onSaved={onSaved} onCancel={vi.fn()} {...props} />);
    return { onSaved, form: screen.getByRole("form", { name: "Course form" }) };
  };

  it("checks values before sending (N1, CO4, CO8)", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { form } = renderForm({ course: course() });
    const save = () => fireEvent.click(within(form).getByRole("button", { name: "Save course" }));
    const alert = () => within(form).getByRole("alert").textContent;
    fireEvent.change(within(form).getByLabelText("Course title (required)"), { target: { value: " " } });
    save();
    expect(alert()).toBe("Enter the course title.");
    fireEvent.change(within(form).getByLabelText("Course title (required)"), { target: { value: "MSc" } });
    fireEvent.change(within(form).getByLabelText("Tuition fee"), { target: { value: "-1" } });
    save();
    expect(alert()).toBe("The tuition fee cannot be negative.");
    fireEvent.change(within(form).getByLabelText("Tuition fee"), { target: { value: "18000" } });
    fireEvent.change(within(form).getByLabelText("Tuition currency"), { target: { value: "" } });
    save();
    expect(alert()).toBe("Enter both the tuition fee and its currency, or neither.");
    fireEvent.change(within(form).getByLabelText("Tuition currency"), { target: { value: "GBP" } });
    fireEvent.change(within(form).getByLabelText("Minimum score"), { target: { value: "9.5" } });
    save();
    expect(alert()).toBe("An IELTS score cannot be above 9.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends only what changed, keeps a legacy level, and deactivates (CO3, CO11)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ course: course() }));
    vi.stubGlobal("fetch", fetchMock);
    const { form, onSaved } = renderForm({ course: course({ level: "Masters", tuition_amount: null, tuition_currency: null, tuition_fee: "£9,000" }) });
    expect(within(form).getByLabelText("Level (required)")).toHaveValue("Masters");
    fireEvent.change(within(form).getByLabelText("Duration (required)"), { target: { value: "12 months" } });
    fireEvent.click(within(form).getByLabelText("Offered (active)"));
    fireEvent.click(within(form).getByRole("button", { name: "Save course" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith("Course updated."));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/partnership/universities/u1/courses/c1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ duration: "12 months", active: false });
  });

  it("offers commission only to the commission roles and sends it as one rate", async () => {
    renderForm();
    expect(screen.queryByText(/commission/i)).not.toBeInTheDocument();
    cleanup();
    const fetchMock = vi.fn().mockResolvedValue(res({ course: course() }));
    vi.stubGlobal("fetch", fetchMock);
    const { form } = renderForm({ course: course({ commission: null }), canSetCommission: true });
    fireEvent.click(within(form).getByLabelText("Percentage"));
    fireEvent.change(within(form).getByLabelText("Commission %"), { target: { value: "12.5" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save course" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ commission: { percent: "12.5" } });
  });

  it("shows the server's reason when saving fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "This university already has a course with this title at this level" }, 409)));
    const { form } = renderForm({ course: course() });
    fireEvent.change(within(form).getByLabelText("Duration (required)"), { target: { value: "2 years" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save course" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("already has a course with this title");
  });
});

describe("CourseImportPanel (upc-017)", () => {
  it("rejects a non-CSV file before uploading, then reports the rows that were not created", async () => {
    const report = {
      id: "b1", total_rows: 3, created_count: 1, duplicate_count: 1, invalid_count: 1,
      rows: [
        { row_number: 2, status: "created", title: "MSc A", level: "PG", course_id: "c9", reason: null },
        { row_number: 3, status: "duplicate", title: "MSc B", level: "PG", course_id: null, reason: "Repeats row 2 of this file" },
        { row_number: 4, status: "invalid", title: "MBA", level: "Masters", course_id: null, reason: "level must be one of UG, PG" },
      ],
    };
    const fetchMock = vi.fn().mockResolvedValue(res(report, 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<CourseImportPanel universityId="u1" />);
    const input = screen.getByLabelText("CSV file");
    fireEvent.change(input, { target: { files: [new File(["x"], "courses.txt")] } });
    fireEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a .csv file.");
    fireEvent.change(input, { target: { files: [new File(["title,level"], "courses.csv", { type: "text/csv" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByText("1 added, 1 duplicate, 1 invalid.")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Rows not added" });
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).getByText("Repeats row 2 of this file")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/partnership/universities/u1/courses/import");
    expect(fetchMock.mock.calls[0][1].headers["Idempotency-Key"]).toBeTruthy();
    expect(refresh).toHaveBeenCalled();
    expect(screen.getByRole("link", { name: "Download the template" })).toHaveAttribute("href", "/api/v1/partnership/universities/u1/courses/imports/template");
  });
});
