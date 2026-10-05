import { afterEach, describe, expect, it, vi } from "vitest";

import {
  BOARD_LABEL,
  display,
  gradeRange,
  isOrganizationBody,
  labelOf,
  ORG_TYPE_LABEL,
  orgDuplicate,
  profileGroup,
  profileNotEmpty,
  rolesFor,
  safeWebsite,
  teamSearch,
  typeChangeMessage,
} from "@/lib/bdmOrganizations";

afterEach(() => vi.unstubAllGlobals());

describe("bdm-003 profile helpers", () => {
  it("maps org types to profile groups", () => {
    expect(["agent", "school", "college", "university", "corporate", "training_institute", "other", ""].map(profileGroup)).toEqual(["agent", "school", "college", "college", null, null, null, null]);
  });
  it("writes grade ranges with pre-primary names", () => {
    expect(gradeRange(-1, 12)).toBe("LKG–12");
    expect(gradeRange(6, 12)).toBe("6–12");
    expect(gradeRange(-2, null)).toBe("From Nursery");
    expect(gradeRange(null, 0)).toBe("Up to UKG");
    expect(gradeRange(null, null)).toBe("—");
  });
  it("labels known values and shows an unknown one as it is", () => {
    expect(labelOf(BOARD_LABEL, "State")).toBe("State board");
    expect(labelOf(BOARD_LABEL, "Cambridge")).toBe("Cambridge");
    expect(labelOf(BOARD_LABEL, null)).toBe("—");
  });
  it("puts the type's suggested roles first and keeps every role", () => {
    expect(rolesFor("college").slice(0, 4)).toEqual(["principal", "dean", "hod", "placement_officer"]);
    expect(rolesFor("school").slice(0, 3)).toEqual(["principal", "management", "counselor"]);
    expect(rolesFor("agent")[0]).toBe("owner");
    expect(new Set(rolesFor("school")).size).toBe(8);
    expect(rolesFor()).toEqual(rolesFor("corporate"));
  });
  it("reads the profile_not_empty conflict and words it", () => {
    expect(profileNotEmpty({ code: "profile_not_empty", message: "x", fields: ["board", "grade_to"] })).toEqual(["board", "grade_to"]);
    expect(profileNotEmpty({ code: "possible_duplicate", matches: [] })).toBeNull();
    expect(profileNotEmpty(null)).toBeNull();
    expect(typeChangeMessage("school", ["board", "grade_to"])).toBe("Clear the School details before changing the type: Board, Highest grade.");
  });
});

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
