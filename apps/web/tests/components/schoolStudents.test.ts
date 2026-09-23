import { describe, expect, it } from "vitest";
import { ROSTER_COLUMNS, listText, toMasterPayload } from "@/lib/schoolStudents";

// ENH-025 -- shared Student Master helpers (spec §4.1).

function form(entries: Record<string, string>) {
  const f = new FormData();
  Object.entries(entries).forEach(([k, v]) => f.append(k, v));
  return f;
}

describe("toMasterPayload", () => {
  it("splits lists on commas, trims, drops empties", () => {
    const p = toMasterPayload(form({ subjects: " Maths, Physics ,, ", city: " Pune ", gender: "female", global_education_interest: "yes" }), "create");
    expect(p).toEqual({ subjects: ["Maths", "Physics"], city: "Pune", gender: "female", global_education_interest: true });
  });

  it("create omits empty fields; edit sends null to clear", () => {
    const f = form({ city: "", subjects: "", gender: "", global_education_interest: "" });
    expect(toMasterPayload(f, "create")).toEqual({});
    expect(toMasterPayload(f, "edit")).toEqual({
      city: null, subjects: null, gender: null, global_education_interest: null, section: null, roll_number: null,
      student_mobile: null, career_interests: null, preferred_countries: null, preferred_courses: null,
    });
  });

  it("maps no to false", () => {
    expect(toMasterPayload(form({ global_education_interest: "no" }), "create")).toEqual({ global_education_interest: false });
  });
});

describe("listText / ROSTER_COLUMNS", () => {
  it("joins lists for inputs", () => {
    expect(listText(["A", "B"])).toBe("A, B");
    expect(listText(null)).toBe("");
  });

  it("documents the original seven columns first and only full_name as required", () => {
    expect(ROSTER_COLUMNS.slice(0, 7).map((c) => c.name)).toEqual(["full_name", "date_of_birth", "grade_or_class", "assigned_teacher_email", "parent_name", "parent_email", "grade_level"]);
    expect(ROSTER_COLUMNS).toHaveLength(17);
    expect(ROSTER_COLUMNS.filter((c) => c.required).map((c) => c.name)).toEqual(["full_name"]);
  });
});
