import { describe, expect, it } from "vitest";

import { AUDIT_PAGE_SIZE, auditFilterError, auditFilters, auditHref, auditUrl, entityHistoryHref } from "@/lib/auditLog";

const ID = "0b8f2a9e-1c2d-4e5f-8a9b-0c1d2e3f4a5b";
const BASE = "/it/admin/audit-log";

describe("nehn-042 audit log filters", () => {
  it("reads the filters from the address, trimmed, and drops unknown keys, repeats, bad dates and divisions", () => {
    expect(auditFilters({ actor: ` ${ID} `, action: " payment. ", entity_type: "payment", entity_id: "P-1", division: "it", date_from: "2026-03-01", date_to: "2026-03-31", offset: "50", extra: "x" }))
      .toEqual({ actor: ID, action: "payment.", entity_type: "payment", entity_id: "P-1", division: "it", date_from: "2026-03-01", date_to: "2026-03-31", offset: 50 });
    expect(auditFilters({ action: ["a", "b"], division: "mars", date_from: "2026-02-30", offset: "-5" }))
      .toEqual({ actor: "", action: "", entity_type: "", entity_id: "", division: "", date_from: "", date_to: "", offset: 0 });
  });

  it("explains filters the API would refuse, so the form can be corrected", () => {
    const none = auditFilters({});
    expect(auditFilterError(none)).toBe("");
    expect(auditFilterError({ ...none, actor: "Asha" })).toMatch(/user reference/);
    expect(auditFilterError({ ...none, date_from: "2026-03-02", date_to: "2026-03-01" })).toMatch(/end date/);
  });

  it("asks the API for one row more than a page, so it knows whether a next page exists", () => {
    const filters = { ...auditFilters({}), action: "payment.", offset: 50 };
    expect(auditUrl(filters)).toBe(`/api/v1/admin/audit?action=payment.&offset=50&limit=${AUDIT_PAGE_SIZE + 1}`);
  });

  it("builds page links that keep the filters", () => {
    expect(auditHref(BASE, auditFilters({}))).toBe(BASE);
    expect(auditHref(BASE, { ...auditFilters({}), entity_type: "payment", entity_id: "P 1", offset: 100 })).toBe(`${BASE}?entity_type=payment&entity_id=P+1&offset=100`);
  });

  it("links an entity to its whole history, and nothing else", () => {
    expect(entityHistoryHref(BASE, "payment", "P-1")).toBe(`${BASE}?entity_type=payment&entity_id=P-1`);
  });
});
