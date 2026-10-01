import { describe, expect, it } from "vitest";
import { buildPayload, duplicateDetail, emptyValues, validate, valuesFrom, type AgentStudentDetail } from "@/lib/agentStudents";

describe("agentStudents lib", () => {
  it("builds a create payload without blank fields", () => {
    const v = { ...emptyValues(), full_name: " Asha ", email: "A@X.COM", graduation_year: "2024" };
    expect(buildPayload(v)).toEqual({ full_name: "Asha", email: "a@x.com", graduation_year: 2024 });
  });

  it("sends only changed fields on edit, null for a cleared field", () => {
    const original = { ...emptyValues(), full_name: "Asha", phone: "123" };
    expect(buildPayload({ ...original, phone: "" }, original)).toEqual({ phone: null });
    expect(buildPayload({ ...original, phone: " 123 " }, original)).toEqual({});
    expect(buildPayload(original, original)).toEqual({});
  });

  it("round-trips a stored student into form values", () => {
    const d = { full_name: "Asha", graduation_year: 2024, date_of_birth: "2004-02-01", email: null } as unknown as AgentStudentDetail;
    const v = valuesFrom(d);
    expect(v.full_name).toBe("Asha");
    expect(v.graduation_year).toBe("2024");
    expect(v.email).toBe("");
    expect(buildPayload(v, v)).toEqual({});
  });

  it("validates like the server", () => {
    const errors = validate({ ...emptyValues(), full_name: " ", email: "bad", graduation_year: "1900", notes: "x".repeat(2001) });
    expect(Object.keys(errors).sort()).toEqual(["email", "full_name", "graduation_year", "notes"]);
    expect(validate({ ...emptyValues(), full_name: "Asha", date_of_birth: "2999-01-01" }).date_of_birth).toBeTruthy();
    expect(validate({ ...emptyValues(), full_name: "Asha" })).toEqual({});
  });

  it("checks the phone with the server's rule (AGN-005 QA5-01)", () => {
    const message = "Enter a phone number of 7–20 digits, spaces, +, -, ( or ) with at least 7 digits";
    for (const phone of ["abc", "98765 4321x", "123456", "+", "9".repeat(21), "Tel: 9876543210"]) {
      expect(validate({ ...emptyValues(), full_name: "Asha", phone }).phone).toBe(message);
    }
    for (const phone of ["", "   ", "9876543", "+91 98765 43210", "(022) 2345-6789", " +44 20 7946 0958 "]) {
      expect(validate({ ...emptyValues(), full_name: "Asha", phone }).phone).toBeUndefined();
    }
  });

  it("does not re-check a phone that was saved before the rule and is unchanged on edit", () => {
    const original = { ...emptyValues(), full_name: "Asha", phone: "abc" };
    expect(validate({ ...original, full_name: "Asha R" }, original).phone).toBeUndefined();
    expect(validate({ ...original, phone: "abcd" }, original).phone).toBeTruthy();
  });

  it("reads only a structured duplicate detail", () => {
    expect(duplicateDetail({ code: "possible_duplicate", message: "m", matches: [], hidden_matches: 2 })?.hidden_matches).toBe(2);
    expect(duplicateDetail("Student not found")).toBeNull();
    expect(duplicateDetail({ code: "other" })).toBeNull();
    expect(duplicateDetail(null)).toBeNull();
  });
});
