// mgmt-011 (spec SM1-SM14): salary management's types, links and the grid's request body. The API decides access (finance tier only)
// and every rule; this module only shapes what the page sends and shows.
export const SALARIES_HOME = "/management/salaries";
export const SALARIES_API = "/api/v1/management/salaries";
export const DEPARTMENTS_API = "/api/v1/management/departments";

export type Department = { id: string; name: string; active: boolean };
export const SALARY_FIELDS = ["headcount", "payable", "paid", "incentives", "commissions", "employer_cost"] as const;
export type SalaryField = (typeof SALARY_FIELDS)[number];
export type SalaryFigures = { headcount: number | null; payable: string | null; paid: string | null; incentives: string | null; commissions: string | null; employer_cost: string | null; total_cost: string | null };
export type SalaryRow = SalaryFigures & { department: Department; entered: boolean; warnings: "paid_exceeds_payable"[] };
export type SalaryMonth = {
  month: string; current_month: string; rows: SalaryRow[]; totals: SalaryFigures; revenue: string; ratio: string | null; updated_at: string | null;
  updated_by: { id: string; full_name: string } | null;
};
export type SalaryDraft = Record<SalaryField, string>;

export const FIELD_LABEL: Record<SalaryField, string> = {
  headcount: "Employees", payable: "Salary payable", paid: "Salary paid", incentives: "Incentives", commissions: "Commissions", employer_cost: "Employer cost",
};

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;

/** The month from the page's search params; anything malformed (only from a hand-edited address) is dropped -> the current month. */
export function salaryMonth(search: Record<string, string | string[] | undefined>): string {
  const month = search.month;
  return typeof month === "string" && MONTH.test(month) ? month : "";
}

export const salariesHref = (month: string) => `${SALARIES_HOME}?month=${month}`;
export const salariesUrl = (month: string) => (month ? `${SALARIES_API}?month=${month}` : SALARIES_API);

export function monthLabel(month: string): string {
  const [year, number] = month.split("-").map(Number);
  // Intl's format() throws on an invalid Date (toLocaleDateString said "Invalid Date"); like formatDate, show the raw value instead.
  const date = new Date(Date.UTC(year, number - 1, 1));
  if (Number.isNaN(date.getTime())) return month;
  return new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(date);
}

/** R7 as "27.50%", or a dash when the month has no revenue (SM7). */
export const ratioText = (ratio: string | null) => (ratio === null ? "—" : `${ratio}%`);

export function draftFrom(row: SalaryRow): SalaryDraft {
  return Object.fromEntries(SALARY_FIELDS.map((f) => [f, row[f] === null ? "" : String(row[f])])) as SalaryDraft;
}

/** SM4: the whole month. A row with no value is left out (so it is removed); in a row with values a blank means 0. A headcount that is
 * not a whole number is sent as typed, so the API's 422 names the field. */
export function salaryBody(drafts: { department_id: string; draft: SalaryDraft }[]) {
  const rows = drafts
    .filter(({ draft }) => SALARY_FIELDS.some((f) => draft[f].trim() !== ""))
    .map(({ department_id, draft }) => {
      const value = (f: SalaryField) => draft[f].trim() || "0";
      const headcount = value("headcount");
      return {
        department_id, headcount: /^\d+$/.test(headcount) ? Number(headcount) : headcount, payable: value("payable"), paid: value("paid"),
        incentives: value("incentives"), commissions: value("commissions"), employer_cost: value("employer_cost"),
      };
    });
  return { rows };
}

/** The API's 422 items placed on their department rows (`loc: ["body", "rows", i, field]`), worded with the field's label; a row with
 * several problems lists them all (QA-02). */
export function rowErrors(detail: unknown, sentIds: string[]): Record<string, string> {
  if (!Array.isArray(detail)) return {};
  const out: Record<string, string> = {};
  for (const item of detail as { loc?: unknown[]; msg?: string }[]) {
    const [, list, index, field] = item.loc ?? [];
    const id = list === "rows" && typeof index === "number" ? sentIds[index] : undefined;
    if (!id) continue;
    const label = FIELD_LABEL[field as SalaryField];
    const text = label ? `${label}: ${item.msg}` : String(item.msg);
    out[id] = out[id] ? `${out[id]} · ${text}` : text;
  }
  return out;
}
