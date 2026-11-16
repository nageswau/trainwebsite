import { describe, expect, it } from "vitest";
import { heldStudentDivisions } from "@/lib/dualEnrolment";

// ENH-033 (DEC-SCOPE-441 D3): the header switcher shows only for a student holding both active student assignments.
describe("heldStudentDivisions", () => {
  it("lists both divisions, IT first, for a dual student", () => {
    expect(heldStudentDivisions([
      { division: "overseas", role: "overseas_student", is_active: true },
      { division: "it", role: "it_student", is_active: true },
    ])).toEqual(["it", "overseas"]);
  });

  it("ignores inactive rows, staff rows and mismatched pairs", () => {
    expect(heldStudentDivisions([
      { division: "it", role: "it_student", is_active: true },
      { division: "overseas", role: "overseas_student", is_active: false },
      { division: "overseas", role: "counselor", is_active: true },
      { division: "overseas", role: "it_student", is_active: true },
    ])).toEqual(["it"]);
    expect(heldStudentDivisions(undefined)).toEqual([]);
  });
});
