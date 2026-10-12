import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS, managementNavFor } from "@/lib/management";
import { SOURCE_LABEL } from "@/lib/managementLedger";
import {
  draftFrom,
  monthLabel,
  ratioText,
  rowErrors,
  salaryBody,
  salaryMonth,
  salariesHref,
  salariesUrl,
  type SalaryRow,
} from "@/lib/salaries";

const ROW: SalaryRow = {
  department: { id: "d1", name: "Training", active: true }, entered: true, headcount: 4, payable: "200000.00", paid: "180000.00",
  incentives: "15000.00", commissions: "0.00", employer_cost: "20000.00", total_cost: "215000.00", warnings: [],
};

describe("mgmt-011 month and links (SM13)", () => {
  it("keeps a well-formed month and drops anything else", () => {
    expect(salaryMonth({ month: "2026-09" })).toBe("2026-09");
    expect(salaryMonth({ month: "2026-13" })).toBe("");
    expect(salaryMonth({ month: ["2026-09", "2026-10"] })).toBe("");
    expect(salaryMonth({})).toBe("");
  });

  it("builds the page link and the API url", () => {
    expect(salariesHref("2026-09")).toBe("/management/salaries?month=2026-09");
    expect(salariesUrl("2026-09")).toBe("/api/v1/management/salaries?month=2026-09");
    expect(salariesUrl("")).toBe("/api/v1/management/salaries");
  });

  it("names the month and writes the ratio", () => {
    expect(monthLabel("2026-09")).toBe("September 2026");
    expect(ratioText("27.50")).toBe("27.50%");
    expect(ratioText(null)).toBe("—");
  });
});

describe("mgmt-011 grid body (SM4)", () => {
  it("starts a draft from a saved row, or blank", () => {
    expect(draftFrom(ROW)).toEqual({ headcount: "4", payable: "200000.00", paid: "180000.00", incentives: "15000.00", commissions: "0.00", employer_cost: "20000.00" });
    expect(draftFrom({ ...ROW, entered: false, headcount: null, payable: null, paid: null, incentives: null, commissions: null, employer_cost: null })).toEqual({
      headcount: "", payable: "", paid: "", incentives: "", commissions: "", employer_cost: "",
    });
  });

  it("sends only rows with a value, with blanks as 0", () => {
    const blank = { headcount: "", payable: "", paid: "", incentives: "", commissions: "", employer_cost: "" };
    const body = salaryBody([
      { department_id: "d1", draft: { ...blank, headcount: " 3 ", paid: "1000" } },
      { department_id: "d2", draft: blank },
    ]);
    expect(body).toEqual({ rows: [{ department_id: "d1", headcount: 3, payable: "0", paid: "1000", incentives: "0", commissions: "0", employer_cost: "0" }] });
  });

  it("keeps a typed headcount that is not a whole number as text, so the API names the field", () => {
    const blank = { headcount: "", payable: "", paid: "", incentives: "", commissions: "", employer_cost: "" };
    expect(salaryBody([{ department_id: "d1", draft: { ...blank, headcount: "2.5" } }]).rows[0].headcount).toBe("2.5");
  });

  it("maps the API's 422s back to their department rows", () => {
    const detail = [
      { loc: ["body", "rows", 1, "paid"], msg: "An amount can't be negative" },
      { loc: ["body", "rows", 0, "department_id"], msg: "Training is no longer in use; reactivate it first" },
    ];
    expect(rowErrors(detail, ["d1", "d2"])).toEqual({ d2: "Salary paid: An amount can't be negative", d1: "Training is no longer in use; reactivate it first" });
    expect(rowErrors("Finance access required", ["d1"])).toEqual({});
  });
});

describe("mgmt-011 navigation and ledger source", () => {
  it("makes Salaries and Employee cost live for the finance tier only", () => {
    const finance = { operational: false, finance: true, partner_only: false };
    const nav = managementNavFor(finance, MANAGEMENT_PILLARS);
    expect(nav).toContainEqual({ label: "Salaries", href: "/management/salaries" });
    expect(nav).toContainEqual({ label: "Employee cost", href: "/management/salaries#employee-cost" });
    expect(managementNavFor({ operational: true, finance: false, partner_only: false }, MANAGEMENT_PILLARS).map((i) => i.label)).not.toContain("Salaries");
  });

  it("labels the salary ledger source", () => {
    expect(SOURCE_LABEL.salary).toBe("Salaries");
  });
});
