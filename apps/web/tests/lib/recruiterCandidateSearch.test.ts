import { describe, expect, it } from "vitest";

import {
  availabilityOf, EMPTY_SEARCH, experienceBand, paramsOf, salaryText, searchBody, stateOf, unknownSkill,
} from "@/lib/recruiterCandidateSearch";

const params = (query: string) => new URLSearchParams(query);

describe("rec-013 search state <-> URL", () => {
  it("reads skills, groups and filters from the URL and writes them back unchanged", () => {
    const query = "all=Java&all=Spring+Boot&any1=AWS&any1=Azure&any2=SQL&verified=1&exp_min=2&exp_max=5&location=Hyderabad&avail=immediate&avail=d15&qualification=B.Tech&sal_min=5&sal_max=10.5&source_id=0f8fad5b-d9cb-469f-a165-70867728950e&status=available&offset=50";
    const state = stateOf(params(query));
    expect(state).toEqual({
      all: ["Java", "Spring Boot"], any: [["AWS", "Azure"], ["SQL"]], verified: true, expMin: "2", expMax: "5", location: "Hyderabad",
      availability: ["immediate", "d15"], qualification: "B.Tech", salMin: "5", salMax: "10.5",
      sourceId: "0f8fad5b-d9cb-469f-a165-70867728950e", status: "available", offset: 50,
    });
    expect(stateOf(paramsOf(state))).toEqual(state);
  });

  it("drops hand-edited values the API would refuse, blanks and duplicates", () => {
    const state = stateOf(params("all=Java&all=java&all=+&any1=&any7=Go&avail=soon&exp_min=-1&exp_max=x&sal_min=abc&source_id=nope&status=gone&offset=-5"));
    expect(state).toEqual({ ...EMPTY_SEARCH, all: ["Java"] });
  });

  it("leaves out empty groups and compacts group numbers", () => {
    const state = { ...EMPTY_SEARCH, all: ["Java"], any: [[], ["AWS"]] };
    expect(paramsOf(state).toString()).toBe("all=Java&any1=AWS");
  });
});

describe("rec-013 request body", () => {
  it("turns years into inclusive months and lakhs into rupees", () => {
    const state = { ...stateOf(params("all=Java&any1=AWS&any1=Azure&exp_min=2&exp_max=5&sal_min=5&sal_max=10.5&avail=d30&verified=1")) };
    expect(searchBody(state)).toEqual({
      all: ["Java"], any: [["AWS", "Azure"]], verified_only: true, experience_min_months: 24, experience_max_months: 71,
      availability: ["d30"], salary_min: 500000, salary_max: 1050000,
    });
  });

  it("is null without a skill (nothing to search)", () => {
    expect(searchBody({ ...EMPTY_SEARCH, location: "Pune" })).toBeNull();
  });
});

describe("rec-013 labels and facets", () => {
  it("maps an experience facet onto the year fields", () => {
    expect(experienceBand("y0_1")).toEqual({ expMin: "0", expMax: "0" });
    expect(experienceBand("y1_3")).toEqual({ expMin: "1", expMax: "2" });
    expect(experienceBand("y3_5")).toEqual({ expMin: "3", expMax: "4" });
    expect(experienceBand("y5_plus")).toEqual({ expMin: "5", expMax: "" });
  });

  it("words the availability and salary of a card", () => {
    expect(availabilityOf(0)).toBe("Immediate");
    expect(availabilityOf(15)).toBe("15 days");
    expect(availabilityOf(45)).toBe("45 days");
    expect(availabilityOf(null)).toBe("—");
    expect(salaryText("800000.00")).toBe("₹8 LPA");
    expect(salaryText("750000")).toBe("₹7.5 LPA");
    expect(salaryText(null)).toBe("—");
  });

  it("reads an unknown-skill 422", () => {
    expect(unknownSkill({ code: "unknown_skill", term: "Jav", suggestions: ["Java"], message: "No skill" })).toEqual({ term: "Jav", suggestions: ["Java"] });
    expect(unknownSkill("Add at least one skill")).toBeNull();
  });
});
