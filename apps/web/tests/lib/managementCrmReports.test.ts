import { describe, expect, it } from "vitest";

import { ADMIN_CRM_REPORTS_HOME, CRM_REPORTS_HOME, crmExportUrl, crmFilters, crmReportsHref, crmReportsUrl, EMPTY_CRM_FILTERS, hasCrmFilters, percentText } from "@/lib/managementCrmReports";

const ID = "0b9c3f1e-6a52-4e43-9d7a-2b8f8f2f3c11";

describe("ccrm-034 crmFilters", () => {
  it("keeps every well-formed filter from the address", () => {
    const search = { date_from: "2026-04-01", date_to: "2026-09-30", counselor: "none", country: ID, university: ID, course: ID, intake: "Fall 2027" };
    expect(crmFilters(search)).toEqual(search);
  });

  it("drops repeated, malformed and unknown values", () => {
    const filters = crmFilters({ counselor: [ID, ID], country: "none", university: "12", date_from: "2026-02-30", intake: "x".repeat(81), staff: ID });
    expect(filters).toEqual(EMPTY_CRM_FILTERS);
    expect(hasCrmFilters(filters)).toBe(false);
  });
});

describe("ccrm-034 URLs", () => {
  it("is the bare API path with no filters and carries only the set ones", () => {
    expect(crmReportsUrl(EMPTY_CRM_FILTERS)).toBe("/api/v1/management/crm-reports");
    expect(crmReportsUrl({ ...EMPTY_CRM_FILTERS, intake: "Fall 2027", counselor: "none" })).toBe("/api/v1/management/crm-reports?counselor=none&intake=Fall+2027");
  });

  it("links each page to itself", () => {
    expect(crmReportsHref(CRM_REPORTS_HOME, { ...EMPTY_CRM_FILTERS, country: ID })).toBe(`/management/crm-reports?country=${ID}`);
    expect(crmReportsHref(ADMIN_CRM_REPORTS_HOME, EMPTY_CRM_FILTERS)).toBe("/overseas/admin/crm-reports");
  });
});

describe("ccrm-034 percentText", () => {
  it("reads a dash when there is nothing to divide by", () => {
    expect(percentText(null)).toBe("—");
    expect(percentText(66.7)).toBe("66.7%");
    expect(percentText(50)).toBe("50%");
  });
});

describe("ccrm-035 export URL", () => {
  it("names the report and carries the applied filters", () => {
    expect(crmExportUrl("ageing", EMPTY_CRM_FILTERS)).toBe("/api/v1/management/crm-reports/export?report=ageing");
    expect(crmExportUrl("leads", { ...EMPTY_CRM_FILTERS, intake: "Fall 2027" })).toBe("/api/v1/management/crm-reports/export?intake=Fall+2027&report=leads");
  });
});
