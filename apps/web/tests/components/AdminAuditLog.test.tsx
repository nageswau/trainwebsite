import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import AdminAuditLog from "@/components/AdminAuditLog";
import { AUDIT_PAGE_SIZE, auditFilters, type AuditRow } from "@/lib/auditLog";

const BASE = "/admin/security-logs";
const ACTOR = { id: "0b8f2a9e-1c2d-4e5f-8a9b-0c1d2e3f4a5b", full_name: "Asha Admin", email: "asha@example.local", division: "it" };
const row = (n: number, extra: Partial<AuditRow> = {}): AuditRow => ({
  id: `r${n}`, user_id: ACTOR.id, actor: ACTOR, action: "payment.discount", entity_type: "payment", entity_id: `P-${n}`, outcome: "recorded",
  created_at: "2026-03-01T09:30:00Z", ...extra,
});
const none = auditFilters({});

afterEach(cleanup);

describe("AdminAuditLog (nehn-042)", () => {
  it("keeps the applied filters in a GET form, with Division only where the caller may choose one", () => {
    const filters = { ...none, action: "payment.", entity_id: "P-1" };
    render(<AdminAuditLog base={BASE} rows={[]} error="" filters={filters} showDivision />);
    const form = screen.getByRole("form", { name: "Audit log filters" });
    expect(form.getAttribute("method")).toBe("get");
    expect(form.getAttribute("action")).toBe(BASE);
    expect((screen.getByLabelText("Action") as HTMLInputElement).value).toBe("payment.");
    expect((screen.getByLabelText("Entity reference") as HTMLInputElement).value).toBe("P-1");
    expect(screen.getByLabelText("Division")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Clear filters" }).getAttribute("href")).toBe(BASE);
    cleanup();
    render(<AdminAuditLog base={BASE} rows={[]} error="" filters={none} showDivision={false} />);
    expect(screen.queryByLabelText("Division")).toBeNull();
  });

  it("says when nothing matches", () => {
    render(<AdminAuditLog base={BASE} rows={[]} error="" filters={none} showDivision={false} />);
    expect(screen.getByRole("status").textContent).toMatch(/No audit records match/);
  });

  it("shows an error above the form and no table when the read failed", () => {
    render(<AdminAuditLog base={BASE} rows={null} error="Could not load" filters={none} showDivision={false} />);
    expect(screen.getByText("Could not load").className).toContain("form-error");
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("links each entity to its whole history and each actor to what they did; a system row says System", () => {
    render(<AdminAuditLog base={BASE} rows={[row(1), row(2, { user_id: null, actor: null, entity_id: null })]} error="" filters={none} showDivision={false} />);
    const table = screen.getByRole("table", { name: "Audit log" });
    expect(within(table).getByRole("link", { name: "P-1" }).getAttribute("href")).toBe(`${BASE}?entity_type=payment&entity_id=P-1`);
    expect(within(table).getByRole("link", { name: "Asha Admin" }).getAttribute("href")).toBe(`${BASE}?actor=${ACTOR.id}`);
    expect(within(table).getByText("System")).toBeTruthy();
    expect(within(table).getAllByRole("row")).toHaveLength(3);
  });

  it("shows a page of 50 and pages with the filters kept", () => {
    const rows = Array.from({ length: AUDIT_PAGE_SIZE + 1 }, (_, i) => row(i));
    render(<AdminAuditLog base={BASE} rows={rows} error="" filters={{ ...none, action: "payment.", offset: 50 }} showDivision={false} />);
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(AUDIT_PAGE_SIZE + 1); // header + 50
    expect(screen.getByText("Showing 51–100")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Previous page" }).getAttribute("href")).toBe(`${BASE}?action=payment.`);
    expect(screen.getByRole("link", { name: "Next page" }).getAttribute("href")).toBe(`${BASE}?action=payment.&offset=100`);
  });

  it("never breaks an action name mid-word (browser QA-042-01)", () => {
    render(<AdminAuditLog base={BASE} rows={[row(1, { action: "mgmt.task.complete" })]} error="" filters={none} showDivision={false} />);
    expect(screen.getByText("mgmt.task.complete").style.overflowWrap).toBe("break-word");
  });

  it("has no Next on the last page and no paging at all on a single page", () => {
    render(<AdminAuditLog base={BASE} rows={[row(1)]} error="" filters={none} showDivision={false} />);
    expect(screen.queryByRole("navigation", { name: "Audit log pages" })).toBeNull();
  });
});
