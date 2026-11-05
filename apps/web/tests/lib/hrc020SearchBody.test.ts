import { describe, expect, it } from "vitest";

import { EMPTY_SEARCH, isSavedSearch, paramsOf, searchBody, type SearchState, stateOfBody } from "@/lib/recruiterCandidateSearch";

// hrc-020 (DEC-SCOPE-401 X2, AC1): a saved search body restores the page's filters exactly.
const CAT = "0f8fad5b-d9cb-469f-a165-70867728950e";
const SOURCE = "6a2f41a3-c54b-4b8e-9f0e-2a1d3c4b5e6f";
const full: SearchState = {
  ...EMPTY_SEARCH,
  text: "kafka microservices", all: ["Java", "Spring Boot"], any: [["AWS", "GCP"], ["Docker"]], preferred: ["Kubernetes"], verified: true,
  expMin: "2", expMax: "5", location: "Pune", availability: ["immediate", "d15"], qualification: "B.Tech", salMin: "6.5", salMax: "10",
  sourceId: SOURCE, status: "available", engagement: "screened", sort: "experience",
  more: {
    cat: [CAT], level: ["intermediate"], skill_yrs: ["1"], degree: ["B.E"], year_min: ["2018"], cgpa_min: ["7.5"], fresher: ["1"], rel_max: ["3"],
    emp_type: ["full_time"], relocate: ["1"], owner: ["me"], reg_from: ["2026-01-01"], resume: ["0"], app: ["shortlisted", "interview"],
    cur_min: ["4"], sal_unknown: ["1"],
  },
};

describe("hrc-020 stateOfBody", () => {
  it("is the exact inverse of searchBody, so a saved search restores its filters", () => {
    const body = JSON.parse(JSON.stringify(searchBody(full)));
    expect(stateOfBody(body)).toEqual(full);
    expect(paramsOf(stateOfBody(body)).toString()).toBe(paramsOf(full).toString());
  });

  it("reads the API's canonical JSON (decimals as strings)", () => {
    const state = stateOfBody({ all: ["Java"], cgpa_min: "7.5", salary_min: "650000.00", current_max: "1200000" });
    expect(state.more.cgpa_min).toEqual(["7.5"]);
    expect(state.salMin).toBe("6.5");
    expect(state.more.cur_max).toEqual(["12"]);
  });

  it("drops values the page would refuse, as for a hand-edited URL", () => {
    const state = stateOfBody({ all: ["Java"], status: "nope", sort: "weird", availability: ["d15", "x"], source_id: "not-a-uuid", app: 3 });
    expect(state).toEqual({ ...EMPTY_SEARCH, all: ["Java"], availability: ["d15"] });
  });

  it("recognises a saved search row", () => {
    expect(isSavedSearch({ id: "s1", name: "A", filters: { all: ["Java"] }, ignored: [], shared: false, mine: true, can_edit: true, owner: { id: "u", name: "U" } })).toBe(true);
    expect(isSavedSearch({ id: "c1", name: "Rahul", skills: [] })).toBe(false);
    expect(isSavedSearch({ id: "s1", name: "A", filters: [], ignored: [], mine: true })).toBe(false);
  });
});
