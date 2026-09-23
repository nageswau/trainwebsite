import { describe, expect, it } from "vitest";
import { ROSTER_COLUMNS, detailMessage, fieldFromMessage, friendlyMessage, listText, toMasterPayload } from "@/lib/schoolStudents";

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

// QA2-05: server validation messages name API fields; users see their labels instead.
describe("friendlyMessage", () => {
  it.each([
    ["roll_number '12' is already used in this grade and section for this academic year", "Roll number 12 is already used in this grade and section for this academic year"],
    ["student_mobile must be 7-20 characters of digits, spaces, +, -, ( or ) with at least 7 digits", "Student mobile must be 7-20 characters of digits, spaces, +, -, ( or ) with at least 7 digits"],
    ["subjects must have at most 20 items", "Subjects must have at most 20 items"],
    ["subjects items must be at most 80 characters", "Each subject must be at most 80 characters"],
    ["preferred_countries items must be at most 80 characters", "Each preferred country must be at most 80 characters"],
    ["global_education_interest must be yes or no", "Interested in studying abroad must be yes or no"],
    ["gender must be one of: female, male, other, prefer_not_to_say", "Gender must be one of: female, male, other, prefer_not_to_say"],
    ["full_name is required", "Full name is required"],
    ["grade_level '99' must be an integer between 1 and 12", "Grade level '99' must be an integer between 1 and 12"],
    ["photo must be a JPEG or PNG image", "Photo must be a JPEG or PNG image"],
  ])("%s", (raw, friendly) => {
    expect(friendlyMessage(raw)).toBe(friendly);
  });

  it("leaves messages that name no known field unchanged", () => {
    expect(friendlyMessage("This student is at a different institution")).toBe("This student is at a different institution");
  });

  it("detailMessage applies it to string details", () => {
    expect(detailMessage("city must be at most 120 characters")).toBe("City must be at most 120 characters");
  });
});

// QA2-06: the field a message is about, so the form can mark and focus it.
describe("fieldFromMessage", () => {
  it.each([
    ["roll_number '12' is already used in this grade and section for this academic year", "roll_number"],
    ["subjects items must be at most 80 characters", "subjects"],
    ["student_mobile must be 7-20 characters", "student_mobile"],
    ["This student is at a different institution", null],
  ])("%s -> %s", (raw, field) => {
    expect(fieldFromMessage(raw)).toBe(field);
  });
});
