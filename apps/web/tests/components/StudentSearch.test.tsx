import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import StudentSearch from "@/components/StudentSearch";
import { studentSearchError, studentSearchFilters, studentSearchUrl, type StudentSearchResult } from "@/lib/studentSearch";

const BASE = "/admin/student-search";
const ALL = ["it_student", "overseas_student", "agency_student", "school_student"] as const;
const none = studentSearchFilters({});
const hit = (id: string, extra = {}) => ({ id, code: "3FA9C21B", label: `Asha ${id}`, detail: "asha@example.local · Python", href: `/admin/users?q=${id}`, ...extra });

afterEach(cleanup);

describe("StudentSearch (nehn-041)", () => {
  it("keeps the search in a GET form with the type and program filters the caller may use", () => {
    render(<StudentSearch base={BASE} filters={{ q: "Asha", type: "it_student", program: "p1" }} kinds={[...ALL]} programs={[{ id: "p1", title: "Python" }]} result={null} error="" />);
    const form = screen.getByRole("search", { name: "Student search" });
    expect(form.getAttribute("method")).toBe("get");
    expect(form.getAttribute("action")).toBe(BASE);
    expect((screen.getByLabelText("Student ID, name, phone, email or course") as HTMLInputElement).value).toBe("Asha");
    expect((screen.getByLabelText("Type") as HTMLSelectElement).value).toBe("it_student");
    expect((screen.getByLabelText("IT program") as HTMLSelectElement).value).toBe("p1");
    cleanup();
    render(<StudentSearch base={BASE} filters={none} kinds={["it_student"]} programs={null} result={null} error="" />);
    expect(screen.queryByLabelText("Type")).toBeNull();
    expect(screen.queryByLabelText("IT program")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("shows one group per kind, each card opening the student, with the more-than-shown hint", () => {
    const result: StudentSearchResult = {
      q: "Asha",
      groups: { it_student: { items: [hit("a1"), hit("a2", { code: null })], more: true }, school_student: { items: [hit("s1", { href: null, detail: "Grade 8 · Hill School" })], more: false } },
    };
    render(<StudentSearch base={BASE} filters={{ ...none, q: "Asha" }} kinds={[...ALL]} programs={null} result={result} error="" />);
    const it_group = screen.getByRole("region", { name: "IT students (2+)" });
    expect(within(it_group).getByRole("link", { name: "Asha a1" }).getAttribute("href")).toBe("/admin/users?q=a1");
    expect(within(it_group).getByRole("link", { name: "Asha a1" })).toHaveStyle({ textDecoration: "underline" });  // QA-041-01: looks like a link
    expect(within(it_group).getByText("Student ID 3FA9C21B")).toBeTruthy();
    expect(within(it_group).getByText("Showing the first 2 — refine your search.")).toBeTruthy();
    const school = screen.getByRole("region", { name: "School students (1)" });
    expect(within(school).queryByRole("link")).toBeNull();  // no page for this caller: the card names the school instead
    expect(within(school).getByText("Grade 8 · Hill School")).toBeTruthy();
    expect(screen.queryByRole("region", { name: /Overseas students/ })).toBeNull();
  });

  it("says when nothing matches, and shows a refusal as an alert", () => {
    render(<StudentSearch base={BASE} filters={{ ...none, q: "Zed" }} kinds={["it_student"]} programs={null} result={{ q: "Zed", groups: { it_student: { items: [], more: false } } }} error="" />);
    expect(screen.getByRole("status").textContent).toBe("No students you can see match “Zed”.");
    cleanup();
    render(<StudentSearch base={BASE} filters={{ ...none, q: "a" }} kinds={["it_student"]} programs={null} result={null} error="Type at least 3 characters." />);
    expect(screen.getByRole("alert").textContent).toBe("Type at least 3 characters.");
  });
});

describe("lib/studentSearch (nehn-041)", () => {
  it("reads the filters from the address, dropping what only a hand edit could produce", () => {
    expect(studentSearchFilters({ q: "  Asha ", type: "school_student", program: "6f1c1a52-8d5b-4f7e-9a0e-0c1d2e3f4a5b" }))
      .toEqual({ q: "Asha", type: "school_student", program: "6f1c1a52-8d5b-4f7e-9a0e-0c1d2e3f4a5b" });
    expect(studentSearchFilters({ q: ["a", "b"], type: "lead", program: "x" })).toEqual({ q: "", type: "", program: "" });
  });

  it("explains a short or long search and builds the API address", () => {
    expect(studentSearchError({ q: "", type: "", program: "" })).toBe("");
    expect(studentSearchError({ q: "ab", type: "", program: "" })).toBe("Type at least 3 characters.");
    expect(studentSearchError({ q: "x".repeat(101), type: "", program: "" })).toBe("Use at most 100 characters.");
    expect(studentSearchUrl({ q: "+91 98765", type: "it_student", program: "" })).toBe("/api/v1/search/students?q=%2B91+98765&type=it_student");
  });
});
