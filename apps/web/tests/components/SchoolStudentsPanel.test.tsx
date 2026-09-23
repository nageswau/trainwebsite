import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SchoolStudentsPanel from "@/components/SchoolStudentsPanel";

// ENH-025 -- the coordinator roster forms carry the Student Master fields (spec §4.2).
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const student = {
  id: "s1", student_code: "A3F9C21B", full_name: "Asha Rao", date_of_birth: "2012-01-02", grade_or_class: "Grade 8-A", academic_year_id: null, grade_level: 8,
  assigned_teacher_user_id: null, pending_parent_email: null, section: "A", roll_number: "7", gender: "female", student_mobile: "+91 98765 43210", city: "Pune",
  subjects: ["Maths", "Physics"], career_interests: null, global_education_interest: true, preferred_countries: ["Germany"], preferred_courses: null, has_photo: false,
};

type Call = { url: string; init?: RequestInit };
let calls: Call[] = [];

function stubFetch(respond: (url: string) => Response) {
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    if (url === "/api/v1/school/team") return new Response(JSON.stringify({ accounts: [] }));
    return respond(url);
  }));
}

const bodyOf = (method: string) => JSON.parse(String(calls.find((c) => c.init?.method === method)!.init!.body));

beforeEach(() => {
  calls = [];
  stubFetch(() => new Response(JSON.stringify(student), { status: 200 }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SchoolStudentsPanel (ENH-025)", () => {
  it("shows section and roll number columns", () => {
    render(<SchoolStudentsPanel students={[student]} />);
    expect(screen.getByRole("columnheader", { name: "Section" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Roll no." })).toBeTruthy();
    expect(screen.getByRole("cell", { name: "7" })).toBeTruthy();
  });

  it("edit form is grouped, pre-filled, focused, and saving untouched keeps every value", async () => {
    render(<SchoolStudentsPanel students={[student]} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    for (const legend of ["Identity", "Class placement", "Contact", "Studies & interests"]) {
      expect(screen.getAllByRole("group", { name: legend }).length).toBeGreaterThan(0);
    }
    expect((screen.getByLabelText("City", { selector: "#edit-city" }) as HTMLInputElement).value).toBe("Pune");
    expect(document.activeElement?.id).toBe("edit-heading");
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(calls.some((c) => c.init?.method === "PATCH")).toBe(true));
    expect(bodyOf("PATCH")).toMatchObject({
      section: "A", roll_number: "7", gender: "female", city: "Pune", student_mobile: "+91 98765 43210", subjects: ["Maths", "Physics"],
      global_education_interest: true, preferred_countries: ["Germany"], career_interests: null, date_of_birth: "2012-01-02",
    });
  });

  it("returns focus to the row's Edit button after Cancel", () => {
    render(<SchoolStudentsPanel students={[student]} />);
    const edit = screen.getByRole("button", { name: "Edit" });
    fireEvent.click(edit);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(document.activeElement).toBe(edit);
  });

  it("create form sends only filled new fields", async () => {
    render(<SchoolStudentsPanel students={[]} />);
    fireEvent.change(screen.getByLabelText("Full name", { selector: "#new-full-name" }), { target: { value: "New Kid" } });
    fireEvent.change(screen.getByLabelText("Roll number", { selector: "#new-roll" }), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "Add student" }));
    await waitFor(() => expect(calls.some((c) => c.init?.method === "POST")).toBe(true));
    const body = bodyOf("POST");
    expect(body.roll_number).toBe("3");
    expect("city" in body).toBe(false);
  });

  it("shows a server error inside the form as an alert", async () => {
    stubFetch(() => new Response(JSON.stringify({ detail: "roll_number '7' is already used in this grade and section for this academic year" }), { status: 409 }));
    render(<SchoolStudentsPanel students={[student]} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect((await screen.findByRole("alert")).textContent).toContain("already used");
  });

  it("empty roster points to add and bulk upload", () => {
    render(<SchoolStudentsPanel students={[]} />);
    expect(screen.getByText(/No students yet/)).toBeTruthy();
    expect(screen.getAllByRole("link", { name: /bulk upload/i }).length).toBeGreaterThan(1);
  });
});
