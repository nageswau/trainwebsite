import { afterEach, describe, expect, it, vi } from "vitest";

import { display, isOrganizationBody, ORG_TYPE_LABEL, orgDuplicate, safeWebsite, teamSearch } from "@/lib/bdmOrganizations";

afterEach(() => vi.unstubAllGlobals());

describe("bdm-002 lib", () => {
  it("labels every organization type", () => {
    expect(ORG_TYPE_LABEL).toEqual({ college: "College", university: "University", agent: "Agent", school: "School", corporate: "Corporate", training_institute: "Training Institute", other: "Other" });
  });

  it("parses only the possible_duplicate 409", () => {
    const m = { id: "1", code: "ORG-000001", name: "A", city: "K", archived: true, assigned_bdm_name: "Asha" };
    expect(orgDuplicate({ code: "possible_duplicate", message: "x", matches: [m], total: 3 })).toEqual({ message: "x", matches: [m], total: 3 });
    expect(orgDuplicate("Already archived")).toBeNull();
    expect(orgDuplicate({ code: "other", matches: [] })).toBeNull();
  });

  it("trusts a write response only when it carries an organization id", () => {
    expect(isOrganizationBody({ organization: { id: "o1" } })).toBe(true);
    expect(isOrganizationBody({})).toBe(false);
    expect(isOrganizationBody(null)).toBe(false);
  });

  it("links only http(s) websites", () => {
    expect(safeWebsite("https://mary.edu")).toBe("https://mary.edu");
    expect(safeWebsite("HTTP://x.org")).toBe("HTTP://x.org");
    expect(safeWebsite("javascript:alert(1)")).toBeNull();
    expect(safeWebsite(null)).toBeNull();
  });

  it("shows a dash for blanks", () => {
    expect(display(null)).toBe("—");
    expect(display("")).toBe("—");
    expect(display(0)).toBe("0");
  });

  it("searches active team BDMs of one type", async () => {
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => Promise.resolve(new Response(JSON.stringify({ items: [{ id: "b1", full_name: "Asha", email: "a@x", active: true, employee_id: "E1" }, { id: "b2", full_name: "Old", email: "o@x", active: false, employee_id: "E2" }], total: 2, limit: 20, offset: 0 }))));
    vi.stubGlobal("fetch", fetchMock);
    const page = await teamSearch("college")("as ha", new AbortController().signal);
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/v1/bdm/manager/team?limit=20&bdm_type=college&q=as+ha");
    expect(page.items).toEqual([{ id: "b1", label: "Asha", detail: "E1 · a@x" }]);
  });
});
